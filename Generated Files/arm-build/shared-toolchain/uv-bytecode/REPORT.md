# P22: uv isolated-hook import bytecode — source-only feasibility

2026-10-29. **Decision: no-go for an upstream default change on present evidence.**
The write opportunity exists, but uv does not ignore Python's existing suppression
environment variable, and the supposedly disposable cache is reused by later hooks.
No implementation, timing, installation, CI, push, owner contact or PR performed.

Read GOALS, PERSONA, PRIOR-WORK, frontends/REPORT and protocol/PROPOSAL plus the
existing wrapper bytecode probe. Common-tool improvements rank first, portable
practice second; private-PDM SDK machinery remains paused and diagnostic-only.
Nothing here establishes Windows/Mac parity or advances the tests/hardware goal.

## Conclusions

All uv citations below resolve to **0.13.6,
`329bf9448afd9f9088d14a4d57fbc61eb454f117`**; [provenance](PROVENANCE.md)
provides immutable URLs, line ranges and minimal excerpts.

| Question | Source result | Confidence |
|---|---|---|
| Standard-command relevance | Default directory `uv build` selects sdist-to-wheel; builds sdist, extracts it, builds wheel from extraction. PDM uses PEP 517, not the native `uv_build` shortcut. [C1–C3] | High |
| Environment lifetime | Each PEP 517 stage creates its own `SourceBuild`, owning a temporary directory/venv. The sdist builder ends before wheel setup; two environments, not one shared sdist/wheel environment. Downloaded/cached requirements are distinct from environment reuse. [C2–C4, F1–F3, K1] | High |
| Hook reuse | Within a stage, setup installs declared requirements, runs `get_requires_for_build_*`, and installs additional requirements into the **same venv**. Build runs there too. A separate Python process is spawned per hook: Python memory is not reused, filesystem `.pyc` can be. [F2–F4, F6] | High |
| Metadata | The ordinary command's stage builders call `builder.build`, not `metadata()`. Other frontend consumers can call metadata then build on the same object/venv; metadata result is retained. Dynamic Hatch metadata has an existing special-case bypass. Do not assume three hooks on every ordinary build. [C2–C3, F1, F5] | High |
| Exact Python flags | On observed Python 3.13 path: `<venv-python> -c <generated-hook-script>`. **No `-I`, `-E`, `-B`, `-s`**. Only preview-enabled CPython >=3.15 adds `-X lazy_imports=all`. Backend bootstrap removes an empty leading `sys.path` entry, adds declared backend paths, imports backend; it does not set `sys.dont_write_bytecode`. [F0, F6] | High |
| Environment policy | Child inherits parent environment, overlays build variables, sets `UV_INTERNAL__BUILD_DIR`, modified `PATH`, `VIRTUAL_ENV`, `PYTHONIOENCODING=utf-8:backslashreplace`, and removes four credential variables. No environment clearing or bytecode-variable removal here. `PYTHONDONTWRITEBYTECODE=1` therefore already reaches normal hooks unless overridden. Preserve existing credential handling. [D2, F6] | High |
| Are import writes possible? | Normal CPython source imports can create `.pyc` in writable locations when no suppression is set and valid cache is absent. Temporary backend site-packages writes can disappear at cleanup, **but can serve the next hook first**. Stdlib caches may outlive that venv; in-tree backend caches need not be temporary. Actual file counts/cost on standard uv were not measured. [F0–F6, P1] | High mechanism; low workload magnitude |
| What is already avoided? | Build-dependency install directly invokes uv's wheel installer, without the separate explicit compile-tree operation. Existing `build` frontend A already passes pip `--no-compile`. Neither is a ban on CPython import-cache writes. [D1, I1; existing frontends report] | High |
| `-I` / `-E` trap | Both ignore `PYTHON*` environment variables, including `PYTHONDONTWRITEBYTECODE`; explicit `-B` still works. That explains the private wrapper probe, **not uv's hook runner**, which uses neither flag. [P1; existing probe] | High |
| Shared-platform consequence | Suppression removes writes but may repeat parsing/compilation across hooks on Windows **and Mac**. `-B` does not prevent reading existing valid `.pyc`. No measured net benefit, ratio improvement or backend compatibility is established. | High tradeoff; low speedup |

