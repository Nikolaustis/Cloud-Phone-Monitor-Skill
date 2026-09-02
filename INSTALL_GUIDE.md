# installation and GitHub upload

## 1. Extract

Extract the ZIP to any temporary directory. Do not extract directly over `C:\Sites`.

## 2. Install

From the extracted root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

The installer:

- overlays source into `%USERPROFILE%\.codex\skills\cloud-phone-monitor-skill`;
- preserves `output/`, `baselines/`, `dashboard/node_modules/`, and `dashboard/dist/`;
- backs up the current `C:\Sites` publisher files;
- installs the Canonical publisher/validator/preflight files into `C:\Sites`;
- verifies the Skill/publisher compatibility contract.

Optional first-time dependency installation:

```powershell
.\INSTALL.ps1 -InstallDependencies
```

Optional Task Scheduler installation/update:

```powershell
.\INSTALL.ps1 -InstallDailyTask -DailyTime "10:00"
```

## 3. Upload the Skill source repository

Run from the same extracted directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PUBLISH_SOURCE_TO_GITHUB.ps1
```

This updates `Nikolaustis/Cloud-Phone-Monitor-Skill`, including `deployment/windows/`, and removes stale tracked `__pycache__`, `*.pyc`, runtime data, and generated Dashboard data from the source repository.

## 4. Publish an already-built Dashboard without recollecting

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Sites\resume_dashboard_publish.ps1
```

## 5. Normal daily run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Sites\update_cloud_phone_dashboard.ps1
```

The daily script refuses to run if the installed Skill and `C:\Sites` publisher compatibility contracts do not match, preventing the publisher from validating a different history-storage format than the Skill emits.
