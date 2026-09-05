import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.advanced_routes import router as advanced_router
from app.api.analytics_routes import router as analytics_router
from app.api.bulk_routes import router as bulk_router
from app.api.buyer_routes import router as buyer_router
from app.api.campaign_routes import router as campaign_router
from app.api.commerce_routes import router as commerce_router
from app.api.marketplace_routes import router as marketplace_router
from app.api.merchant_routes import router as merchant_router
from app.api.negotiation_routes import router as negotiation_router
from app.api.payment_routes import router as payment_router
from app.api.phase9_routes import router as phase9_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.campaign_scheduler import campaign_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    task = None
    if settings.app_env != "test":
        task = asyncio.create_task(campaign_scheduler(settings))
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="SentinelPay API", version="4.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request.state.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.getLogger(__name__).exception(
        "request failed correlation_id=%s", request.state.correlation_id
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "correlation_id": request.state.correlation_id},
    )


app.include_router(router)
app.include_router(merchant_router)
app.include_router(buyer_router)
app.include_router(commerce_router)
app.include_router(payment_router)
app.include_router(negotiation_router)
app.include_router(campaign_router)
app.include_router(analytics_router)
app.include_router(phase9_router)
app.include_router(advanced_router)
app.include_router(bulk_router)
app.include_router(marketplace_router)
