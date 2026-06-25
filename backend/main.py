"""Process entrypoint: `python -m backend.main` serves backend.api (FastAPI) via uvicorn;
the API's lifespan hook starts/stops backend.scheduler's trading loop.
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    import uvicorn

    from backend import api

    uvicorn.run(api.app, host="0.0.0.0", port=8000)
