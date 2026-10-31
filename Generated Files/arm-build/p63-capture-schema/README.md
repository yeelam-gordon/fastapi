# One bounded hosted capture/schema attempt

This branch replaces only the existing manual `arm-build-experiment.yml`
(registered workflow 400167398). It does not allocate or dispatch a run, change
the default branch, publish a branch, or change any workflow's enabled state.
The unique job uses `windows-11-arm`, eight minutes, and only contents/actions
read plus OIDC write permissions. A future dispatch must be separately approved
for exactly one fresh VM and select `P63_ONE_EPHEMERAL_ATTEMPT`, on
`perf/arm-scan-schema`, attempt 1. The input is a scope acknowledgement, not
reusable authority or a substitute for that external approval.

`hosted.ps1` protects a new job-local private directory for the current identity
and SYSTEM before any bootstrap output. The existing P50 bootstrap supplies
hash-verified PSF CPython 3.12.10 ARM64; official uv 0.13.6 is downloaded and
hash-verified before capture. There are no package installs, retries, baseline
builds, matrices, or extra workflows. All download, API, OIDC, tool inspection,
offline input preparation, and baseline inventory work precedes recording.
Signed hosting proof remains exclusively in the copied controller.

`hosted.py` obtains the sole running job's numeric ID from the attempt's jobs
API, requiring its exact logical name, runner, label, and attempt. It writes
the private path/hash-only plan and authority for that current run/job/head/ref,
binding both to the canonical runner-provided `GITHUB_WORKSPACE`.
The authority has scope `P63_ONE_EPHEMERAL_ATTEMPT`, approved true,
accepted transient overshoot true, workflow ID 400167398, timeout eight
minutes, exact plan SHA-256, and expiry 900 seconds ahead (at most 1800).
No actual approved authority is shipped in this branch.

The initial collector/test copies were formatting-only, with an independently
retained AST-equality proof. The final candidate applies exactly three reviewed
correction scopes: canonical job-wide one-shot location, optional live buffer
counts, and verified private-root creation before raw disk writes.
`source-pins.json` binds the four executed collector files' new byte hashes;
the existing eight-helper closure and published guardian remain unchanged.
`HANDOFF.md` is an unchanged historical collector handoff, not a hosted
verification claim. Its previous unavailable-format-tool note does not describe
the copied files' later local style validation.

## Public OSS fixtures

`fixtures/source-proof.json` is actual `source.prove` output, freshly checked
against all 2557 raw Git blobs and executable flags at FastAPI revision
`864b569cf8453654fc3bc2c64108c0f644e2918c` (0.119.1). The canonical LF source
archive SHA-256 is
`4cba86b9b9d61883fe786425a505149ca777782cfe266e274796097c30eb8e83`.
It contains no Git directory or Generated Files tree. FastAPI's MIT license
is included as `FASTAPI-LICENSE.txt` and in the original archives.

The unchanged PDM backend 2.5.0 wheel SHA-256 is
`5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63`;
its MIT license is inside the wheel and the inherited helper cohort's
`PDM-LICENSE.txt`. The two `reference` archives are exact previously accepted
stock FastAPI outputs, not new baseline builds. Their archive inventories,
package metadata and wheel RECORD are checked without executing package code.
Every fixture's digest is in `fixture-hashes.json`. No local research manifest,
environment receipt, Windows proprietary code, credential, or signed URL is
included.

Capture invokes exactly one existing `frontend.argv_for("B", ...)`, offline:
sdist then wheel from that sdist. Standard source-unchanged, full inventory,
metadata/RECORD, member order, tar content, and wheel byte oracles are not
waived. Collection is bounded to 64 MiB configured circular buffers, a requested
30 seconds, owned stop at most 60 seconds, and a 128 MiB post-stop acceptance
check, **not a hard write quota**. Transient overshoot and residual buffers
until VM teardown remain accepted risks only for that separately approved VM.

## Publication and remaining gates

Only the exact classified `p63-public/public-result.json` is uploaded, even
after failure. All raw ETL/reports, command streams, errors, authority, plan,
paths and environment stay private until VM teardown. A durable private exit
receipt propagates nonzero after upload; neither `continue-on-error` nor a
success-shaped fallback is used. Default Python CLIs perform no collection.

Production complete-circular-history coverage is unimplemented and always
UNKNOWN/nonzero, including after valid capture/schema and artifact checks.
This is not Defender causality, total cost, zero cost, or performance evidence.
ARM WPR status shape, wrapper/decoder compatibility, current admin token,
live signed OIDC/API receipts and cleanup remain unexercised runtime gates.

## Three bounded controller corrections

1. The exclusive run/job marker and capture root use the canonical
   `GITHUB_WORKSPACE`, bound in both authority and hashed plan, never caller
   cwd. The controller rejects aliases, UNC paths and any reparse-point
   ancestor before exclusive creation. A consumed attempt remains consumed
   after bootstrap failure, cwd changes, or a new interpreter invocation.
2. The pinned profile and actual `-profiledetails` still require two configured
   32 x 1024 KiB collectors. Existing read-only profile-details metadata reports
   `WPR_initiated_WprApp_WPR System Collector` and
   `WPR_initiated_WprApp_Owned Engine Memory`; existing advanced-help evidence
   defines `-instancename` as the final session-operation argument. Live status
   must match the exact owned-instance names, profile, Memory mode, sizes,
   provider, ProcessThread keywords and loss fields. Counts are optional in
   live status; any supplied count must be 32. No live count is inferred when
   absent. The native instance-specific format remains a runtime compatibility
   gate, not a local live-status observation.
3. Before any raw receipt, guardian import, redirected stream or private error
   is written, `private_root.ps1` atomically creates the directory with its
   protected DACL using .NET Framework `Directory.CreateDirectory(path, acl)`.
   It then verifies owner, protection, exactly the current SID/SYSTEM allow
   rules, FullControl/inheritance flags, no reparse point, and an empty root.
   The one fixed ACL-only Windows PowerShell process uses memory pipes, a
   ten-second timeout, no profile, no token-bearing environment, and no guardian
   or trace/build operation. Failure exposes only a fixed category/error hash
   and never persists raw diagnostics under the unverified candidate root.
   The outer pwsh bootstrap uses the corresponding .NET
   `FileSystemAclExtensions.CreateDirectory(acl, path)` API and the same DACL
   verification before opening its log. Positive child environments include
   `NoDefaultCurrentDirectoryInExePath=1` and exclude GitHub/OIDC credentials.

The original source namespace is untouched. The initial format-only proof is
not a claim that the final corrected controller AST equals the original.
Targeted source review, hosted wiring/privacy review, and explicit finite
allocation approval remain required. No runtime gate is marked passed.

Primary API/format references:

- https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpr-command-line-options
- https://learn.microsoft.com/en-us/dotnet/api/system.io.directory.createdirectory?view=netframework-4.8.1
- https://learn.microsoft.com/en-us/dotnet/api/system.io.filesystemaclextensions.createdirectory?view=net-8.0
