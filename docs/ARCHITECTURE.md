# Architecture

## Runtime layers

```text
LOGIN.ps1 / run.py
        |
        v
session + runtime guards
        |
        +-- dedicated .venv Python
        +-- session-bound login controller
        +-- UgPhone persistent-profile lock
        |
        v
Playwright browser contexts
        |
        v
platform scraper / auth verifier
        |
        v
output/ (private runtime data)
        |
        v
Dashboard export/build (generated data)
```

The repository separates source, local runtime state, and public release artifacts. Source code must not depend on the caller's working directory for authentication paths.

## Authentication authority

- **UgPhone:** persistent Chromium profile is the primary long-lived authority; Playwright storage state and runtime context are auxiliary artifacts.
- **VSPhone / Redfinger / LDCloud:** Playwright storage state is the primary persisted authentication artifact.
- Login success is fail-closed: navigation, cookie presence, or storage keys alone are insufficient.

## Concurrency

`cloud_phone_monitor.profile_lock` provides an atomic cross-process lock for the UgPhone persistent profile. The canonical login controller, login preflight, and `run.py` collector share that lock. A live owner with unverifiable identity is treated conservatively and is not killed or overwritten.

## Publication boundary

The developer working tree is not the release artifact. `tools/public_release_policy.py` defines an explicit public allowlist. `tools/build_release_staging.py` copies only approved paths into a new staging tree and sanitizes `deployment_contract.json` to its public contract keys before Manifest generation.
