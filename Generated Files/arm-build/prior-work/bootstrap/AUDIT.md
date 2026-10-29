# Prior bootstrap fixes: source-reviewed, not reproduced

Credit the original branch contributions, not this investigation. The audited commits identify Clint Rutkas with recorded Copilot App co-authorship. No foreign patch, test suite, benchmark or global installation was executed in this audit.

| Component | Pinned head | Focused merge base |
|---|---|---|
| pip | `d86a728fdcfa2f694149a466c745115af476ee11` | `d1fd55753405fd728a0751a578e27c1054acdf48` |
| CPython ensurepip | `0e522c49773a4be778a843d3a0251cae3b9d34c7` | **3.12** `063d4555c94ef412c731527dbf30193327f2ee82` |

## pip: Windows-only threaded bytecode compilation

The new path chooses `min(8, file_count, os.cpu_count() or 1)` threads on Windows when a wheel has at least eight source paths and at least two workers. Other cases remain serial. It still forces compilation, reads the source and writes bytecode; this is concurrency, not a bytecode cache or reduction in delivered files.

Diagnostics are buffered per task and replayed in input order. Exceptions propagate in that order; pending futures are cancelled and worker shutdown is awaited. Already-running tasks can still produce later `.pyc` files after an earlier failure, so deterministic reporting does not establish serial-equivalent side effects. Process-global output redirection also warrants care around unrelated threads.

Tests cover serial/threshold behavior, compilation and ordered errors, exception propagation and worker cleanup. They were inspected, not run. On GIL-enabled Python the expected benefit is overlapping filesystem waits, not guaranteed parallel CPU compilation. This path does not run on Mac and is therefore a genuinely Windows-gated prior proposal.

Primary sources: [implementation, lines 417–477](https://github.com/crutkas/pip/blob/d86a728fdcfa2f694149a466c745115af476ee11/src/pip/_internal/operations/install/wheel.py#L417-L477), [integration, lines 671–705](https://github.com/crutkas/pip/blob/d86a728fdcfa2f694149a466c745115af476ee11/src/pip/_internal/operations/install/wheel.py#L671-L705), [tests, lines 658–780](https://github.com/crutkas/pip/blob/d86a728fdcfa2f694149a466c745115af476ee11/tests/unit/test_wheel.py#L658-L780).

## ensurepip: bundled-wheel hardlink staging

The 3.12 POC attempts a hardlink from a bundled wheel to the temporary staging filename, falling back to the existing copy path on `OSError`. Distributor wheels remain copied. It does not remove pip's subprocess, package extraction or bytecode compilation.

It is **not Windows-gated**. A same-volume Mac path could benefit too. The relevant placement is bundled wheel versus temporary directory—not just venv location. Hardlinks share file contents/attributes; real same-volume identity, cross-volume fallback, read-only cleanup, ACL behavior and source preservation need integration coverage. Added tests mock the OS and pip runner and do not establish those real filesystem properties.

Our installed 3.13.15 ensurepip already uses `_get_pip_whl_path_ctx()` and `shutil.copy2()`. The 3.12 `_Package`/`read_bytes()` patch is not a literal drop-in; its bytes-buffer rationale cannot be carried across unchanged. These Python-level mechanisms can be tested in isolated module arrangements without rebuilding all CPython, but the base interpreter's shared stdlib must never be edited.

Primary sources: [POC, lines 167–208](https://github.com/crutkas/cpython/blob/0e522c49773a4be778a843d3a0251cae3b9d34c7/Lib/ensurepip/__init__.py#L167-L208), [POC tests](https://github.com/crutkas/cpython/blob/0e522c49773a4be778a843d3a0251cae3b9d34c7/Lib/test/test_ensurepip.py#L60-L122), [3.13.15 implementation](https://github.com/python/cpython/blob/4061bc4c35f7c26f25264666d4ba083b93d2f6f9/Lib/ensurepip/__init__.py#L154-L173), [Windows hardlink semantics](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/FileIO/hard-links-and-junctions.md#L16-L34).

## Relevance and next gate

Neither source change proves reduced Defender scanning, ARM speedup or the supplied numerical result. pip overlaps existing work; ensurepip can avoid a wheel copy, but later reads/scans still occur.

Our earlier dependency ZIP experiment is not this pip algorithm. If either exact prior fix is reproduced or adopted, label it accordingly. First determine whether the selected build frontend actually invokes the affected pip/ensurepip path; outer scenario preparation must not be assigned to an inner package-build timer.

Confidence: high on source mechanisms, lineage and the 3.12/3.13 mismatch; medium on expected tradeoffs; performance magnitude remains unverified.
