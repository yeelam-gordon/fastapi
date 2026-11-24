"""Explicit worker-only Proactor pipe factory; no policy or stdlib mutation.

The small pipe constructor follows CPython 3.13 windows_utils.pipe, adding
PIPE_REJECT_REMOTE_CLIENTS. PIPE_NOWAIT is a legacy synchronous pipe mode,
not an alternative to real overlapped reads. This is a review prototype only.
"""

import _winapi
import asyncio
import ctypes
import errno
import os
import threading
from asyncio import windows_utils
from ctypes import wintypes

PIPE_REJECT_REMOTE_CLIENTS = 0x8
PIPE_NOWAIT = 1
BUFFER_SIZE = 8192
api = ctypes.WinDLL("kernel32", use_last_error=True)
api.GetNamedPipeHandleStateW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    wintypes.DWORD,
]
api.GetNamedPipeHandleStateW.restype = wintypes.BOOL
api.GetHandleInformation.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
api.GetHandleInformation.restype = wintypes.BOOL
for _name in ("GetNamedPipeServerProcessId", "GetNamedPipeClientProcessId"):
    getattr(api, _name).argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.ULONG),
    ]
    getattr(api, _name).restype = wintypes.BOOL


def checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())


def mode(handle):
    value = wintypes.DWORD()
    checked(
        api.GetNamedPipeHandleStateW(
            handle, ctypes.byref(value), None, None, None, None, 0
        )
    )
    return value.value


def local_pipe():
    """Default security, non-inheritable, first-instance, one local client."""
    reader = writer = None
    try:
        address = rf"\\.\pipe\python-pipe-{os.getpid()}-{os.urandom(8).hex()}"
        reader = _winapi.CreateNamedPipe(
            address,
            _winapi.PIPE_ACCESS_DUPLEX
            | _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE
            | _winapi.FILE_FLAG_OVERLAPPED,
            _winapi.PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1,
            BUFFER_SIZE,
            BUFFER_SIZE,
            _winapi.NMPWAIT_WAIT_FOREVER,
            _winapi.NULL,
        )
        writer = _winapi.CreateFile(
            address,
            _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
            0,
            _winapi.NULL,
            _winapi.OPEN_EXISTING,
            0,
            _winapi.NULL,
        )
        operation = _winapi.ConnectNamedPipe(reader, overlapped=True)
        operation.GetOverlappedResult(True)
        for handle in (reader, writer):
            flags = wintypes.DWORD()
            checked(api.GetHandleInformation(handle, ctypes.byref(flags)))
            if flags.value & 1:
                raise RuntimeError("inheritable pipe")
        # Both PID APIs require the server handle returned by CreateNamedPipe.
        for name in ("GetNamedPipeServerProcessId", "GetNamedPipeClientProcessId"):
            process = wintypes.ULONG()
            checked(getattr(api, name)(reader, ctypes.byref(process)))
            if process.value != os.getpid():
                raise RuntimeError("pipe endpoint process mismatch")
        return reader, writer
    except BaseException as original:
        for handle in (reader, writer):
            if handle is not None:
                try:
                    _winapi.CloseHandle(handle)
                except BaseException as cleanup:
                    original.add_note(f"pipe cleanup failure: {cleanup!r}")
        raise


class Writer:
    def __init__(self, handle):
        self.handle = handle
        self.lock = threading.RLock()

    def fileno(self):
        with self.lock:
            if self.handle is None:
                raise OSError(errno.EBADF, "closed pipe writer")
            return self.handle

    def send(self, data):
        with self.lock:
            count, error = _winapi.WriteFile(self.fileno(), data, overlapped=False)
            if error:
                raise OSError(error, "synchronous pipe write failed")
            if count == 0:
                raise BlockingIOError(errno.EWOULDBLOCK, "pipe buffer full")
            return count

    def close(self):
        with self.lock:
            if self.handle is not None:
                _winapi.CloseHandle(self.handle)
                self.handle = None


class WorkerProactorEventLoop(asyncio.ProactorEventLoop):
    def __init__(self, proactor=None):
        self._use_pipe = (
            proactor is None
            and threading.current_thread() is not threading.main_thread()
        )
        if not self._use_pipe:
            super().__init__(proactor)
            return
        # IocpProactor allocation precedes BaseEventLoop initialization in stock.
        # A closed sentinel makes the inherited destructor safe at that boundary.
        self._closed = True
        try:
            super().__init__()
        except BaseException as original:
            for endpoint in (
                getattr(self, "_ssock", None),
                getattr(self, "_csock", None),
            ):
                if endpoint is not None:
                    try:
                        endpoint.close()
                    except BaseException as cleanup:
                        original.add_note(f"endpoint cleanup failure: {cleanup!r}")
            owned_proactor = getattr(self, "_proactor", None)
            if owned_proactor is not None:
                try:
                    owned_proactor.close()
                except BaseException as cleanup:
                    original.add_note(f"owned proactor cleanup failure: {cleanup!r}")
            self._proactor = self._selector = None
            if all(
                hasattr(self, name)
                for name in (
                    "_thread_id",
                    "_ready",
                    "_scheduled",
                    "_default_executor",
                    "_debug",
                )
            ):
                try:
                    asyncio.BaseEventLoop.close(self)
                except BaseException as cleanup:
                    original.add_note(f"base loop cleanup failure: {cleanup!r}")
                    self._closed = True
            else:
                self._closed = True
            raise

    def _configure_pipe(self):
        if [mode(self._ssock.fileno()), mode(self._csock.fileno())] != [0, 0]:
            raise RuntimeError("initial pipe modes")
        _winapi.SetNamedPipeHandleState(self._csock.fileno(), PIPE_NOWAIT, None, None)
        if [mode(self._ssock.fileno()), mode(self._csock.fileno())] != [0, 1]:
            raise RuntimeError("reader WAIT / synchronous writer NOWAIT")

    def _make_self_pipe(self):
        if not self._use_pipe:
            return super()._make_self_pipe()
        reader, writer = local_pipe()
        self._ssock = self._csock = None
        try:
            self._ssock = windows_utils.PipeHandle(reader)
            self._csock = Writer(writer)
        except BaseException as original:
            for handle, wrapper in ((reader, self._ssock), (writer, self._csock)):
                if wrapper is None:
                    try:
                        _winapi.CloseHandle(handle)
                    except BaseException as cleanup:
                        original.add_note(
                            f"unbound endpoint cleanup failure: {cleanup!r}"
                        )
            raise
        self._configure_pipe()
        self._internal_fds += 1
