"""
JWT — Todo lo que necesitas saber en un archivo:

1. El usuario hace login con email + password
2. El backend verifica la contraseña y crea un TOKEN (string firmado)
3. El token viaja en cada request siguiente en el header: Authorization: Bearer <token>
4. El backend verifica la firma del token sin consultar la BD
5. Si el token es válido, se extrae el user_id y se procesa el request

El token tiene 3 partes separadas por puntos:
  HEADER.PAYLOAD.SIGNATURE
  - Header: algoritmo usado
  - Payload: datos guardados (user_id, expiración) → NO guardes contraseñas aquí
  - Signature: firma que garantiza que nadie lo alteró
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt                              # PyJWT
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import get_settings

settings = get_settings()

# ── Hashing de contraseñas ────────────────────────────────────────────────────
# bcrypt convierte "mi_password" → "$2b$12$xyz..." (irreversible)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Convierte contraseña en texto a hash seguro para guardar en BD."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara contraseña ingresada con el hash guardado. Retorna True si coincide."""
    return pwd_context.verify(plain_password, hashed_password)


# ── Creación de tokens JWT ────────────────────────────────────────────────────
def create_access_token(user_id: str, extra_data: Optional[dict] = None) -> str:
    """
    Crea un token JWT con el user_id adentro.

    El token expira en JWT_EXPIRE_MINUTES (default 24h).
    Nadie puede modificar el token sin invalidar la firma.
    """
    payload = {
        "sub": user_id,                                          # 'sub' = subject (estándar JWT)
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
        "iat": datetime.now(timezone.utc),                       # 'iat' = issued at
    }
    if extra_data:
        payload.update(extra_data)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── Verificación de tokens ────────────────────────────────────────────────────
def decode_token(token: str) -> dict:
    """
    Decodifica y verifica un token JWT.
    Lanza excepción si el token es inválido o expiró.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Dependencia de FastAPI ────────────────────────────────────────────────────
# Esta función se inyecta en cualquier endpoint que requiera autenticación
# Uso: async def mi_endpoint(user_id: str = Depends(get_current_user_id))

bearer_scheme = HTTPBearer()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """
    Extrae y valida el token del header Authorization.
    Retorna el user_id si el token es válido.

    El cliente debe enviar: Authorization: Bearer <token>
    """
    payload = decode_token(credentials.credentials)
    user_id: str = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene user_id",
        )
    return user_id


# ── Dependencias de contexto de negocio ──────────────────────────────────────
#
# Estas funciones se inyectan en endpoints que necesitan saber:
#   - quién es el usuario  (user_id)
#   - a qué negocio accede (business_id desde header X-Business-ID)
#   - qué rol tiene en ese negocio
#
# Uso en un endpoint:
#   async def mi_endpoint(ctx: BusinessContext = Depends(require_member)):
#       ctx.user_id, ctx.business_id, ctx.role
#       ctx.is_owner  → True si es dueño
#
# El frontend envía siempre:
#   Authorization: Bearer <token>
#   X-Business-ID: <uuid-del-negocio>

from fastapi import Header
from app.db.supabase_client import get_supabase
from app.schemas.business import BusinessContext


def _get_member_context(user_id: str, business_id: str) -> BusinessContext:
    """Valida que el usuario pertenece al negocio y retorna su contexto."""
    db = get_supabase()

    result = (
        db.table("business_members")
        .select("role, is_active")
        .eq("user_id", user_id)
        .eq("business_id", business_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este negocio.",
        )

    member = result.data[0]

    if not member["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu acceso a este negocio fue desactivado.",
        )

    return BusinessContext(
        user_id=user_id,
        business_id=business_id,
        role=member["role"],
    )


def require_member(
    x_business_id: str = Header(..., alias="X-Business-ID",
                                 description="UUID del negocio activo"),
    user_id: str = Depends(get_current_user_id),
) -> BusinessContext:
    """
    Dependencia base: cualquier miembro del negocio (dueño o empleado).
    Usar en endpoints de registro de ventas, gastos, inventario.
    """
    return _get_member_context(user_id, x_business_id)


def require_owner(
    ctx: BusinessContext = Depends(require_member),
) -> BusinessContext:
    """
    Dependencia estricta: solo el dueño puede acceder.
    Usar en reportes, gestión de personal, configuración del negocio.
    """
    if not ctx.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el dueño del negocio puede realizar esta acción.",
        )
    return ctx
