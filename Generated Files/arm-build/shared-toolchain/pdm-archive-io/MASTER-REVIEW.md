# Parent review: bounded PDM prototype

**Disposition: functional/source review passed within tested cases; owner
typing remains blocked. No standard-command performance screen, adoption or
upstream PR is authorized by this review.**

The typed production patch changes 68 lines in PDM's existing sdist module.
Review found no demonstrated successful-input artifact regression: metadata and
hardlink bookkeeping stay serial, large/nonregular entries retain streaming,
capped reads respect recorded size, and deferred errors preserve member order.
The cleanup path joins readers rather than leaving background work.

The first version failed a local BLE001 check and had an ambiguous queue shape.
The updated explicit exception-or-entry union avoids `None` path sentinels.
Its narrowly explained deferred catch is not a silent fallback.

`ROOT-REVIEW.txt` records a second independent run against the typed source:
owner-config Ruff and format checks pass and all eight focused proofs pass.
Source SHA256 before and after is
`50f0bad699bda95cfe58901f81f1dc30782a46d693efacbeb4ca64c58b434bb4`.
These checks use available Ruff 0.17.3, not the owner's pinned 0.16.6, and do
not substitute for the upstream suite or supported-Python/platform matrix.

The `entry` tuple can retain the previous completed future across refill;
`last` aliases also need accounting. Use the corrected conservative bound of
four capped payloads, about 256 KiB logical bytes, plus BytesIO/buffering,
exception and executor/thread overhead. This is not an RSS ceiling.
Speculative I/O can delay failure cleanup, and failed archive tails can differ.
Neither issue is hidden by the passing immutable-input tests.

## External tool-access blocker

The owner requires mypy 2.3.1. It is missing in available interpreters, and the
producer's isolated installation failed TLS. A distinct parent attempt used
uv's **secure platform certificate store**, retained certificate validation,
disabled retries and targeted a new private tool environment. It failed with
the same `HandshakeFailure`; raw output is `SYSTEM-CERTS-ACCESS.txt`.
No TLS/DNS/protection setting was weakened or changed globally.

An earlier parent guard aborted before networking because an assumed validation
interpreter did not exist; it was not an additional download attempt.
A read-only official release-asset lookup also returned HTTP 404; no tool was
acquired through it. The user-assistance dialog requested an approved mypy and
dependency wheelhouse or approved download access, but the user was unavailable.

Do not treat the typing gap as a source error or a pass. Keep this proposal
blocked pending real owner-config analysis; do not retry installations or spend
CI merely to bypass this local gate. Broader compatibility, peak memory and
full-command benefit remain unproven. Continue independent source work instead.
