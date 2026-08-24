# Cloud Phone Monitor Skill

Source-only repository for the Cloud Phone Monitor collection and Dashboard system.

## Included

- `cloud_phone_monitor/` — Python collectors and data-processing code
- `dashboard/src/` — React/Vite Dashboard source
- `tests/` — unit/regression tests
- `run.py` — collector entry point
- `rebuild_dashboard_history.py` — Dashboard history rebuild entry point
- `requirements.txt` — Python dependencies
- `dashboard/package.json` / `package-lock.json` — frontend dependencies

## Intentionally excluded

This repository contains no production collection data or authentication state. The following are runtime-only and are ignored by Git:

- `output/`
- `logs/`
- `baselines/`
- `dashboard/public/dashboard_data/`
- `dashboard/dist/`
- `dashboard/node_modules/`
- browser profiles, cookies, Playwright storage states, runtime-context files
- generated `.xlsx`, `.csv`, `.jsonl` and `.log` files

The fallback module `dashboard/src/data/mockData.js` contains empty placeholders only. Real Dashboard data must be generated locally.

## Fresh deployment

### Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

### Dashboard

```powershell
Set-Location dashboard
npm ci
npm run build
```

### Authentication

Authentication files are deliberately not included. Re-create platform login states in the target environment rather than committing credentials or browser profiles to Git.

### First collection

From the repository root:

```powershell
python run.py --headed
```

For an existing monitoring installation, restore the required runtime data described in `DEPLOYMENT_DATA_GUIDE.md` before rebuilding history.

## Rebuild Dashboard history

```powershell
python rebuild_dashboard_history.py
Set-Location dashboard
npm run build
```

Generated Dashboard JSON is written under `dashboard/public/dashboard_data/` and `dashboard/dist/dashboard_data/`; these paths are intentionally not tracked by this source repository.
