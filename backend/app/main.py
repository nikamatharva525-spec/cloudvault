
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

# Resolve backend/.env from this file, independently of the current shell directory.
BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)

AWS_REGION = os.getenv("AWS_REGION", "").strip()
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "").strip()
configured_backend = os.getenv("STORAGE_BACKEND", "").strip().lower()
STORAGE_BACKEND = configured_backend or "s3"

if STORAGE_BACKEND not in {"local", "s3", "github"}:
    raise RuntimeError(
        f"Unsupported STORAGE_BACKEND={configured_backend!r} in {ENV_FILE}. "
        "Use one of: local, s3, github."
    )

from app.routes.files import router as files_router  # noqa: E402
from app.security import (  # noqa: E402
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    has_authenticated_session,
    issue_session_token,
    is_valid_credentials,
    register_user,
    require_authenticated,
    validate_auth_configuration,
)
from app.services import storage  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_auth_configuration()
    if os.getenv("VERCEL") and not storage.using_s3():
        raise RuntimeError("Vercel deployments require STORAGE_BACKEND=s3 for durable storage.")
    yield


app = FastAPI(
    title="CloudVault API",
    description="Single-user file storage API.",
    version="1.0.0",
    lifespan=lifespan,
)

configured_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
allowed_origins = (
    [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if configured_origins
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
)


def validate_cors_origins(origins: list[str]) -> None:
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or (
                parsed.scheme == "http"
                and parsed.hostname not in {"localhost", "127.0.0.1"}
            )
        ):
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS must contain exact HTTPS origins; "
                "only localhost HTTP origins are permitted."
            )


validate_cors_origins(allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])


@auth_router.get("/status")
def auth_status(
    response: Response,
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    response.headers["Cache-Control"] = "no-store"
    return {
        "authenticated": has_authenticated_session(session),
        "registration_enabled": not bool(os.getenv("VERCEL")),
    }


@auth_router.post("/login")
def login(payload: LoginRequest):
    if not is_valid_credentials(payload.email, payload.password):
        return JSONResponse(
            status_code=401,
            content={"detail": "Email or password is incorrect."},
            headers={"Cache-Control": "no-store"},
        )
    response = JSONResponse(
        content={"authenticated": True},
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issue_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=bool(os.getenv("VERCEL")) or os.getenv("COOKIE_SECURE", "").lower() == "true",
        samesite="strict",
        path="/",
    )
    return response


@auth_router.post("/register")
def register(payload: RegisterRequest):
    if os.getenv("VERCEL"):
        return JSONResponse(
            status_code=409,
            content={"detail": "Registration is disabled in the deployed app. Configure the access email and password in Vercel environment variables."},
        )
    try:
        created = register_user(payload.email, payload.password)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"detail": str(error)})
    if not created:
        return JSONResponse(status_code=409, content={"detail": "An account is already registered."})
    response = JSONResponse(content={"registered": True}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issue_session_token(),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=bool(os.getenv("VERCEL")) or os.getenv("COOKIE_SECURE", "").lower() == "true",
        samesite="strict",
        path="/",
    )
    return response


@auth_router.post("/logout")
def logout():
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=bool(os.getenv("VERCEL")) or os.getenv("COOKIE_SECURE", "").lower() == "true",
        samesite="strict",
        path="/",
    )
    return response


app.include_router(auth_router)
app.include_router(files_router)


@app.get("/")
@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/storage/status", dependencies=[Depends(require_authenticated)])
def storage_status():
    return storage.storage_status()
