"""Run the single-process Cgent service."""

import uvicorn

from cgent.app import create_app
from cgent.config import Settings
from cgent.telemetry.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = Settings.from_env()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    main()
