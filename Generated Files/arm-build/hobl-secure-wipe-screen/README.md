# Finite secure-wipe whole-HOBL screen

Preparation only until separately reviewed, frozen and explicitly dispatched.
No automatic dispatch, retry, adoption or parity claim. Windows is the treatment;
macOS is an explicit **NOOP** publisher-versus-publisher noise control.

## Interface

Use the unchanged sibling `hobl-parallel-screen/screen.py prepare` on the pinned
FastAPI checkout with a new preparation directory, native uv0.13.6 and native
Python3.13.15. This reuses the established source fixture patches and hash-locked
82-distribution runtime; it is not an unmodified upstream checkout benchmark.
Then run this `screen.py` **with that preparation's venv Python**:

```
python screen.py --source CHECKOUT --prepared PREPARATION --output NEW_ROOT --uv NATIVE_UV --workers 4 --bindings-source PINNED_BINDINGS_CHECKOUT
```

macOS uses `--workers 3`, omits `--bindings-source`, and mirrors the installed
publisher for both arms. No hardcoded machine paths, affinity changes, CPU
overrides, offline fallback, dependency rescue, or source copying. Actual CPU
availability must match the hosted allocation. Normal bytecode, no pycache prefix,
stock5ms GIL/no JIT and original plugins remain enabled.

Windows invokes `bindings.py` exactly once outside clocks, passing `--source`,
`--python`, `--output` and `--sdk-version 10.0.26100.0`; its schema1
`PASS_FUNCTIONAL_PACKAGE` proof must tie the reference and candidate images.
`candidate_package_root` is the exact `NEW_ROOT/binding-build/candidate`
overlay directory containing `_argon2_cffi_bindings`, not the inner package.
Its public optional `--clang` interface is owned by the builder. Missing tools,
SDK/library/source identity or failed native lifecycle aborts before workloads;
there is no install or fallback route. See `BINDINGS-README.md`.

## Work and clocks

Exactly warmupA,warmupB,measuredA,measuredB,measuredB,measuredA. Each payload builds
the full sdist then wheel **from that sdist**, audits1196/58 members, RECORD,
source/version and complete same-host metadata before tests, then runs the
unchanged four/three-worker full covered command. Score is the sum of original
guardian native build and covered-test command clocks, including startup/flush.
Preparation, exact-ledger readiness and archive/case/coverage audits are excluded.
Build60s/test150s,480s total driver bound, observed-warmup admission and final audit
reserve; the workflow caps each job at10min.

All2643 cases/2513pass/130skip, compatibility-v1 cases, resource group order,
CTracer7.17.0,863files/1409contexts, real CLI-child/native worker flush and final
AB/BA reportable line/context loss checks are preserved. No collection-only
or filtered workload. Case IDs are canonicalized from the first observed warmup's
full worker collection; all other workers/payloads must match exact IDs/order and
outcomes. Source content is tied to the existing prepared fixture manifest.

The passive trylast observer explicitly records NOT_IMPORTED without forcing a
crypto import. Every worker must produce metadata; every actual call worker of
the tutorial004/005 security test families (all11 parameterized source variants)
must prove the correct private loaded image/path. At least one image must be
observed. Other observed images must also match; abstention is allowed only for
noncrypto workers. macOS uses the common Mach-O native check, never PE parsing.

## New reproducible-input fixture policy

Fresh CI must have no PID-temporary cache inputs. Before each subsequent payload,
only nonmanifest regular/non-reparse pytest PID-temporary files with matching
native pyc header, source size/mtime/co_filename and a **current owned worker PID**
may enter an exact ledger and be renamed to private quarantine outside clocks.
Unknown/changed input aborts. Completed ordinary `.pyc` files are never removed;
normal generation/use continues. All original file bytes/size/mtime/mode and
reference package hashes are checked before/after. This is a new labeled fixture
policy, not a claim about historical CI cleanup or a proven historical creator.

Both Windows measured order pairs must save>=0.5s AND>=2% with all contracts.
Mac NOOP timings are reported separately, never used as a matched Windows
control or mixed with old CI times. Two pairs provide at most MEDIUM directional
evidence; hosted/downlevel/production compatibility remains unqualified.

The callee is workflow_call-only and refuses any repository/branch/attempt other
than the owned fork's exact reviewed experiment branch, attempt1. Uploads list
only experiment manifests, raw case/resource/native-coverage/JUnit evidence and
safe summary; no source checkout, `.git`, credential/environment dump, compiler
tree, package image, quarantine file or binary glob is uploaded.

Builder evidence is exported through a fixed19-file basename allowlist plus a
SHA256 manifest: actual plan/source/library resolution, compiler version,
functional helper JSON stdout and every individual original guardian receipt.
The workflow names all20 exported files explicitly. Partial exports occur even
when preparation fails; an unknown new receipt blocks rather than disappearing.
Developer environment dumps, package/compiler/quarantine trees are never copied.

## Private integration entry

`run_payload(context, index, arm, measured)` is the exact normal complete-payload
entry used by the public six-payload loop. `_command` remains the shared original
guardian runner (native clock, build60/test150). No public partial-success,
iteration or skip-gate flag exists; normal CI still prepares the candidate and
executes all six plus final pair audits.

A separately admitted local qualifier may build an honest `SimpleNamespace`
context with `args` (uv/workers), `output`, `source`, frozen `before`, validated
`env`, private `images`, `result` (including rows), `deadline` (monotonic),
`owned_pids`, `cases`, `outcomes_reference`, `inventories`, and `coverages`.
It must validate/reuse source/helper/runtime/reference inputs and check
preservation afterward, without invoking candidate preparation. Local CPU16 with
an owned4-LP mask must be reported honestly, not presented as the hosted4-CPU
allocation. The public CLI CPU/native/82-distribution attestation is unchanged;
no exception for a local editable83rd FastAPI distribution has been added.
The fresh CI preparation intentionally installs only82 pins and imports FastAPI
from the checkout. A local83-distribution context is a payload-path-only
qualification difference, not a defect in the CI closure or preparation path.
