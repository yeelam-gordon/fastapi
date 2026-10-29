# Next experiments: close the measured gap without spending CI blindly

**Windows package-build parity is not demonstrated.** Observed runner medians are 2.679 s versus 0.730 s, but the strict artifact-identical comparison was rejected. Using those observations only suggests approximately 72.7% further Windows latency reduction would be needed. More compiler workers are not an answer to a packaging workload with no native compilation.

## Resolve artifact comparability before another timing run

The source-byte fix is already implemented and locally validated: disable Git archive newline conversion and record source hashes. A local canonical-source build now matches every Mac wheel/sdist member's contents. Five sdist shell-script executable modes still differ. Preserve that diagnostic; do not strip modes or relabel the result as equivalent.

Determine the required cross-platform sdist permission behavior before changing packaging. The existing release already builds on Linux. A wheel-only experiment could answer a narrower question but would change this round's complete-build workload and must be explicitly identified as a different experiment. No third CI run is scheduled while this acceptance decision remains open.

## First isolate the Windows critical path locally

Use the committed harness and fixed inputs to compare source/cache/temp/environment placement on the same local volume versus the current cross-volume arrangement. Record wall time, process CPU and file activity; preserve all archive checks. The local source bootstrap already showed uv falling back from hardlinks to copies across volumes, but that is **not proof** that it explains the CI build gap.

Use the direct PDM backend profile and, if its attribution is insufficient, a bounded Windows CPU/file-I/O trace. Respect other trace sessions and do not weaken antivirus, UAC, certificates or filesystem protections. Report orchestration, sdist extraction and Python startup separately from backend compression/file traversal. The current backend profile excludes those outer costs.

## Consider a native backend only as a separate compatibility experiment

The official [uv backend documentation](https://docs.astral.sh/uv/concepts/build-backend/) describes a tightly integrated native backend for pure-Python packages, including a bundled fast path. It is a plausible way to reduce Python/process overhead, **not a demonstrated FastAPI optimization**.

It is not a drop-in PDM replacement: its documented sdist behavior rewrites `pyproject.toml` and includes `pyproject.toml.orig`, and its layout/inclusion and versioning requirements must be evaluated against FastAPI's existing dynamic version and source files. A temporary snapshot experiment must quantify those differences. Do not change the project's backend, remove sdist contents or quietly weaken equivalence checks to advertise a speedup. Any accepted compatibility change needs an explicit requirement and separate decision.

## Distinguish shipping improvements from a platform contest

The existing release workflow already builds the universal Python artifact once on Linux; the sampled upstream build step was about one second at coarse timestamp resolution. Reusing an identical source-keyed artifact across platform test jobs can avoid unnecessary repeated packaging, but a cache hit is not a faster full build and must not be reported as one.

Pre-provisioning the backend is useful for repeated builds but saves less than one second in the corrected Windows CI trial. Keep isolated release correctness checks until a setup-inclusive benefit is established. The managed-Python provisioning change has a much larger observed pipeline effect than backend-isolation removal.

## Gate the next CI run

Apply the budget rule in [CIRCUMSTANCES.md](../CIRCUMSTANCES.md#limited-fork-ci-capacity). Require a reproducible local improvement, unchanged accepted artifacts, passing checks and a specific runner-only question. Do not schedule a third run merely to reduce noise or try an unvalidated flag.

## Physical devices and tests follow separately

Repeat the same source/tool/cache protocol on the real Windows and Mac devices; record actual CPU model, power, storage and thermals. The present 16-core VM and hosted 4-versus-3-CPU runners cannot prove the proposed physical 20-versus-16-core result.

For tests, first provision the repository's actual locked test group and extras and measure installation, collection and execution independently. The current smoke dependencies are a separate minimal experiment lock, not the full repository test environment. Sweep a small worker-count set before assuming all cores improve performance; preserve test selection and assertions.
