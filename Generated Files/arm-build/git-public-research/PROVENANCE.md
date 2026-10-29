# Public-source provenance

Accessed **2026-10-29**. Only public product identifiers were used in queries.
Source files were read, never executed. No installer download, build, package
installation, CI run, push, PR or upstream contact was performed.

## Immutable code references

- **S1 — release identity:** [v2.56.0.windows.3 release](https://github.com/git-for-windows/git/releases/tag/v2.56.0.windows.3),
  published `2026-10-22T19:10:21Z`. Annotated tag object
  [`260a670435d66dd5cbf5ec4aad087550c0f55177`](https://api.github.com/repos/git-for-windows/git/git/tags/260a670435d66dd5cbf5ec4aad087550c0f55177)
  resolves to commit
  [`0e9926caea36270e3e9067b5ac512ac0335a004a`](https://github.com/git-for-windows/git/commit/0e9926caea36270e3e9067b5ac512ac0335a004a).
  Release asset:
  [Git-2.56.0.3-arm64.exe](https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.3/Git-2.56.0.3-arm64.exe).
  Release notes advertise SHA256
  `53cfe6358a1f0573c8c777c9ad71151df8f29986759c689c7b8a5cbb84cca495`;
  **not independently downloaded/hash-verified**. Release pages/assets are
  publisher-mutable, unlike the pinned Git object identities.
- **S2 — MSYS2 environment matrix:** [environments.md L14–31](https://github.com/msys2/msys2.github.io/blob/7d591272bcc04087c576664c831736c292cd5a5c/web/docs/environments.md#L14-L31);
  [CLANGARM64 introduction L100–106](https://github.com/msys2/msys2.github.io/blob/7d591272bcc04087c576664c831736c292cd5a5c/web/docs/environments.md#L100-L106).
- **S3 — release-adjacent package/installer sources:**
  [PKGBUILD L20–25, exact version and environments](https://github.com/git-for-windows/MINGW-packages/blob/743878777844a6e74ce8af749daa3384bfaeed30/mingw-w64-git/PKGBUILD#L20-L25);
  [installer/release.sh L126–136, ARM64 selection](https://github.com/git-for-windows/build-extra/blob/60940ea2e4a8b6cd9a443af8517d00e7e429dd95/installer/release.sh#L126-L136);
  [L190–199, wrapper copies](https://github.com/git-for-windows/build-extra/blob/60940ea2e4a8b6cd9a443af8517d00e7e429dd95/installer/release.sh#L190-L199);
  [make-file-list.sh L20–27, aarch64 prefix](https://github.com/git-for-windows/build-extra/blob/60940ea2e4a8b6cd9a443af8517d00e7e429dd95/make-file-list.sh#L20-L27).
  PKGBUILD and build-extra commits selected via public commits API with
  `until=2026-10-22T19:10:21Z`; these are source context, not a binary attestation.
- **S4 — wrapper delegation:**
  [compat-bash.rc L1–4](https://github.com/git-for-windows/MINGW-packages/blob/743878777844a6e74ce8af749daa3384bfaeed30/mingw-w64-git/compat-bash.rc#L1-L4);
  [mingw-w64-git.mak L3–29, common launcher build](https://github.com/git-for-windows/MINGW-packages/blob/743878777844a6e74ce8af749daa3384bfaeed30/mingw-w64-git/mingw-w64-git.mak#L3-L29);
  [git-wrapper.c L675–689, resource dispatch first](https://github.com/git-for-windows/MINGW-packages/blob/6c637aa43ac0d9bb9033475ebbcd709261e93800/mingw-w64-git/git-wrapper.c#L675-L689);
  [L782–813, Git target and separate BusyBox fallback](https://github.com/git-for-windows/MINGW-packages/blob/6c637aa43ac0d9bb9033475ebbcd709261e93800/mingw-w64-git/git-wrapper.c#L782-L813);
  [L870–902, process creation](https://github.com/git-for-windows/MINGW-packages/blob/6c637aa43ac0d9bb9033475ebbcd709261e93800/mingw-w64-git/git-wrapper.c#L870-L902).
  Wrapper commit is the last change to that path before release publication.
- **S5 — native Git dispatch:**
  [git.c L660–669, helper builtin registration](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git.c#L660-L669);
  [L794–825, dashed external dispatch](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git.c#L794-L825);
  [compat/mingw.c L1873–1906, shebang parser](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/compat/mingw.c#L1873-L1906);
  [L2437–2470, interpreter lookup/spawn](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/compat/mingw.c#L2437-L2470).
- **S6 — shell script and foreach:** [git-submodule.sh L1–30](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git-submodule.sh#L1-L30);
  [L155–190, foreach implementation](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git-submodule.sh#L155-L190).
- **S7 — shell setup queries:**
  [git-sh-setup.sh L44–47](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git-sh-setup.sh#L44-L47);
  [L170–189](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git-sh-setup.sh#L170-L189);
  [L338–357](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/git-sh-setup.sh#L338-L357).
- **S8 — native foreach implementation:**
  [builtin/submodule--helper.c L350–365, callback shell request](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/builtin/submodule--helper.c#L350-L365);
  [L436–471, module-list traversal](https://github.com/git-for-windows/git/blob/0e9926caea36270e3e9067b5ac512ac0335a004a/builtin/submodule--helper.c#L436-L471).
- **S9 — checkout auth cleanup:**
  [git-auth-helper.ts L76–83](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-auth-helper.ts#L76-L83);
  [L233–236](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-auth-helper.ts#L233-L236);
  [L460–491](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-auth-helper.ts#L460-L491);
  [L535–541](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-auth-helper.ts#L535-L541).
- **S10 — checkout command construction:**
  [git-command-manager.ts L348–360](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-command-manager.ts#L348-L360);
  [L435–445](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/src/git-command-manager.ts#L435-L445).

## Dated upstream discussion records (not immutable code)

Issue/comment IDs provide stable attribution; their text/status can be edited.
Statuses below were observed on the access date and are not release promises.

- **S11:** [msys2/MSYS2-packages#3834](https://github.com/msys2/MSYS2-packages/issues/3834),
  open; [runtime prerequisite comment](https://github.com/msys2/MSYS2-packages/issues/3834#issuecomment-1584837824).
- **S12:** [git-for-windows/git#5292, original maintainer explanation](https://github.com/git-for-windows/git/issues/5292#issuecomment-2510738434);
  [2026 closure/runtime-roadmap comment](https://github.com/git-for-windows/git/issues/5292#issuecomment-4648108074).
  Issue closed `2026-06-08T10:51:24Z`. Historical Windows 10 compatibility
  discussion is not a diagnosis of Windows 11 startup performance.
- **S13:** [msys2/MSYS2-packages#4583](https://github.com/msys2/MSYS2-packages/pull/4583),
  closed 2024-11-13; [msys2/MSYS2-packages#4916](https://github.com/msys2/MSYS2-packages/pull/4916),
  closed 2024-09-24; [msys2/MSYS2-packages#5000](https://github.com/msys2/MSYS2-packages/pull/5000),
  closed 2024-11-11. These describe hangs/crashes, not a proven fix here.
- **S14:** [Microsoft IsWow64Process2 reference, Parameters/Return value](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2).
  Live authoritative documentation, not an immutable source snapshot.
  Only its public API contract is used; no private authoring-system links or
  metadata are reproduced.

## Method and verification scope

Public GitHub REST metadata/source via `gh api`, public raw GitHub source and
Microsoft/MSYS2 documentation were consulted. A general web-search attempt
failed; specific public GitHub searches and direct primary-source retrieval
succeeded. Search absence was not treated as proof of absence.

This documentation-only change requires no build. Validate commit scope and
whitespace with Git. No independent installed-binary or dynamic execution
validation is claimed.
