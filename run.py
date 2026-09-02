"""EGX Decision Engine entry point.

Starts uvicorn serving app.main:app on the host/port from settings
(default http://127.0.0.1:8642).
"""
from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> None:
    """Run the web server (blocking)."""
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
