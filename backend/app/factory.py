from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import ALL_BLUEPRINTS
from .database import init_db
from .services.plc_simulator import start_plc_background_writer


def create_app() -> FastAPI:
    app = FastAPI(title="Poultry ERP API")
    app.router.redirect_slashes = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_db()
    start_plc_background_writer(interval_seconds=5, lookback_minutes=60)

    for blueprint in ALL_BLUEPRINTS:
        app.include_router(blueprint.router)

    return app
