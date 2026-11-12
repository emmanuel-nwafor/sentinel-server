import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.core.config import settings
from backend.models import Base  # Ensures all ORM models register on Base.metadata

logger = logging.getLogger(__name__)

# Create Async Engine for PostgreSQL
engine = create_async_engine(
    settings.DATABASE_URL,
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
