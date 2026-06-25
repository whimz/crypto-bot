"""JWT login/me endpoints and a middleware that guards every other route."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from config import (
    AUTH_PASSWORD,
    AUTH_USERNAME,
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    JWT_SECRET_KEY,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Paths reachable without a token. Everything else is gated by AuthMiddleware below.
PUBLIC_PATHS = {"/auth/login", "/health", "/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}

_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
# AUTH_PASSWORD comes from .env as plaintext; hash it once at startup so verification
# never compares plaintext directly and stays constant-time.
_password_hash = _pwd_context.hash(AUTH_PASSWORD) if AUTH_PASSWORD else None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return username


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest) -> TokenResponse:
    valid = (
        _password_hash is not None
        and credentials.username == AUTH_USERNAME
        and _pwd_context.verify(credentials.password, _password_hash)
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenResponse(access_token=create_access_token(credentials.username))


@router.get("/me")
def me(request: Request) -> dict:
    # AuthMiddleware already validated the token and stashed the username before this runs.
    return {"username": request.state.username}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        token = auth_header.removeprefix("Bearer ")
        try:
            request.state.username = decode_access_token(token)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        return await call_next(request)
