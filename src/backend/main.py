from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.core.database import db_manager
from backend.api.auth import router as auth_router
from backend.api.posts import router as posts_router
from backend.api.media import router as media_router
from backend.api.social import router as social_router
from backend.api.inbox import router as inbox_router
from backend.api.premium import router as premium_router
from backend.api.streaks import router as streaks_router


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
