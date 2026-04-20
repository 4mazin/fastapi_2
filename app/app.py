from logging import exception
from datetime import timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from app.schemas import PostCreate, UserRead, UserCreate, UserUpdate, RefreshRequest
from app.db import Post, UserRole, create_db_and_tables, get_async_session, User
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imageKit
from imagekitio.types import FileUploadParams
import shutil
import os
import uuid
import tempfile
from app.users import UserManager, fastapi_users, current_active_user, auth_backend, refresh_auth_backend, create_access_token,decode_token, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from app.users import (
    UserManager,
    fastapi_users,
    current_active_user,
    auth_backend,
    get_user_manager,
    get_jwt_strategy,
    get_refresh_jwt_strategy,
    get_current_user
)
from fastapi_users import exceptions

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# Allow CORS for testing
app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

@app.get("/users/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role
    }


@app.post("/auth/login")
async def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    user_manager=Depends(get_user_manager),
):
    user = await user_manager.authenticate(credentials)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token(
        {"id": str(user.id), "email": user.email}
    )

    refresh_token = create_access_token(
        {"id": str(user.id), "email": user.email},
        expires_delta=timedelta(days=7),
        refresh=True
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": str(user.id), "email": user.email}
    }

@app.post("/auth/refresh")
async def refresh_token(data: RefreshRequest):
    payload = decode_token(data.refresh_token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not payload.get("refresh"):
        raise HTTPException(status_code=401, detail="Not refresh token")

    new_access_token = create_access_token(
        user_data=payload["user"],
        refresh=False
    )

    return {"access_token": new_access_token}

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        contents = await file.read()  # read the entire file into memory
        upload_result = imageKit.files.upload(
            file=contents,  # bytes
            file_name=file.filename,
            folder="/backend-upload",
            tags=["fastapi-upload"],
            use_unique_file_name=True
        )

        # Create a new Post in the database
        post = Post(
            user_id=user.id,
            caption=caption,
            url=upload_result.url,
            file_type="video" if file.content_type.startswith("video/") else "image",
            file_name=upload_result.name
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)

        return post

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    finally:
        file.file.close()  # Ensure the file is closed

@app.get("/feed")
async def get_feed(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    # Get all posts ordered by newest first
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts = [row[0] for row in result.all()]

    # Get all users to map user_id -> email
    result = await session.execute(select(User))
    users = [row[0] for row in result.all()]
    user_dict = {str(u.id): u.email for u in users}

    posts_data =[]

    for post in posts:
        posts_data.append(
            {
                "id": str(post.id),
                "user_id" : str(post.user_id),
                "caption": post.caption,
                "url": post.url,
                "file_type": post.file_type,
                "file_name": post.file_name,
                "created_at": post.created_at.isoformat(),
                "Is Owner": post.user_id == user.id,
                "email": user_dict.get(str(post.user_id), "Unknown")
            }
        )
    
    return {"posts": posts_data}


@app.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        post_uuid = uuid.UUID(post_id)
        result = await session.execute(select(Post).where(Post.id == post_uuid))
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        if not (
            user.role == UserRole.ADMIN.value or
            post.user_id == user.id
        ):
            raise HTTPException(status_code=403, detail="Not authorized to delete this post")
        
        await session.delete(post)
        await session.commit()
        return {"detail": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")
