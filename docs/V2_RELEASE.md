# v2 AI Release Line

## Beta

- Tag: `v2.0.0-beta.1`
- Release title: **Cloud Phone Pricing Intelligence Platform v2.0.0-beta.1 — AI Copilot**
- Mark as GitHub pre-release.

The beta introduces the `ai-context-v2` semantic layer, eight deterministic pricing tools, evidence IDs, Dashboard Evidence Mode, optional FastAPI/provider orchestration, Explain, What-if, synthetic demo data and the first AI benchmark suite.

## Stable target

- Tag: `v2.0.0`
- Release title: **Cloud Phone Pricing Intelligence Platform v2.0.0 — AI Copilot**

Promote to stable only after the full collector/Dashboard pipeline, GitHub Actions, public release contract and a safe real-data AI benchmark are all validated. Production AI metrics must not reuse the synthetic demo benchmark scores.

## Beta release gate

Before creating the GitHub pre-release, run on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap
```

The release candidate is locally ready only when the verifier emits `RELEASE_READY=True`. The public repository should then be populated from the validated allowlist staging tree, preferably through `PUBLISH_PUBLIC_SOURCE.ps1`, not by uploading the local working directory.

## Public-readiness hardening gates

Before tagging `v2.0.0-beta.1`, the source repository must pass the Git-tracked public-tree validator, supported Python 3.12-3.14 / Node 22 or 24 runtime checks, unique-process FastAPI network smoke test and canonical Manifest reproduction. `RELEASE_READY=True` is required from a non-skipped `VERIFY_V2.ps1 -Bootstrap` run on a clean Windows environment.

Real platform collection remains a separate maintainer acceptance step because public CI intentionally has no private platform credentials. Record login/reuse/collection failures explicitly rather than weakening the portable demo gate.
