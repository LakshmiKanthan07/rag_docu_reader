from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv() # Load variables into os.environ for LangSmith

from app.api.routers import auth, chats, documents, ask
from app.db.database import Base, engine
from app.core.config import settings

# Create tables (In production, use Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SaaS ChatGPT-like Document Q&A API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(chats.router, prefix=f"{settings.API_V1_STR}/chats", tags=["chats"])
app.include_router(documents.router, prefix=f"{settings.API_V1_STR}", tags=["documents"])
app.include_router(ask.router, prefix=f"{settings.API_V1_STR}", tags=["chat interaction"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Serve Frontend
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))
