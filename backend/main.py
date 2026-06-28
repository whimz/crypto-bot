"""Process entrypoint: run as `python main.py` from inside backend/ (Railway's root
directory is set to backend/, so imports across this package are root-relative, not
prefixed with `backend.`). Serves api.py (FastAPI) via uvicorn; the API's lifespan hook
starts/stops scheduler.py's trading loop.

Logging is configured in api.py, not here - Railway's actual start command runs
`uvicorn api:app` directly, bypassing this file entirely, so this stays a thin convenience
wrapper for local runs rather than the only place logging gets set up.
"""

from __future__ import annotations

if __name__ == "__main__":
    import uvicorn

    import api

    uvicorn.run(api.app, host="0.0.0.0", port=8000)
