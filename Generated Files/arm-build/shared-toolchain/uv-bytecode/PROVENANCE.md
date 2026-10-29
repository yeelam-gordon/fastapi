# P22 public-source provenance

Fetched 2026-10-29 using read-only HTTPS and GitHub metadata; source bodies stayed
in memory, no source mirror or new dependency. `git ls-remote
https://github.com/astral-sh/uv.git 'refs/tags/0.13.6*'` returned:

```text
329bf9448afd9f9088d14a4d57fbc61eb454f117 refs/tags/0.13.6
```

This matches the `329bf9448` prefix in existing frontends evidence; the public
source identity is not a new binary-verification claim. Anonymous tree API hit
rate limiting; authenticated `gh api` tree lookup succeeded. Unavailable guessed
paths were discarded, not used as evidence.

## Immutable citation index

All line numbers are 1-based at that commit, not mutable main.

| ID | Public source and relevant lines |
|---|---|
| C1 | [Default directory plan: uv-build-commands 1566–1572](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-commands/src/lib.rs#L1566-L1572) |
| C2 | [sdist, extraction, wheel sequencing 808–865](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-commands/src/lib.rs#L808-L865) |
| C3 | [PEP 517 sdist builder 1163–1205](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-commands/src/lib.rs#L1163-L1205); [wheel builder 1276–1315](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-commands/src/lib.rs#L1276-L1315) |
| C4 | [Dispatch creates SourceBuild 633–658](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-dispatch/src/lib.rs#L633-L658) |
| F0 | [Backend import bootstrap 180–213](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L180-L213) |
| F1 | [State/ownership 241–269](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L241-L269) |
| F2 | [Temporary root 317](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L317); [isolated venv and requirements install 374–420](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L374-L420) |
| F3 | [Requirement hook, additional install, retained state 453–544](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L453-L544) |
| F4 | [Requirement hook script and runner 1140–1183](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L1140-L1183); [build hook and same venv 1040–1073](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L1040-L1073) |
| F5 | [Metadata reuse and Hatch caveat 866–905](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L866-L905); [same runner/venv 943–953](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L943-L953) |
| F6 | [Python command, flags, environment, spawn 1306–1334](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L1306-L1334) |
| D1 | [Build requirement installer 564–580](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-dispatch/src/lib.rs#L564-L580) |
| D2 | [Extra build environment overlays 621–631](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-dispatch/src/lib.rs#L621-L631); [PATH treatment 422–451](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-build-frontend/src/lib.rs#L422-L451) |
| K1 | [venv_dir returns TempDir 337–340](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-cache/src/lib.rs#L337-L340) |
| I1 | [Wheel installer implementation](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-installer/src/installer.rs); [separate compile-tree operation 15–47](https://github.com/astral-sh/uv/blob/329bf9448afd9f9088d14a4d57fbc61eb454f117/crates/uv-install-operations/src/bytecode.rs#L15-L47) |
| P1 | CPython 3.13 authoritative docs: [`-B`](https://docs.python.org/3.13/using/cmdline.html#cmdoption-B), [`-E`](https://docs.python.org/3.13/using/cmdline.html#cmdoption-E), [`-I`](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I), [`PYTHONDONTWRITEBYTECODE`](https://docs.python.org/3.13/using/cmdline.html#envvar-PYTHONDONTWRITEBYTECODE). Versioned documentation, not an immutable CPython source pin. |

## Minimal public excerpts

F6: `let mut command = Command::new(venv.python_executable());`
then `.args(["-c", script])` and `.envs(environment_variables)`.
The only preceding conditional arguments are `["-X", "lazy_imports=all"]`.

F3: `get_pep517_build_requirements(... &venv, ...)`, then
`.install(&resolution, &venv, build_stack)`.

K1: `tempfile::tempdir_in(self.bucket(CacheBucket::Builds))`.

P1: `-B`: “Python won’t try to write .pyc files on the import of source modules.”
`-E`: “Ignore all PYTHON* environment variables”.

## Retrieved text digests

SHA-256 of UTF-8-encoded HTTP response text (not a Git blob hash):

```text
503b365046802352dd1986b3d7c146840c3fdce19aa455e7ccf8369f419a44e3 crates/uv-build-frontend/src/lib.rs
f5e76aac806b555a893ba24af28a76d25b267d543af628e12ce40b556ef9debe crates/uv-build-commands/src/lib.rs
fe643e46a2faf7f30d8e6cee2c8fab8cfad3cd3815c090cdd1fb8bc38368655f crates/uv-dispatch/src/lib.rs
727252fe97dccfe5a0408e8a8cf66a959e4477c7ee8fd97164316d838cea6ff1 crates/uv-cache/src/lib.rs
314d761fbee7194f16b3fc1c1a5cee853bb4432fa2ee2e21ec04e241215a4e71 crates/uv-installer/src/installer.rs
```

Existing local context: `Generated Files\GOALS.md`, `PERSONA.md`, `PRIOR-WORK.md`,
`arm-build\frontends\REPORT.md`, `arm-build\protocol\PROPOSAL.md`,
`arm-build\protocol\wrapper-evidence\bytecode-policy\probe.json`.
Context checkout before this report: `bfb7eacbd832da2a959ed00060f47480b77b68c7`.
Only this directory is owned/changed. No benchmark or new interpreter probe ran.
