# Independent diagnostic pipeline review

The read-only risk reviewer inspected frozen `c2554b5a`, then fixed
`11f2ff73`. Findings are functional/data-contract issues, not an exploit
assessment. Initial statements were static causal traces, not executed tests.

| ID | Severity | Finding | Current disposition |
|---|---|---|---|
| ARM-RISK-001 | High | Fresh workflow wheelhouse lacked the manifest required by the collector | Closed in reviewed source: manifest follows hash-required download. Parent independently verified a fresh official wheel -> workflow-format manifest -> collector handoff |
| ARM-RISK-002 | High | Collector searched the original package checkout for diagnostic helpers | Closed in reviewed source: helpers resolve from installed tools; canonical source remains separate |
| ARM-RISK-003 | Medium | Reader discarded the actual nested Actions Node identity schema | Closed in reviewed source: strict actual-schema translation, required-field validation and actual JS-produced contract fixture |
| ARM-RISK-004 | High | Regression test expected historical source objects in the shallow tooling checkout | Closed in reviewed source: validated DIAG_SOURCE supplies source objects; genuine shallow-tools proof retains source79 absence before/after |

The native-request false-input fix is also present and reports not-requested
without probing or running an extra native build.

No accidental raw-native upload was found in the inspected paths. That is a
bounded source assessment, not proof of every runtime or metadata behavior.
Native trace availability, Mac runtime/counter behavior and actual hosted
Actions execution remain explicit runner-only gaps.

The final immutable local C: integration observed all 16 actual Python children
across four instrumented passes and eight successful uv commands, using a fresh
singleton wheelhouse and genuine two-checkout layout. Existing failures remain
retained, including the unwaived five mode-only differences per build.

The final independent review at `1c54e40b9` closed all four findings and found
no remaining evidenced source/portable-collection blocker for one analysis
allocation. It inspected supplied runtime evidence rather than replaying
builds. Native capture and actual Mac/Actions behavior remain unverified.
This is not strict artifact, performance, parity or foundational-cause approval.
