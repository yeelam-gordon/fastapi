# Prior Uvicorn changes: runtime work, not package building

**Source-reviewed, not reproduced.** The commits identify Clint Rutkas with Copilot App co-authorship. No foreign code/tests, installation or CI was run.

| Revision | SHA | Relationship |
|---|---|---|
| Baseline | `ee8e45ca472db17b4aef1d539f209539062d002e` | Uvicorn 0.52.1 |
| Graceful reload | `58779399365e7a79b5cbccaf9bb67fc25b73a9a6` | One commit above baseline |
| Reload dedup | `70ab5bafa84ac0f2b6520fdc223bd3a7831580f6` | Direct child of graceful reload |

## Verified mechanisms

Graceful reload uses a multiprocessing spawn event for supported Windows server targets. Restart requests cooperative child shutdown, joins it, then creates the replacement. Custom targets retain the older console-event fallback; POSIX keeps its existing termination path. The waiter thread sets the normal server exit flag, allowing connection/task draining and lifespan shutdown. Joins have no timeout/escalation, so bounded restart latency is not guaranteed.

Sources: [reload supervisor, lines 92–127](https://github.com/crutkas/uvicorn/blob/70ab5bafa84ac0f2b6520fdc223bd3a7831580f6/uvicorn/supervisors/basereload.py#L92-L127), [child waiter, lines 89–97](https://github.com/crutkas/uvicorn/blob/70ab5bafa84ac0f2b6520fdc223bd3a7831580f6/uvicorn/_subprocess.py#L89-L97).

Dedup is Windows-only in WatchFilesReload, after existing event filtering. It tracks file generations using content hashes plus metadata and bounded history: 1,024 file generations, 32 batches and 8,192 remembered batch-path entries. Missing files have a deletion sentinel; other read failures conservatively request reload. It still reads/hashes each eligible file, without a file-size/time bound. It is not a universal exactly-once or time-window debounce guarantee.

Sources: [generation/dedup path, lines 99–216](https://github.com/crutkas/uvicorn/blob/70ab5bafa84ac0f2b6520fdc223bd3a7831580f6/uvicorn/supervisors/watchfilesreload.py#L99-L216), [history limits, lines 18–27](https://github.com/crutkas/uvicorn/blob/70ab5bafa84ac0f2b6520fdc223bd3a7831580f6/uvicorn/supervisors/watchfilesreload.py#L18-L27).

## Independent applicability assessment

Neither focused diff changes package building or installation. Graceful behavior is shared by reload backends through BaseReload; dedup requires WatchFiles. The new paths are Windows-gated, not demonstrated Mac improvements.

Directory-descendant exclusions already existed in the baseline. Event filtering/dedup happens after watcher delivery (`watch_filter=None`); it does not prove fewer OS watch registrations or reduced MDE scanning. The NTFS rationale is not causal telemetry.

The branch includes mocked ordering/error/history tests and native-Windows integration coverage, but this audit establishes neither passing test status nor ARM-specific performance. Native integration cleanup forcibly terminates workers, so it does not verify graceful final console shutdown.

Build-first disposition: retain as credited prior runtime work; do not combine reload gains with package-build or installation metrics.

Confidence: high on ancestry, implementation gates and workload separation; measured performance and MDE causality remain unverified.
