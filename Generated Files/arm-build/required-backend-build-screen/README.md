# Prepared-project required-backend build screen

Readiness only: no dispatch/admission, adoption, cold-environment or full-HOBL
claim. Manual fork route `required-backend-build-screen` is restricted to
`yeelam-gordon/fastapi`, branch `perf/required-backend-build-20261104`, attempt1.
Two eight-minute ARM jobs use the same runners as C1.

The original common preparation installs exactly82 pins, including publisher
PDM2.5.0, and preserves mandatory ujson-last. FastAPI is not installed. Common
setup timing is reported separately, excluded equally from A/B build clocks.
Each host performs exactly ABBA, no warmup/retry. B really disables isolation on
both hosts; its publisher-wheel/installed-RECORD/dynamic-requirements validation
is inside the native family clock. Every complete sdist→wheel build has an
immediate full archive/RECORD/payload/metadata/source audit. Normal completed
bytecode is retained and newly generated caches recorded; no cache cleanup.

Windows materiality: both ordered pairs ≥0.5s and ≥10%; macOS reports the same
real comparison without an absolute-gain workflow floor. Correctness is always
mandatory. Parent must review/freeze the decision and invocation before any
run. Compare Windows B/macOS B from that same measured cohort, without inferring
stable parity from two pairs. Trusted shared-runtime visibility is explicit,
not a security sandbox/default build-isolation claim.

Portable local invocation (after separately qualified common preparation):

```text
<prepared-python> build_screen.py --execute-reviewed --source <canonical-source> --prepared <common-prepared> --output <new-evidence> --uv <native-uv> --workers <host-count>
```

Default invocation refuses; existing output directories are never overwritten.
Only explicitly allowlisted text/JSON/log evidence and the two canonical public
FastAPI build outputs are uploaded. Actual wheel/sdist bytes let independent
reviewers recompute complete payload/RECORD inventories; they are not installed
native-package dumps. No package roots, caches, `.git`, environment dumps or
native traces are published.

A separate two-build Windows integration smoke passed using the disclosed local
83-distribution fixture without changing the public CI82 identity gate. It is
not materiality data; macOS and the public common preparation remain unexecuted.
