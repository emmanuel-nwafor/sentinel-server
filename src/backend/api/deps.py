import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db_session
from backend.core.security import decode_access_token
from backend.models.user import UserModel
from backend.unit_of_work.base import IUnitOfWork
from backend.unit_of_work.sql_unit_of_work import SqlAlchemyUnitOfWork

security_scheme = HTTPBearer()


async def get_uow(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[IUnitOfWork, None]:
    """Dependency injection delivering a scoped Unit of Work per request."""
    uow = SqlAlchemyUnitOfWork(session)
    async with uow:
        yield uow


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    uow: IUnitOfWork = Depends(get_uow),
) -> UserModel:
    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token user identifier",
        )

    user = await uow.users.get_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account email is not verified",
        )

    return user
