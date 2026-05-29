"""
AbastOS — Backend
Punto de entrada de la aplicación FastAPI.

Para correr en desarrollo:
    uvicorn app.main:app --reload

Documentación automática disponible en:
    http://localhost:8000/docs       ← Swagger UI (interactivo)
    http://localhost:8000/redoc      ← ReDoc
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.v1.router import api_router

settings = get_settings()

app = FastAPI(
    title="AbastOS API",
    description="Sistema de administración para comerciantes de la Central de Abastos",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Permite que el frontend (React en localhost:5173) llame al backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rutas ─────────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": "AbastOS", "version": "0.1.0"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
