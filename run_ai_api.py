from __future__ import annotations

import uvicorn

from ai_backend.config import Settings


if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run(
        "ai_backend.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
