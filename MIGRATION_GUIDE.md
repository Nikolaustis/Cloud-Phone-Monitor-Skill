# Migration Guide

This project separates **public reproducible source** from **private machine state**. A new computer should restore them through different paths.

## 1. Public source

Clone the validated public repository, then rebuild the runtime rather than copying `.venv/`:

```powershell
git clone <YOUR_REPOSITORY_URL>
cd Cloud-Phone-Pricing-Monitor
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap
```

The recommended baseline is Python 3.12.x, Node.js 22.x and Playwright 1.62.0. Python 3.13/3.14 and Node 24 are also supported compatibility runtimes. `VERIFY_V2.ps1 -Bootstrap` creates the project-local `.venv` using an available supported Python and installs the matching Playwright Chromium.

## 2. Private data that may be backed up separately

The following paths are intentionally excluded from the public repository:

```text
output/
baselines/
publisher.local.json
ai.env
```

Before changing computers, copy the business data you actually need to encrypted/private storage. Do **not** attach that archive to a public GitHub Release.

Recommended migration priority:

1. historical output needed for trend reconstruction;
2. private baseline files;
3. `publisher.local.json` if you want to preserve local publishing destinations;
4. `ai.env` if it contains a backend provider configuration.

## 3. Authentication state

Authentication material under `output/auth/` can contain cookies, storage state and a persistent Chromium profile. Treat it as a credential, not as source code.

For a new computer, the preferred path is to **re-authenticate locally** rather than depending on a copied browser profile:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Start
# Sign in in the local Playwright Chromium window.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Complete
```

Repeat the supported login flow for other platforms as required. If you choose to privately copy old authentication state, keep it encrypted and expect re-login to still be necessary because browser/profile state is machine-sensitive.

## 4. AI configuration

Copy `ai.env.example` to the private local file `ai.env`:

```powershell
Copy-Item .\ai.env.example .\ai.env
notepad .\ai.env
```

`ai_backend.config.Settings` automatically reads `ai.env` when present. Process environment variables take precedence. `ai.env` is ignored by Git and rejected by the public release policy.

## 5. Scheduler and deployment

Scheduled tasks and local deployment paths are machine state and are not restored by `git clone`. After source/runtime verification:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deployment\windows\install_deployment.ps1
```

Then recreate or verify the Windows scheduled task using the project scripts and your local paths.

## 6. Final migration acceptance

On the new computer, do not consider the migration complete until:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap
```

returns:

```text
RELEASE_READY=True
```

For real collection, separately verify local login and at least one live collector run. Public CI and synthetic demo validation intentionally do not depend on private platform credentials.

After re-authenticating on the new computer, a maintainer can run `VERIFY_REAL_COLLECTORS.ps1` to verify the four-platform live path end to end. This check is separate from the public reproducibility gate because it requires private credentials.
