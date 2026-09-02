# deployment and data boundaries

## Version-controlled source

The GitHub source repository should contain application code, Dashboard source, tests, documentation, and `deployment/windows/`.

`deployment/windows/` is the canonical source for files installed into `C:\Sites`. Do not maintain a separate publisher implementation there.

## Local runtime data — do not upload

Keep these local/private:

```text
output/
output/auth/
output/.history_cache/
baselines/
logs/
dashboard/node_modules/
dashboard/dist/
dashboard/public/dashboard_data/
```

Authentication state, cookies, persistent UgPhone browser profiles, account information, raw run outputs, and private baseline workbooks must never be committed.

## GitHub Pages repository

The generated Dashboard site remains a separate repository:

```text
C:\Sites\Cloud-Phone-Dashboard-Site
https://github.com/Nikolaustis/Cloud-Phone-Price-Dashboard-Site.git
```

mirrors `dashboard/dist` into that repository's `docs/` directory and pushes only generated public Dashboard assets.

## Rebuilding a machine

1. Clone `Cloud-Phone-Monitor-Skill`.
2. Run `INSTALL.ps1 -InstallDependencies`.
3. Restore private `output/` history and `baselines/` from your own backup if continuity is required.
4. Re-create/restore authentication state locally; never retrieve it from GitHub.
5. Run `python rebuild_dashboard_history.py --incremental` and `npm run build`.
6. Install/update the daily task with `scripts/setup_daily_monitor_windows.ps1` if desired.
