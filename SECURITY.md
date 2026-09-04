# Security Policy

## Sensitive local data

This repository is source-only. Never commit or attach collector authentication or private business data, including:

- `output/auth/` and all Playwright storage states
- Chromium persistent profiles
- cookies, tokens, runtime-context snapshots, login signals/status/control files
- `.venv/`, runtime diagnostics, logs, baselines, generated Dashboard data
- `publisher.local.json` or private Git remotes

The canonical public release is produced by `PREPARE_RELEASE.ps1`, which builds an explicit-allowlist staging tree and generates `MANIFEST_SHA256.txt` from that staging tree.

## Authentication boundary

Collector authentication must be created in the local Playwright Chromium launched by this project. A remote/Cloud Browser session is not an authentication source for the local collector.

UgPhone's persistent profile is protected by a cross-process profile lock shared by login, login preflight, and the canonical `run.py` collector entrypoint. The lock must never be bypassed by deleting Chromium lock files while a process is active.

## Reporting

If you find a credential exposure, unsafe process-control path, release-packaging leak, or authentication-verification bypass, do not publish secrets in an issue. Remove/rotate exposed credentials first, then report the defect with sanitized reproduction details.
