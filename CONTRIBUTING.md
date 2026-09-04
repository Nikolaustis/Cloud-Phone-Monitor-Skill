# Contributing

## Development rules

1. Keep runtime/private data outside the public source package.
2. Do not weaken authentication verification to make a failing login appear successful.
3. Do not add purchase/order/payment/subscription confirmation actions to collectors or the Dashboard.
4. Keep controller/helper protocol changes synchronized and covered by behavior tests.
5. Use the canonical `run.py` entrypoint so UgPhone persistent-profile locking is enforced.

## Before submitting changes

On Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1 -InstallDevDependencies
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_TESTS.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PREPARE_RELEASE.ps1
```

`PREPARE_RELEASE.ps1` is the publication boundary. It builds a clean allowlist-only staging directory, disables Python bytecode writes during release tooling, sanitizes the public deployment contract, validates the public tree, regenerates and re-validates the manifest transactionally, and creates the canonical release ZIP. The ZIP builder rejects any file outside the public allowlist plus the validated manifest.

Do not upload a developer working tree merely because `.gitignore` exists; the release staging policy is the authoritative public-file policy.
