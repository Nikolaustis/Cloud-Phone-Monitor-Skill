# Security Policy

## Sensitive local data

Never commit or publish:

- `output/auth/`, Playwright storage states and Chromium profiles;
- cookies, tokens, runtime context, login signals/status/control files;
- `.venv/`, logs, private baselines and local publisher configuration;
- backend `.env` files or AI provider credentials;
- private Git remotes or unsanitized diagnostics.

The canonical public release is produced by `PREPARE_RELEASE.ps1` using an explicit allowlist and sanitized deployment contract.

## Authentication boundary

Collector authentication must be created in the local Playwright Chromium launched by this project. Remote/Cloud Browser sessions are not a source for local collector state. UgPhone persistent profile access is guarded by the shared cross-process profile lock.

## AI boundary

The AI service is a read-only consumer of safe semantic context. Its tool registry must not expose collector execution, login mutation, baseline initialization, file-system mutation, purchase or subscription actions.

Provider credentials are backend-only. Do not place them in `VITE_*`, JavaScript bundles, static Dashboard data, demo data, evidence payloads or logs. Public GitHub Pages defaults to key-free Evidence Mode.

Deterministic tools own numerical pricing calculations. Treat evidence provenance and correct abstention as security/integrity properties: a fluent unsupported answer is a defect.

## Reporting

If you find a credential exposure, unsafe process-control path, release leak, auth-verification bypass, provider-secret exposure or evidence-grounding bypass, do not publish secrets in an issue. Rotate/remove exposed credentials first and report sanitized reproduction details.

## Git index is validated, not only the working tree

Public CI validates `git ls-files` against the explicit public allowlist and conservative secret patterns. This closes the case where an ignored runtime path had already been committed before `.gitignore` was added.

`ai.env` is treated as a private credential/configuration file and must never be committed. Use `ai.env.example` as the public template.

## Destructive demo-path guard

`tools/prepare_demo_runtime.py` refuses to recursively delete the repository, a repository ancestor, arbitrary source subdirectories, `output/auth`, or arbitrary non-temporary external paths. Only controlled demo runtime roots or OS/CI temporary directories are accepted.
