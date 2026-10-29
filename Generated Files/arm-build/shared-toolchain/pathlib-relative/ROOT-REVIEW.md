# Parent review: PATH-001 exact-class guard

**Confirmed semantic counterexample, subsequently fixed as recorded below.**
The first prototype's parsed-ancestor comparison and whole-string lowercase
strategy appear coherent for the selected stock-class cases. However,
`type(self) in stock_types` uses class equality, not identity, so its promised
subclass fallback is not guaranteed.

Parent reproduction used a fresh native 3.13.15 process with the ignored pinned
CPython source directory prepended before pathlib import. The unchanged
baseline method was extracted from the pinned Git source AST and executed
against the same classes; no installed module or source file was modified.

The counterexample subclasses `PureWindowsPath` with a metaclass whose
`__eq__` returns true. The instance class also overrides equality to return
false. It is not identical to any stock class, yet tuple membership admits it:

```text
actual_stock_identity: False
tuple_guard_accepts: True
baseline ValueError 'a\b\Leaf' is not in the subpath of 'a'
candidate result b\Leaf
```

This is not evidence that ordinary paths failed, but it is a real breach of the
explicit exact-class/fallback boundary. Require an identity-safe guard and a
focused metaclass/subclass regression, retaining the small source scope and
existing semantic suite. Do not mask the case or claim passing selected tests
proved all subclass behavior. No benchmark or adoption is authorized yet.

## Fixed-guard closure

Producer `dbf330c2` replaces equality membership with identity-only checks and
adds both metaclass-equality and overridden-parent fallback cases. The new
regressions produce ten failures against the old guard; untouched baseline and
fixed candidate agree. Production change is 13 lines, with 62 test lines.

Parent source review found the identity checks correctly exclude those
subclasses. `ROOT-FIX-REVIEW.log` and `candidate-root-modules.json` retain an
independent fresh-source run: 447 selected tests, zero failures/errors and
71 documented skips. Candidate source SHA256 before/after is
`ffdec1568d6c4f6826ecfb8dfeaa77f9647ebc90598766ab353787927b019b3c`.
PATH-001 is closed for these cases; broader semantic assurance is not absolute.

This clears only a staged local diagnostic: a fixed microbenchmark including
fallback costs, followed by one stock-command C: screen only if justified.
No installed runtime, FastAPI source, CI or owner-facing change is approved.
Generator/type-guard overhead and failed-fast-path overhead remain performance
questions, not assumed negligible work.

## V1 cost gate: rejected, no full build

The fixed 21-case micro screen retained all 210 timings. Although shallow,
deep and root cases improved, Windows equal paths regressed about 28.5-34.0%
and the WindowsPath nonancestor case about 21.5%. The predeclared safeguards
failed. V1 is rejected; no C: runtime copies or standard build were started.
`MICRO-SCREEN.md` retains the complete result, not selected positive cases.

One separate, bounded design revision is under semantic review only: handle
the complete default case for the same exact stock class, retain cheap equal
handling and avoid repeating parent traversal after a failed lexical test.
Other classes/flags retain the old fallback. This does not replace V1 samples,
relax its gate or authorize another measurement automatically. Reject it if
clarity or semantic compatibility requires a broad rewrite.
