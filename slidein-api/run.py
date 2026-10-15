"""Development entry point: `python run.py`."""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "slidein_api.api.app:app",
        host=os.getenv("SLIDEIN_HOST", "127.0.0.1"),
        port=int(os.getenv("SLIDEIN_PORT", "8100")),
        reload=os.getenv("SLIDEIN_RELOAD", "1") == "1",
        log_level=os.getenv("SLIDEIN_LOG_LEVEL", "info"),
    )