## Owner, candidate and adoption gate

**Owner:** Astral's uv maintainers. If evidence eventually warranted a change, the
shared owner-level location is `PythonRunner::run_script` in
`crates/uv-build-frontend/src/lib.rs:1306–1333`, with policy supplied from
`SourceBuild`'s isolation state. A blanket `-B` there would also affect persistent
non-isolated environments and other frontend users: it is not acceptably scoped.
A hypothetical isolated-only policy still needs cross-backend proof, not a
FastAPI special case. No such patch or new option is recommended now.

The simpler supported alternative is a **process-scoped**
`PYTHONDONTWRITEBYTECODE=1` around the unchanged standard `uv build` command.
This is an existing Python capability, not our technique. It is an experiment
control, **not yet a portable best-practice recommendation**. It also propagates
to nested Python commands unless they ignore/override it, whereas adding `-B`
only to the first child does not automatically propagate to nested interpreters.
Do not silently treat these as equivalent policies.

Compatibility/review gates:

- **PDM:** no private patch; repeated requirement/build imports may benefit from
  the first hook's cache. Existing 2.5.0 FastAPI evidence is not cross-project proof.
- **setuptools:** dynamic requirements, legacy backend import/setup behavior and
  backend-launched Python tools can change the balance and suppression reach.
- **Hatch:** plugin/build/metadata hooks and uv's dynamic-metadata exception must
  remain intact; no metadata skipping/reuse change is proposed.
- **Other hooks/backends:** code can inspect `sys.dont_write_bytecode`, explicitly
  invoke compilation, spawn interpreters or package generated files. Suppression
  is not an output-equivalence proof and not a universal `.pyc` prohibition.
- **Environment reuse:** per-stage temporary environments are not per-hook
  disposable environments. Persistent/no-isolation and cache-reading behavior
  must not regress. Do not merge the two stage environments to make this win.
- **Mac:** apply any common policy to both ARM platforms; faster Mac builds may
  cancel or reverse any Windows/Mac ratio improvement.

**Maintainer-facing rationale:** This is the right upstream ownership boundary
only if a general isolated-build cost can be demonstrated across backends. At
0.13.6, uv already exposes Python's suppression behavior through inherited
environment variables, while deliberately reusing each build environment across
hooks. An unconditional suppression patch would trade filesystem writes for
repeated compilation, widen behavior for persistent environments, and add review
and compatibility burden without measured value. Therefore this investigation
does not justify an upstream change or PR; first establish that the supported
policy is materially better under the real lifecycle on both platforms.

## One later discriminating experiment, not authorization

Only if this lane is reopened: one bounded, paired **standard `uv build`**
experiment, baseline versus process-scoped `PYTHONDONTWRITEBYTECODE=1`, on native
Windows ARM and Mac ARM, with pinned identical sources/Python/uv/backend versions,
fresh default isolated environments and matched warm dependency caches. Use a
small PDM/setuptools/Hatch representative set including a dynamic hook case.
Record full-command paired wall time, hook/import-cache writes and repeat-hook
work; independently verify full sdist/wheel members, payloads, modes, metadata and
RECORD, retaining existing mode failures rather than normalizing them away.
Reject on artifact/behavior differences, reversals or noise; require worthwhile
repeatable savings on both platforms, and report Windows/Mac ratios. If this
existing environment policy wins, prefer documenting it over adding uv code;
only a demonstrated insufficiency reopens an owner-level implementation.

This is the smallest useful discriminator because it includes the lost
between-hook cache benefit rather than timing only a first import. It was **not
run**. No additional CI or custom SDK experiment is requested.

## Attribution and limits

Credit the supplied crutkas pip Windows threaded-bytecode work, reviewed in
PRIOR-WORK at `d86a728f`: it concerns explicit compilation parallelism, not this
import-write suppression question. No authorship, reproduction or applicability
claim is made for that work. The previous wrapper `-B` probe is existing internal
diagnostic evidence, not proof of uv subprocess flags. All new conclusions here
are source-reviewed, not locally/CI reproduced performance results.
