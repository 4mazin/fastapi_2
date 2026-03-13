import os
import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend, BearerTransport, JWTStrategy
)

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from app.db import User, get_user_db


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
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)  # 1 hour

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
    return JWTStrategy(secret=SECRET, lifetime_seconds=7200)  # 2 hours

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

