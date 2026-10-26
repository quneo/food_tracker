import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app import maintenance
from app.ai.jobs import worker
from app.api import (
    admin,
    analytics,
    assistant,
    auth,
    bot,
    meals,
    media,
    memory,
    notes,
    photo_lock,
    products,
    profile,
    progress,
    reminders,
)
from app.core.exceptions import DomainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
BACKGROUND = {"enabled": True}  # tests switch the workers off


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = []
    if BACKGROUND["enabled"]:
        tasks = [asyncio.create_task(worker.serve()), asyncio.create_task(maintenance.serve())]
    yield
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Food Tracker API", version="0.1.0", lifespan=lifespan)

for router in (
    auth.router,
    profile.router,
    meals.router,
    assistant.router,
    notes.router,
    products.router,
    progress.router,
    media.router,
    photo_lock.router,
    analytics.router,
    memory.router,
    reminders.router,
    admin.router,
    bot.router,
):
    app.include_router(router, prefix="/api")


@app.middleware("http")
async def guard(request: Request, call_next):
    # Cookies are SameSite and changes need JSON or our own uploads: refuse requests that
    # a browser marks as coming from another site.
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("sec-fetch-site") == "cross-site"
    ):
        return JSONResponse({"detail": "Запрос с другого сайта запрещен"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(DomainError)
async def domain_error(request: Request, error: DomainError):
    return JSONResponse({"detail": error.message, **error.extra}, status_code=error.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    fields = sorted({str(item["loc"][-1]) for item in error.errors() if item.get("loc")})
    return JSONResponse({"detail": "Проверьте введенные данные", "fields": fields}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, error: IntegrityError):
    return JSONResponse({"detail": "Запись конфликтует с другими данными"}, status_code=409)


@app.get("/api/health")
def health():
    return {"status": "ok"}
