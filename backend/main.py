"""Process entrypoint: run as `python main.py` from inside backend/ (Railway's root
directory is set to backend/, so imports across this package are root-relative, not
prefixed with `backend.`). Serves api.py (FastAPI) via uvicorn; the API's lifespan hook
starts/stops scheduler.py's trading loop.
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if __name__ == "__main__":
    import uvicorn

    import api

    uvicorn.run(api.app, host="0.0.0.0", port=8000)
