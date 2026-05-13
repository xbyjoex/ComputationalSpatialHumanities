from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..auth import (
    create_access_token,
    create_refresh_token_value,
    hash_password,
    verify_password,
    _hash_token,
    CurrentUser,
)
from ..db import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, password_hash, is_active FROM auth.users WHERE email = %s",
                (body.email,),
            )
            row = await cur.fetchone()

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user_id = str(row["id"])
    access_token = create_access_token(user_id, body.email)
    refresh_token = create_refresh_token_value()

    expires = datetime.now(tz=timezone.utc) + timedelta(days=30)
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO auth.refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, _hash_token(refresh_token), expires),
            )
            await cur.execute(
                "UPDATE auth.users SET last_login = NOW() WHERE id = %s", (user_id,)
            )
        await conn.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str) -> TokenResponse:
    token_hash = _hash_token(refresh_token)
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT rt.id, rt.user_id, u.email
                FROM auth.refresh_tokens rt
                JOIN auth.users u ON u.id = rt.user_id
                WHERE rt.token_hash = %s
                  AND rt.expires_at > NOW()
                  AND rt.revoked = FALSE
                  AND u.is_active = TRUE
                """,
                (token_hash,),
            )
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    new_access = create_access_token(str(row["user_id"]), row["email"])
    new_refresh = create_refresh_token_value()
    new_expires = datetime.now(tz=timezone.utc) + timedelta(days=30)

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            # Rotate: revoke old, create new
            await cur.execute(
                "UPDATE auth.refresh_tokens SET revoked = TRUE WHERE id = %s", (row["id"],)
            )
            await cur.execute(
                "INSERT INTO auth.refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (str(row["user_id"]), _hash_token(new_refresh), new_expires),
            )
        await conn.commit()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(refresh_token: str, _user: CurrentUser) -> None:
    token_hash = _hash_token(refresh_token)
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE auth.refresh_tokens SET revoked = TRUE WHERE token_hash = %s",
                (token_hash,),
            )
        await conn.commit()


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "is_admin": user["is_admin"],
    }


MAX_USERS = 2


@router.post("/register", status_code=201)
async def register(body: RegisterRequest) -> dict:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS n FROM auth.users")
            count = (await cur.fetchone())["n"]
            if count >= MAX_USERS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Registrierung nicht möglich – maximale Nutzeranzahl erreicht.",
                )
            await cur.execute(
                "SELECT 1 FROM auth.users WHERE email = %s", (body.email,)
            )
            if await cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="E-Mail bereits registriert."
                )
            await cur.execute(
                "INSERT INTO auth.users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id",
                (body.email, hash_password(body.password), body.full_name),
            )
            new_id = (await cur.fetchone())["id"]
        await conn.commit()

    return {"id": str(new_id), "email": body.email}
