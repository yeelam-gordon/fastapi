# Stock hosted FastAPI HOBL on Windows NTFS and macOS

Measure native packaging and all covered tests on standard hosted Windows
ARM64 C: NTFS and macOS ARM64, with no storage or runtime treatment. This
is a new cross-platform timing reference, not a causal optimization test
or a measurement of the combined ordinary-ReFS-cache recipe.

One manual fork dispatch, attempt 1 only: two jobs, ten minutes each,
a point-in-time queue check and a five-minute queue acceptance bound
from run creation to each job's recorded start, four stock rows per host, no warmups,
retries or exclusions. Use the existing common82 workload, Python 3.13.15,
native uv 0.13.6, fixed dispatch (four Windows workers, three Mac), exact
source closure and existing complete native, archive and coverage proofs.
Use `macos-15`: GitHub [retired `macos-14` on November 2, 2026](https://github.blog/changelog/2026-10-01-github-actions-macos-14-runner-image-retirement/).

Report all rows and per-host build, covered-test and total medians, plus job
wall time separately. No parity claim unless all eight rows pass the complete
proofs and Windows total is no greater than Mac at every matched position.
Do not demand cross-OS raw-map equivalence that the workload does not promise;
retain and audit all associations and require the existing within-host
equality. No extrapolation to physical machines or Dev Drive.
