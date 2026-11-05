# Timestamp conversion, not an ETW diagnosis

The old cancellation error is reproducible without a real clock or network:
PowerShell decodes JSON `created_at` as `System.DateTime`, kind UTC. Passing
that object into `DateTimeOffset.Parse` implicitly converts it to a string
without its timezone. On this +08:00 machine, UTC14:09:03 is then parsed as
14:09:03+08:00 instead of14:09:03+00:00: **exactly28,800s error**.
This explains the old inflated queue age without asserting a bad system clock.
The corrected explicit-UTC helper returns181s for both original ISO text and
the automatically decoded DateTime property. The latter is now a regression
case in `required-backend-ci-readiness\test_queue_clock.ps1`.

The closed ETW R11 failure is different: its root-birth gate compares launch
QPC brackets, with typed QPC clock/frequency10MHz. Its safe tag cannot identify
missing/multiple/outside-bracket births. The timezone reproduction does not
establish a cause or justify another capture. No R12, raw trace retrieval,
gate relaxation or timestamp-window stretching was performed.

The restarted native-policy watcher also encountered a fixture-only file
sharing error while rapidly rewriting one mock-state filename. The cause of
that lock is unknown. Tests now use distinct owned state paths per case;
all8 cases pass and their files are removed. The hosted run was not retried.
