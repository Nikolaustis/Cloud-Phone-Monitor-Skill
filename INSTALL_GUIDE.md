# Installation Guide — Cloud Phone Pricing Intelligence Skill

## 1. Requirements

- Windows 10/11 for the canonical local collector/login workflow.
- CPython 3.12, 3.13 or 3.14 available as a bootstrap interpreter; the installed Skill runtime is `.venv\Scripts\python.exe`. Python 3.12 is recommended, not mandatory.
- Node.js 22.x or 24.x with npm when building the React Dashboard.
- Git only when using Git-based deployment/publishing.

System Google Chrome is not required. The runtime installer installs the Playwright Chromium build matched to the pinned Python Playwright package.

## 2. Base installation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1
```

New machine / create the canonical `.venv` and Playwright Chromium:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies
```

Install Dashboard npm dependencies as well:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies -InstallDashboardDependencies
```

## 3. Optional AI backend dependencies

The public Dashboard does not require an LLM backend. Evidence Mode works from static `dashboard_data/ai` files.

To install FastAPI/uvicorn for the optional AI service:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_ai_dependencies_windows.ps1
```

or during installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies -InstallAIDependencies
```

AI dependencies are installed into the same canonical Skill `.venv`; the installer does not create a second Python environment.

## 4. Collector login

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone
```

Agent two-stage flow:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Start
# complete login in LOCAL Chromium
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\LOGIN.ps1 UgPhone -Complete
```

ChatGPT Work / Cloud Browser authentication is isolated and must not be used as collector state.

## 5. Collection and AI semantic context

```powershell
.\.venv\Scripts\python.exe .\run.py
.\.venv\Scripts\python.exe -B .\build_ai_context.py
```

The AI context is written under `dashboard/public/dashboard_data/ai/` and contains only safe, derived Dashboard data.

## 6. Dashboard and optional AI API

```powershell
cd dashboard
npm ci
npm run dev
```

Optional backend:

```powershell
.\.venv\Scripts\python.exe -B .\run_ai_api.py
```

Provider configuration is backend-only. Copy values from `ai.env.example` into local environment configuration; never expose `AI_LLM_API_KEY` through Vite variables.

## 7. Tests

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_TESTS.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\RUN_AI_TESTS.ps1
```

## 8. Public release

After overlaying changes into the complete repository, regenerate the canonical release contract:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PREPARE_RELEASE.ps1
```

Do not upload a developer working tree containing `.venv`, auth state, private baselines, runtime output, provider keys or generated private diagnostics.

## v2 reproducibility requirements

The recommended baseline is **Python 3.12.x + Node.js 22.x + Playwright 1.62.0**. Supported compatibility runtimes are **Python 3.12-3.14** and **Node.js 22 or 24**; the bootstrap uses an already-active supported Python instead of forcing a downgrade.

After installing any supported Python 3.12-3.14 and Node.js 22 or 24, the preferred clean-machine command is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap
```

If the machine already has Python 3.13 or 3.14, it may be used directly. The release gate still requires the pinned dependencies, tests and Chromium launch to pass. Use `-PythonVersion 3.12|3.13|3.14` on the dependency installer when an exact interpreter is required for reproducibility testing.

Optional AI provider configuration can be placed in the local `ai.env` file copied from `ai.env.example`; it is loaded automatically and must not be committed.
