"""Captured-object API-close proofs, not numeric-handle reclamation polling."""

import asyncio
import socket
import sys
import threading
from dataclasses import dataclass


@dataclass
class Lifetime:
    loop: object
    reader: object
    writer: object
    reactor: object
    creator: threading.Thread
    identity: tuple
    platform: str
    close_returned: bool = False


def identity(thread):
    return id(thread), thread.ident, thread.native_id


def capture(loop):
    if sys.platform not in ("win32", "darwin") or loop.is_closed():
        raise RuntimeError("Only a live owned Windows/Mac loop can be captured")
    creator = threading.current_thread()
    reactor = loop._proactor if sys.platform == "win32" else loop._selector
    if sys.platform == "darwin":
        import selectors

        if type(reactor) is not selectors.KqueueSelector:
            raise RuntimeError("Mac requires actual stock KqueueSelector")
    return Lifetime(
        loop,
        loop._ssock,
        loop._csock,
        reactor,
        creator,
        identity(creator),
        sys.platform,
    )


def certificate(value, *, mac_source_qualified=False):
    if not value.close_returned:
        raise RuntimeError("Unmodified close must return successfully first")
    if identity(value.creator) != value.identity:
        raise RuntimeError("Creator Thread identity changed")
    loop = value.loop
    if not loop.is_closed() or loop._ssock is not None or loop._csock is not None:
        raise RuntimeError("Loop close-state mismatch")
    states = []
    for endpoint in (value.reader, value.writer):
        if type(endpoint) is socket.socket:
            state = (endpoint.fileno(), endpoint._closed, endpoint._io_refs)
            if state != (-1, True, 0):
                raise RuntimeError(f"Captured socket not fully closed: {state}")
        elif value.platform == "win32":
            from asyncio import windows_utils

            from prototype import Writer

            if type(endpoint) not in (windows_utils.PipeHandle, Writer):
                raise RuntimeError("Unexpected captured pipe endpoint type")
            state = endpoint.handle
            if state is not None:
                raise RuntimeError("Captured pipe wrapper retains handle")
        else:
            raise RuntimeError("Unexpected Mac endpoint type")
        states.append({"object_id": id(endpoint), "closed_state": state})
    if value.platform == "win32":
        if (
            type(value.reactor) is not asyncio.IocpProactor
            or value.reactor._cache
            or value.reactor._iocp is not None
            or loop._proactor is not None
            or loop._self_reading_future is not None
        ):
            raise RuntimeError("Proactor close-state mismatch")
    else:
        if not mac_source_qualified:
            raise RuntimeError("Mac native/source provenance remains unqualified")
        if (
            loop._selector is not None
            or value.reactor.get_map() is not None
            or not value.reactor._selector.closed
        ):
            raise RuntimeError("Captured Kqueue selector did not close")
    return {
        "creator": value.identity,
        "closer": identity(threading.current_thread()),
        "captured_endpoints": states,
        "api_close_success": True,
        "released_numeric_id_queries": 0,
        "instant_kernel_reclamation_claim": False,
    }
