import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from backend.core.config import settings
from backend.core.database import db_manager
from backend.api.auth import router as auth_router
from backend.api.posts import router as posts_router
from backend.api.media import router as media_router
from backend.api.social import router as social_router
from backend.api.inbox import router as inbox_router
from backend.api.premium import router as premium_router
from backend.api.streaks import router as streaks_router
from backend.api.admin import router as admin_router
from backend.api.profile import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize PostgreSQL schemas / connection pool
    await db_manager.init_tables()
    yield
    # Shutdown: Close connection pool
    await db_manager.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Dispatch AI Operations Platform - Unified Python Backend (PostgreSQL + Async SQLAlchemy 2.0)",
    lifespan=lifespan,
)

logger = logging.getLogger("dispatch.http")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    method = request.method
    path = request.url.path
    query = str(request.url.query)
    url_display = f"{path}?{query}" if query else path
    client_ip = request.client.host if request.client else "unknown"

    logger.info(f"➡️ [HTTP REQ] {method} {url_display} (Client: {client_ip})")

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        status_code = response.status_code

        log_fn = logger.info if status_code < 400 else logger.warning if status_code < 500 else logger.error
        log_fn(f"⬅️ [HTTP RES] {method} {url_display} -> Status {status_code} ({duration_ms:.1f}ms)")
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ [HTTP ERR] {method} {url_display} -> Exception: {exc} ({duration_ms:.1f}ms)", exc_info=True)
        raise exc


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routes under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(posts_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")
app.include_router(social_router, prefix="/api/v1")
app.include_router(inbox_router, prefix="/api/v1")
app.include_router(premium_router, prefix="/api/v1")
app.include_router(streaks_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")

# Mount Static Assets for Direct Media Uploads & Stream Serving
Path("static/uploads").mkdir(parents=True, exist_ok=True)


@app.get("/static/uploads/{filename}")
async def serve_static_upload(filename: str):
    file_path = Path("static/uploads") / filename
    if file_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(file_path)
    from fastapi.responses import Response
    return Response(
        content=b"",
        status_code=404,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


# Universal OAuth callback aliases to prevent 404 "Not Found" errors across provider redirects
@app.get("/auth/callback")
@app.get("/api/v1/auth/callback")
async def alias_auth_callback(request: Request):
    query = str(request.url.query)
    target = f"/api/v1/social/callback?{query}" if query else "/api/v1/social/callback"
    return RedirectResponse(url=target, status_code=307)


@app.get("/social/callback/{platform}")
async def alias_social_callback_platform(platform: str, request: Request):
    query = str(request.url.query)
    target = f"/api/v1/social/callback/{platform}?{query}" if query else f"/api/v1/social/callback/{platform}"
    return RedirectResponse(url=target, status_code=307)


@app.get("/")
async def root_endpoint(request: Request):
    query = str(request.url.query)
    # If OAuth provider redirects to root with code and state, forward to callback handler
    if "code=" in query and "state=" in query:
        return RedirectResponse(url=f"/api/v1/social/callback?{query}", status_code=307)
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "database": "PostgreSQL (Async SQLAlchemy 2.0)",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "database": "PostgreSQL (Async SQLAlchemy 2.0)",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


def main():
    import uvicorn

    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)


if __name__ == "__main__":
    main()
