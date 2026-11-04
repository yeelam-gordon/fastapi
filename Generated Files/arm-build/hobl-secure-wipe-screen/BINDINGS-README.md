# Private Windows ARM64 binding builder

```powershell
python bindings.py --source <pinned-bindings-with-vendor> --python <qualified-venv-python> --output <NEW-private-root> --sdk-version 10.0.26100.0
```

Optional `--clang <existing-native-ARM64-clang-cl.exe>` overrides compiler
discovery. No acquisition, dependency installation, Git mutation or performance
execution is performed. Non-Windows, reused output roots, wrong source commits,
changed blobs, missing SDK/development inputs and failed ownership gates fail
nonzero with `UNQUALIFIED`, never a default success.

The source must be binding commit
`fb50afcbb80aee5e87d6f8b1d15e7238321387c9` with vendor commit
`f57e61e19229e23c4445b85494dbf7c07de721cb`.
Read-only input Git commit/tree verification checks all working-tree blobs.
The previously verified retained106-file manifest is also accepted only at its
anchored SHA256. Source is never changed.
Input checkout must preserve Git blob bytes (including line endings); the
builder rejects rewritten working files instead of repairing the checkout.

Existing Visual Studio is discovered with vswhere/installed directories, with
bundled CMake/Ninja and native ARM64 Clang. Registry/installed SDK discovery is
read-only. Exact tools/version, selected SDK/include/library paths and source
identities are recorded. The unchanged checked-in-C/CMake recipe uses Release,
`ref.c`, SABI3.10 and static `volatileaccessu.lib` with
`VOLATILE_ACCESSOR_LIB`. No internal/VCTIP flags or global policy changes.
Only preparation receives `VSCMD_SKIP_SENDTELEMETRY=1`.

The original guardian must be available in sibling `protocol`, or the existing
shared `hobl-complete-ci` folder, at the exact pinned SHA256. Compiler
preparation is bounded90s; independent probe/functional helpers30s. Any failure
or survivor makes the whole invocation unqualified; cleanup is not a waiver.

Output contract:

- `candidate\_argon2_cffi_bindings\...`: real API-mode native extension plus
  byte-identical installed reference Python files; no ctypes shim.
- `binding-proof.json`: schema1/status`PASS_FUNCTIONAL_PACKAGE`,
  `reference_image_sha256`, `candidate_image_sha256`,
  `candidate_package_root`, `sdk_version`, `compiler`, `target`.
- Exact build plan/source proof/receipts/logs and full functional evidence.

`candidate_package_root` is the absolute **overlay root** `<output>\candidate`,
not the inner package directory. The caller prepends that root to its own
`sys.path`; the native extension is its `_argon2_cffi_bindings\_ffi.pyd` child.

Reference/candidate actual PasswordHasher/pwdlib success/wrong/malformed and
full encoded/raw cases must agree, with native ARM64/PyInit__ffi import proof
and unchanged reference files. The unchanged public fixture salt is17bytes;
PasswordHasher's configuration default remains16bytes.

This qualifies only a current-host private package. It does not qualify a
wheel, downlevel Windows/runtime, deployment, full-HOBL gain or this image's
performance. SDK/compiler differences require their own measured CI cohort.
