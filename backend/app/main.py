from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

from app.routes.files import router as files_router
from app.services import storage

app = FastAPI(
    title="CloudVault API",
    description="Local file storage API for the CloudVault project.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(files_router)


@app.get("/")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "storage": storage.backend_label()}
