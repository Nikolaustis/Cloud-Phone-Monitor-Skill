# Deployment Data Guide

The Git repository is source-only. Runtime data should be backed up separately and never committed to the source repository.

## 1. Fresh deployment — no historical continuity required

No collected business data needs to be transferred.

Install dependencies, then log in to each platform again and create a new baseline from the new environment. This is the safest option because authentication state and browser profiles are environment-sensitive.

## 2. Continue monitoring from the current state — minimum runtime data

Carry these separately from Git:

- `output/latest/`
  - especially `baseline_products_updated.xlsx`
  - current `products.csv` / `products.xlsx`
  - current run metadata used by monitoring and Dashboard generation
- `baselines/products_baseline.xlsx` if the installation still relies on the original baseline

This preserves current comparison continuity but does not preserve the complete historical trend if older run directories are omitted.

## 3. Preserve the complete Dashboard price history

In addition to the minimum runtime data, carry all complete historical run directories:

- `output/cloud_phone_monitor_*/`

`rebuild_dashboard_history.py` reconstructs trend history from these run directories. If they are not transferred, the old historical curves cannot be recreated from source code alone.

Generated Dashboard files do not need to be transferred because they can be rebuilt:

- `dashboard/public/dashboard_data/`
- `dashboard/dist/dashboard_data/`
- `dashboard/dist/`

## 4. Authentication — transfer only if absolutely necessary

Authentication is sensitive and should preferably be recreated by logging in again on the target machine.

If preserving login state is essential, the relevant runtime files are under:

- `output/auth/vsphone_state.json`
- `output/auth/redfinger_state.json`
- `output/auth/ldcloud_state.json`
- `output/auth/ugphone_state.json`
- `output/auth/ugphone_runtime_context.json`
- `output/auth/ugphone_profile/`

These files may contain cookies, tokens, session state, or browser-profile data. Do not commit them to GitHub. UgPhone's persistent Chromium profile is particularly environment-dependent and may fail after migration; re-login is preferred.

## 5. Not required for migration

The following can be regenerated or reinstalled and normally should not be copied:

- `dashboard/node_modules/`
- `.venv/`, `venv/`
- `__pycache__/`
- `dashboard/dist/`
- generated Dashboard JSON
- logs
- temporary debug folders

## Recommended backup sets

### Source only
Use the Git repository.

### Minimal continuity backup
- `output/latest/`
- `baselines/` if used

### Full continuity backup
- `output/latest/`
- all `output/cloud_phone_monitor_*/` complete runs
- `baselines/` if used

### Optional sensitive authentication backup
- `output/auth/` stored separately in an encrypted/private location, never in Git
