"""
Endpoints IoT — AbastOS

Ruta pública (ESP32 sin JWT):
  POST /api/v1/iot/reading
  Autenticación: api_key en el body JSON

Rutas protegidas (dueño con JWT):
  GET  /api/v1/iot/status          → estado actual del dispositivo
  GET  /api/v1/iot/history         → últimas 60 lecturas para la gráfica
  GET  /api/v1/iot/alerts          → historial de alertas
  POST /api/v1/iot/alerts/{id}/ack → reconocer una alerta
  GET  /api/v1/iot/config          → configuración de umbrales
  PATCH /api/v1/iot/config         → actualizar umbrales y correo
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional

from app.schemas.iot import (
    SensorReading, SensorReadingResponse,
    SensorReadingOut, IotStatus, IotAlert,
    IotConfigOut, IotConfigUpdate,
)
from app.core.config import get_settings
from app.core.security import require_owner, BusinessContext
from app.services import iot_service

router = APIRouter(prefix="/iot", tags=["IoT / Sensores"])
settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINT PÚBLICO — recibe lecturas del ESP32
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/reading", response_model=SensorReadingResponse)
async def receive_reading(body: SensorReading):
    """
    El ESP32 llama a este endpoint cada 60 segundos.

    Autenticación: api_key en el body (no JWT).
    La api_key identifica tanto el dispositivo como el negocio.

    El ESP32 no necesita el header X-Business-ID porque la api_key
    ya está vinculada a un business_id en la tabla iot_config.
    """
    # Validar api_key y obtener business_id
    from app.db.supabase_client import get_supabase
    db = get_supabase()

    key_result = (
        db.table("iot_config")
        .select("business_id, device_id")
        .eq("api_key", body.api_key)
        .execute()
    )

    if not key_result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="api_key invalida. Verifica la configuracion del dispositivo.",
        )

    config = key_result.data[0]
    business_id = config["business_id"]

    result = iot_service.process_reading(body, business_id)

    return SensorReadingResponse(**result)


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS PROTEGIDOS — solo el dueño
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=Optional[IotStatus])
async def get_status(ctx: BusinessContext = Depends(require_owner)):
    """
    Estado actual del dispositivo: temperatura, humedad, LED, fan, online/offline.
    Refresca cada 30 segundos en el frontend.
    """
    return iot_service.get_current_status(ctx.business_id)


@router.get("/history", response_model=List[SensorReadingOut])
async def get_history(
    ctx: BusinessContext = Depends(require_owner),
    limit: int = Query(60, ge=1, le=300),
):
    """
    Historial de lecturas para la gráfica de temperatura/humedad.
    Por defecto devuelve las últimas 60 (= última hora si el ESP32 envía cada minuto).
    """
    return iot_service.get_history(ctx.business_id, limit)


@router.get("/alerts", response_model=List[IotAlert])
async def get_alerts(
    ctx: BusinessContext = Depends(require_owner),
    limit: int = Query(20, ge=1, le=100),
):
    """Historial de alertas generadas. Incluye si se envió correo y si fue reconocida."""
    return iot_service.get_alerts(ctx.business_id, limit)


@router.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(
    alert_id: str,
    ctx: BusinessContext = Depends(require_owner),
):
    """Marca una alerta como reconocida (vista por el dueño)."""
    iot_service.acknowledge_alert(alert_id, ctx.business_id)
    return {"detail": "Alerta reconocida."}


@router.get("/config", response_model=IotConfigOut)
async def get_config(ctx: BusinessContext = Depends(require_owner)):
    """Devuelve la configuración de umbrales y correo de alertas."""
    return iot_service.get_config(ctx.business_id)


@router.patch("/config", response_model=IotConfigOut)
async def update_config(
    body: IotConfigUpdate,
    ctx: BusinessContext = Depends(require_owner),
):
    """Actualiza los umbrales de temperatura/humedad y el correo de alertas."""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
    return iot_service.update_config(ctx.business_id, data)
