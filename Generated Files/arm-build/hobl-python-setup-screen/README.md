# Windows ARM Python setup SCREEN

Manual/reusable, owned-fork-only, one Windows 11 ARM job capped at four minutes;
no build, full HOBL, Mac, retries or project dependencies. The registered
`arm-build-diagnostics.yml` entry routes `hobl-python-setup-screen` exclusively
here. No runtime change or functional qualification is made.

Record the exact tool-cache executable and completion marker **before** the
pinned stock action. If both exist, skip the cold candidate: “gap not reproduced,
no change.” Otherwise install pinned uv's exact 3.13.15 in fresh workspace-owned
install/cache directories, without bin/registry registration, with verified TLS,
zero HTTP retries, a 20-second HTTP timeout and a strict 60-second install cap.

Use the unmodified SHA256 `45d6db4f...` guardian and require natural process drain.
Persist each receipt/stdout/stderr, including nanosecond wall readings, before
checking success or discovering/validating the interpreter. Discover via
`uv python find`, not alias-directory globbing. Probe stock and candidate native
PE/process, exact CPython, normal nondebug GIL, asyncio, SQLite and default-TLS
public PyPI JSON. Bundled OpenSSL/SQLite and distribution differences remain
explicit uncertainties; no third-party project dependencies are installed.

Join the finished GitHub job-step API stock action wall and candidate whole step
with precise install receipt externally. Advance only for a real cache miss,
at least 30 seconds saved **and** at least 50% reduction. Otherwise close with
no runtime change or further CI. Even a promising result is setup-only and
requires separately justified functional qualification, not a HOBL speedup claim.
