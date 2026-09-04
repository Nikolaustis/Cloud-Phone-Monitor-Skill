# AI Deployment

GitHub Pages stays static. Provider secrets belong only on a separately deployed FastAPI service.

```text
GitHub Pages Dashboard
        │ POST /api/ai/*
        ▼
FastAPI AI service
        │
        ├── rate limit / CORS / timeout
        ├── deterministic pricing tools
        └── optional LLM provider secret
```

For a public demo, keep Evidence Mode as a fallback so the Dashboard remains useful if the AI backend is unavailable or its daily budget is exhausted.

The backend can read a local AI context (`AI_CONTEXT_DIR`) or a remotely published safe context (`AI_CONTEXT_BASE_URL`). It must never connect to the private local Playwright auth directory.

## Local demo deployment

`START_DEMO.ps1` is the supported zero-account demo path. It builds a temporary Dashboard tree, copies only the synthetic safe dataset, regenerates AI context, optionally starts the FastAPI evidence backend and starts Vite. This keeps demo deployment separate from real collector/runtime data.

## Local configuration file

`run_ai_api.py` and `ai_backend.config.Settings` read the private root-level `ai.env` file automatically. Create it from `ai.env.example`; process environment variables override file values. `AI_HOST` and `AI_PORT` from `ai.env` are also honored by `run_ai_api.py`.

The public release rejects `ai.env`, provider keys and other obvious tracked credential material.
