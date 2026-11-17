import logging
from typing import AsyncGenerator
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.core.config import settings
from backend.models import Base  # Ensures all ORM models register on Base.metadata

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """
    Ensure the connection string uses the asyncpg driver and clean query parameters.
    Handles Neon, Supabase, Railway, and AWS RDS query formats.
    """
    if not url:
        return url

    parsed = urlparse(url)
    scheme = parsed.scheme

    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    elif scheme == "sqlite":
        scheme = "sqlite+aiosqlite"

    query_params = parse_qs(parsed.query)
    # Remove asyncpg-incompatible parameters
    query_params.pop("channel_binding", None)
    if "sslmode" in query_params:
        query_params["ssl"] = query_params.pop("sslmode")

    new_query = urlencode(query_params, doseq=True)
    return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


DATABASE_URL = normalize_database_url(settings.DATABASE_URL)

# Create Async Engine for PostgreSQL
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    future=True,
    pool_pre_ping=True,
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class DatabaseSessionManager:
    """
    Senior OOP Database Lifecycle Manager.
    Manages connection pooling, table schemas, and session lifecycle.
    """

    def __init__(self):
        self.engine = engine
        self.session_maker = AsyncSessionLocal

    async def init_tables(self):
        """Create tables if they don't exist (helpful for local development)."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("[PostgreSQL] Tables initialized successfully.")
        except Exception as e:
            logger.warning(f"[PostgreSQL] Notice during table init: {e}")

    async def close(self):
        """Cleanly close connection pools."""
        if self.engine:
            await self.engine.dispose()
            logger.info("[PostgreSQL] Engine connection pool disposed.")


db_manager = DatabaseSessionManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for yielding transactional AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
