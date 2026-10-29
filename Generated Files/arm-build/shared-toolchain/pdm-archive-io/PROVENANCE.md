# P23 source provenance

Read-only inspection on 2026-10-29. Workspace branch:
`investigate/arm-pdm-archive-io`; starting repository commit:
`bfb7eacbd832da2a959ed00060f47480b77b68c7`.
Only this directory's report/provenance are owned outputs.

## Official immutable sources

GitHub REST `repos/pdm-project/pdm-backend/git/ref/tags/2.5.0` returned a
**commit** object, `8c6653726f71afdb2059b44dc9c7706693e95be6` (no tag peel needed).
Source bytes were fetched over HTTPS from:
`https://raw.githubusercontent.com/pdm-project/pdm-backend/<commit>/<path>`.
No checkout, package install, import or execution of fetched code occurred.
Line citations in REPORT.md use the same immutable commit.

| PDM path | SHA256 of complete fetched bytes |
|---|---|
| `src/pdm/backend/sdist.py` | `f62cdc17df1b922d03e1ef8103ce1c0109c94966931d8909f8543b9243f41396` |
| `src/pdm/backend/base.py` | `6be4a8396d598e8a2ab1d8207f81b96b1a813ce63f6a31227b210539a6243dd2` |
| `src/pdm/backend/utils.py` | `76833680ee7fa0d686fcc331392cef3a17d7fc65aedb465c6f78ee4a2efb26cf` |
| `src/pdm/backend/__init__.py` | `24a162a914cf4b49c2c3b3d4e3e1617079549736f6cbba29a966d351cb9051c3` |
| `src/pdm/backend/hooks/version/__init__.py` | `83e8939f5184a3e1ebf64b8d0916c4a5c9fcfd28734ca47fdca04d0e8ecd5045` |
| `tests/test_api.py` | `0430788cd9c82c63e60aff92303e93b47d420645ce4a026df5f0f2786d5d1fff` |
| `tests/test_hooks.py` | `6c5a1acc0720db8dc9eb4d27db32d1549a46ce2597b17e1167a9b8cd1a38ceb7` |

CPython reference: REST tag `v3.13.15` returned annotated tag object
`9cb432a43babc597b349cabb704870e88a82a382`; peeling through
`repos/python/cpython/git/tags/<tag-object>` returned commit
`4061bc4c35f7c26f25264666d4ba083b93d2f6f9`.
This version matches the managed interpreter recorded by the historical
stdlib-ops README/evidence; it is a public implementation reference, not a new
audit of the installed managed binary or an asserted runtime for every old run.
Raw source used the same immutable URL pattern with `python/cpython`.

| CPython path | SHA256 of complete fetched bytes |
|---|---|
| `Lib/tarfile.py` | `9fedddf7e814c226cb7e1ac0aa603092eda40047367ec00ad740a81484a17d01` |
| `Lib/gzip.py` | `c397e928174259f77190fb7ab15421196eadec4c0b3f33ef1b57ec5a8052eb56` |

Exploratory `v3.14.0` tag lookup was not used as source evidence.

## Local historical evidence (unchanged)

Read GOALS, PERSONA, INVESTIGATION-AND-PROPOSALS and arm-build/PROFILING;
`results/profile-01/{profile.json,sdist.txt}` and its build log;
`filesystem/METHOD.md`; `filesystem/c-vs-q/{REPORT.txt,followup/REPORT.txt}`;
`filesystem/stdlib-ops/{README.md,REPORT.txt,ops.py,evidence.json}` (receipt prefix);
`candidate/ops.py`; and `profiles/sdk-validation/README.md`.
Paths are relative to `Generated Files` or `Generated Files/arm-build` as named.
These identify existing diagnostics, not executions authorized by P23.
Candidate code was inspected solely to distinguish whole-file task bounds from
byte bounds and to reject transplantation of private mode/selection policy.

Inspection used git/gh read operations and in-memory Python urllib/hashlib
fetching/line numbering. No source cache or scratch files were created.
Documentation-only verification: local relative-link existence, immutable
source-reference/hash consistency, scoped git diff whitespace check and committed
path review; no performance or behavioral tests were run.

## Fixed-cap design follow-up

Read-only inspection on the same date, starting at P23 commit
`87e32f3fea959eee8152cceb638a29a5a9ecd9d3`. Added source/design analysis only;
P22's separate stock-command measurement was not run or inferred here.
Additional complete public files fetched from the same immutable CPython commit:

| CPython path | SHA256 |
|---|---|
| `Lib/concurrent/futures/thread.py` | `62e194f69dcd39919d8c06d0abee8b92c6c3d3c71229d7b55e151005e2960a76` |
| `Lib/concurrent/futures/_base.py` | `6ca5d2bb59aa23af56d95dcdd31728fda687f7727e79f4465236d1f65c06b053` |

Relevant lines: thread worker exception storage 58–65, shutdown cancellation/join
220–239; Future cancellation limits 365–379; executor context exit 652–654.
No new production code, dependencies, framework, benchmark, C-drive write or CI.
