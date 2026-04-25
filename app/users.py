import os
import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend, BearerTransport, JWTStrategy
)

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from app.db import User, UserRole, get_user_db


SECRET = os.getenv("JWT_SECRET_KEY")


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        print(f"User {user.id} forgot their password. Reset token: {token}")

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


# -----------------------
# Access token (short-lived)
# -----------------------
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)  

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# -----------------------
# Refresh token (longer-lived)
# -----------------------
refresh_bearer_transport = BearerTransport(tokenUrl="auth/jwt/refresh")

def get_refresh_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=100) 

refresh_auth_backend = AuthenticationBackend(
    name="jwt_refresh",
    transport=refresh_bearer_transport,
    get_strategy=get_refresh_jwt_strategy,
)


# -----------------------
# FastAPI Users instance
# -----------------------
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# Current active user dependency
current_active_user = fastapi_users.current_user(active=True)


from datetime import datetime, timedelta
import jwt
import logging

ACCESS_TOKEN_EXPIRE = 30  # 1 hour
REFRESH_TOKEN_EXPIRE = 3600 * 24 * 7  # 7 days


def create_access_token(user_data: dict, expires_delta=None, refresh: bool = False) -> str:
    if isinstance(expires_delta, timedelta):
        expire = datetime.utcnow() + expires_delta
    elif isinstance(expires_delta, int):
        expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    else:
        expire = datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_EXPIRE)

    payload = {
        "user": user_data,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "refresh": refresh
    }

    return jwt.encode(payload, SECRET, algorithm="HS256")


def create_refresh_token(user_data: dict) -> str:
    return create_access_token(
        user_data,
        expires_delta=REFRESH_TOKEN_EXPIRE,
        refresh=True
    )


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWTError as e:
        logging.exception(e)
        return None

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


import uuid
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import User, get_async_session
from app.users import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session)
):
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("refresh"):
        raise HTTPException(status_code=401, detail="Invalid token type")

    try:
        user_id = uuid.UUID(payload["user"]["id"])  # ✅ FIX HERE
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid user ID in token")

    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

# GET CURRENT USER ADMIN

async def get_current_admin(user: User = Depends(get_current_user)):
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admins only")
    return user