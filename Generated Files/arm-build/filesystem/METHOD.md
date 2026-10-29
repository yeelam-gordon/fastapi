# Protected-filesystem and Defender attribution method

## Evidence boundary

The user reports Windows ARM CI lacks Dev Drive and requests optimization of unnecessary repeated scanning. Local read-only inspection confirms C: NTFS and Q: ReFS, but `fsutil devdrv query` was denied; ReFS alone does not establish trusted Dev Drive or effective Defender performance mode.

Microsoft documents synchronous antivirus scanning normally and asynchronous scanning in performance mode on a trusted Dev Drive, subject to antivirus/protection/version prerequisites. MDE is the broader endpoint-security platform; Defender Antivirus is one component. Neither a C:/Q: delta nor fewer file operations alone proves that antivirus caused the elapsed-time difference.

Sources: [Dev Drive performance mode](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint-antivirus-performance-mode), [Dev Drive workloads](https://learn.microsoft.com/en-us/windows/dev-drive/), [MDE overview](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-endpoint), [Defender Antivirus](https://learn.microsoft.com/en-us/defender-endpoint/microsoft-defender-antivirus-windows).

## Clean timing experiment

Colocate source, dependency environment, candidate code, temporary files, caches and outputs on the tested drive. Recreate environments; do not copy a venv or silently load Q: dependencies in a C: trial. Use identical versions and algorithms, one preparation and alternating paired fresh-output trials. Record preparation separately; do not call warmed filesystem results cold-machine measurements.

Prefer the simplest artifact-correct materialization reduction. Count extracted/staged files and observable archive/intermediate writes; preserve every delivered source/wheel member, metadata input and executable bit. Node/custom archive experiments must show value beyond a simpler selective extractor before adoption is justified.

Keep workload clocks separate from diagnostic tracing. C:/Q: location changes filesystem/storage conditions together, not just scanning. Mac benefit remains separately unmeasured until an appropriately controlled platform comparison.

## Optional Defender diagnostic

The cmdlets are available through this host's **Windows PowerShell** `ConfigDefenderPerformance` module, although they were not discovered in the initial PowerShell 7 probe.

Microsoft documents `New-MpPerformanceRecording -RecordTo <path> -Seconds <integer>`; recording requires elevation. Without `-Seconds`, stop by pressing Enter. There is no documented PID capture filter. Report grouping/time-window options filter analysis after capture, not collection.

Permission was requested for at most two 60-second recordings. The CLI dialog returned user unavailable and the bounded native Windows consent dialog returned no response, so **no trace has been authorized or started**. On this shared host, do not collect system-wide scan/process metadata without approval. Do not cancel another recording or bypass elevation.

If approved later, check installed syntax and existing recording state first; run baseline and candidate in separate normal-permission workload processes. Keep raw ETLs and security reports private and ignored, publishing only sanitized workload aggregates. Top-N report rows are truncated—not total scan counts—and summed scan duration is not equivalent to blocked build wall time.

Sources: [Analyzer workflow](https://learn.microsoft.com/en-us/defender-endpoint/tune-performance-defender-antivirus), [recording parameters](https://learn.microsoft.com/en-us/powershell/module/defenderperformance/new-mpperformancerecording), [report parameters](https://learn.microsoft.com/en-us/powershell/module/defenderperformance/get-mpperformancereport), [analyzer reference](https://learn.microsoft.com/en-us/defender-endpoint/performance-analyzer-reference).

No protection, exclusion, tamper, UAC, drive trust or shared-machine power settings will be changed.

## Initial C:/Q: findings

The first matrix is in [c-vs-q/REPORT.txt](c-vs-q/REPORT.txt). The Python full-extraction control is **not the existing uv frontend**; a follow-up is measuring that actual baseline. C: wheel work is roughly 0.53 seconds versus Q: 0.10 seconds. A mode-correct selective control unexpectedly stalls in sdist creation on C:, so its regression cannot be assigned to extraction or Defender without a same-writer control/profile.

Source checkout preparation was measured separately and excluded from build clocks. The initial matrix uses fresh source copies; the follow-up holds one prepared checkout fixed and uses fresh output directories to match repeated-build conditions more closely. Neither case establishes a cold-cache or scan-causality claim.
