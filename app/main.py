"""Safe Circles — FastAPI entrypoint.

Server-rendered, mobile-first pages (Jinja2) with a small service worker for
offline access to the facilitator toolkit. Open source under Apache 2.0.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import SESSION_COOKIE, current_account
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.deps import BASE_DIR, render
from app.routers import admin, attend, authr, data, lead, public, toolkit

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
settings = get_settings()



@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Safe Circles", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def attach_account(request: Request, call_next):
    """Resolve the signed-in account once per request so templates can use it."""
    request.state.account = None
    if request.cookies.get(SESSION_COOKIE):
        db = SessionLocal()
        try:
            request.state.account = current_account(request, db)
        finally:
            db.close()
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        return render(request, "login.html", next_url=str(request.url.path), status_code=401)
    return render(request, "error.html", status=exc.status_code, detail=exc.detail, status_code=exc.status_code)


app.include_router(public.router)
app.include_router(authr.router)
app.include_router(attend.router)
app.include_router(lead.router)
app.include_router(toolkit.router)
app.include_router(admin.router)
app.include_router(data.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True, "env": settings.env}
