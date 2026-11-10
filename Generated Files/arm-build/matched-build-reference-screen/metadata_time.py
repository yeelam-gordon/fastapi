"""UTC bounds arithmetic only; callers must first bind the owned process evidence."""

FILETIME_EPOCH = 116444736000000000
COMMAND_SECONDS = 30


def utc_window_ns(process, native_start_ns, native_end_ns, *, platform):
    """Return inclusive UTC nanosecond bounds without treating native clocks as UTC.

    Requires the caller's successful, naturally drained owned-process receipt,
    matching native/command/sidecar identities and unchanged metadata policy.
    Darwin's upper endpoint includes only the reported birth-time quantization.
    Like the inherited Windows proof, this assumes no intervening UTC clock step.
    """
    if not all(type(value) is int for value in (native_start_ns, native_end_ns)):
        raise ValueError("native clock values must be integer nanoseconds")
    duration = native_end_ns - native_start_ns
    if not 0 < duration <= COMMAND_SECONDS * 1_000_000_000:
        raise ValueError("native duration must be positive and within the command cap")
    if platform == "win32":
        birth = process.get("birth_filetime")
        if (
            type(birth) is not int
            or not FILETIME_EPOCH < birth < 2**64
            or "start_unix_interval_us" in process
        ):
            raise ValueError("real Windows creation FILETIME required")
        lower = (birth - FILETIME_EPOCH) * 100
        return lower, lower + duration
    if platform == "darwin":
        interval = process.get("start_unix_interval_us")
        if (
            not isinstance(interval, (list, tuple))
            or len(interval) != 2
            or not all(type(value) is int for value in interval)
            or interval[0] <= 0
            or interval[1] != interval[0] + 1
            or "birth_filetime" in process
        ):
            raise ValueError("Darwin one-microsecond Unix birth interval required")
        lower = interval[0] * 1000
        upper_birth = interval[1] * 1000 - 1
        return lower, upper_birth + duration
    raise ValueError("only explicit Windows or Darwin timestamp bounds are defined")
