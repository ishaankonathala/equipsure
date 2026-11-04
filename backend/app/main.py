from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin_rates,
    assistant,
    auth,
    claim_images,
    claim_list,
    claims,
    health,
    notifications,
    policies,
    purchases,
)
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="EquipSure API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=(
            r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
            if settings.app_env == "development"
            else None
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(assistant.router, prefix="/api/assistant")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(claims.router, prefix="/api/claims")
    app.include_router(claim_list.router, prefix="/api/claims")
    app.include_router(claim_images.router, prefix="/api/claims")
    app.include_router(notifications.router, prefix="/api/notifications")
    app.include_router(admin_rates.router, prefix="/api/admin/rates")
    app.include_router(purchases.router, prefix="/api/quotes")
    app.include_router(policies.router, prefix="/api/policies")
    return app


app = create_app()