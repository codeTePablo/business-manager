"""
Servicio IoT — lógica de umbrales, alertas y persistencia.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from app.db.supabase_client import get_supabase
from app.schemas.iot import (
    SensorReading, SensorReadingOut, IotStatus,
    IotAlert, IotConfigOut,
)
from app.services import notification_service


# ── Umbrales por defecto (si no hay config en BD) ─────────────────────────────
DEFAULT_TEMP_WARNING  = 26.0    # °C — LED amarillo, fan ON
DEFAULT_TEMP_CRITICAL = 26.5    # °C — LED rojo, email
DEFAULT_HUMIDITY_WARN = 85.0   # % — advertencia humedad
DEFAULT_COOLDOWN_MIN  = 30     # minutos entre emails del mismo tipo
DEFAULT_ALERT_EMAIL   = 'jopsan63@gmail.com'   # sin email por defecto

# ══════════════════════════════════════════════════════════════════════════════
#  RECIBIR LECTURA DEL ESP32
# ══════════════════════════════════════════════════════════════════════════════

def process_reading(reading: SensorReading, business_id: str) -> dict:
    """
    1. Valida la api_key del dispositivo contra la configuración del negocio
    2. Persiste la lectura en sensor_readings
    3. Evalúa umbrales y crea alerta si es necesario
    4. Envía correo si la alerta es nueva y pasó el cooldown
    """
    db = get_supabase()

    # 1. Obtener config del negocio (umbrales y correo)
    config_result = (
        db.table("iot_config")
        .select("*")
        .eq("business_id", business_id)
        .execute()
    )
    config = config_result.data[0] if config_result.data else {}

    temp_warning  = float(config.get("temp_warning_c",       DEFAULT_TEMP_WARNING))
    temp_critical = float(config.get("temp_critical_c",      DEFAULT_TEMP_CRITICAL))
    hum_warning   = float(config.get("humidity_warning_pct", DEFAULT_HUMIDITY_WARN))
    cooldown_min  = int(config.get("alert_cooldown_minutes",  DEFAULT_COOLDOWN_MIN))
    alert_email   = config.get("alert_email")

    # 2. Persistir lectura
    reading_result = db.table("sensor_readings").insert({
        "business_id":   business_id,
        "device_id":     reading.device_id,
        "temperature_c": reading.temperature_c,
        "humidity_pct":  reading.humidity_pct,
        "fan_active":    reading.fan_active,
        "led_state":     reading.led_state,
    }).execute()

    saved = reading_result.data[0]
    alert_created = False

    # 3. Evaluar umbrales
    alert_type = None
    severity   = None
    message    = None

    temp = reading.temperature_c
    hum  = reading.humidity_pct

    if temp >= temp_critical:
        alert_type = "critical_temp"
        severity   = "critical"
        message    = (
            f"Temperatura CRITICA detectada: {temp:.1f}°C. "
            f"El umbral critico es {temp_critical}°C. "
            "Revisa la camara de refrigeracion inmediatamente."
        )
    elif temp >= temp_warning:
        alert_type = "high_temp"
        severity   = "warning"
        message    = (
            f"Temperatura elevada: {temp:.1f}°C. "
            f"El umbral de advertencia es {temp_warning}°C. "
            "El ventilador deberia estar activo."
        )
    elif hum is not None and hum >= hum_warning:
        alert_type = "high_humidity"
        severity   = "warning"
        message    = (
            f"Humedad elevada: {hum:.1f}%. "
            f"El umbral es {hum_warning}%. "
            "Puede causar condensacion en los productos."
        )

    # 4. Crear alerta y enviar correo si aplica
    if alert_type:
        # Verificar cooldown: ¿hubo una alerta del mismo tipo en los últimos N minutos?
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_min)).isoformat()
        recent = (
            db.table("iot_alerts")
            .select("id")
            .eq("business_id", business_id)
            .eq("device_id", reading.device_id)
            .eq("alert_type", alert_type)
            .gte("created_at", cutoff)
            .execute()
        )

        if not recent.data:
            # Crear alerta en BD
            email_sent = False
            if alert_email:
                # Obtener nombre del negocio
                biz = db.table("businesses").select("name").eq("id", business_id).execute()
                biz_name = biz.data[0]["name"] if biz.data else "Negocio"

                email_sent = notification_service.send_iot_alert(
                    to_email=alert_email,
                    business_name=biz_name,
                    device_id=reading.device_id,
                    alert_type=alert_type,
                    severity=severity,
                    temperature_c=temp,
                    humidity_pct=hum,
                    message=message,
                )

            db.table("iot_alerts").insert({
                "business_id":   business_id,
                "device_id":     reading.device_id,
                "alert_type":    alert_type,
                "severity":      severity,
                "temperature_c": temp,
                "humidity_pct":  hum,
                "message":       message,
                "email_sent":    email_sent,
                "email_sent_at": datetime.now(timezone.utc).isoformat() if email_sent else None,
            }).execute()

            alert_created = True

    return {
        "id":            saved["id"],
        "recorded_at":   saved["recorded_at"],
        "alert_created": alert_created,
        "command":       None,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CONSULTAS PARA EL DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def get_current_status(business_id: str) -> Optional[IotStatus]:
    """Retorna el estado actual del dispositivo (última lectura)."""
    db = get_supabase()

    result = (
        db.table("sensor_readings")
        .select("*")
        .eq("business_id", business_id)
        .order("recorded_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return None

    row = result.data[0]
    last_seen = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
    is_online = (datetime.now(timezone.utc) - last_seen).seconds < 180  # 3 minutos

    # Alertas sin reconocer
    pending = (
        db.table("iot_alerts")
        .select("id")
        .eq("business_id", business_id)
        .eq("acknowledged", False)
        .execute()
    )

    return IotStatus(
        device_id=row["device_id"],
        temperature_c=row["temperature_c"],
        humidity_pct=row.get("humidity_pct"),
        fan_active=row["fan_active"],
        led_state=row["led_state"],
        last_seen=last_seen,
        is_online=is_online,
        pending_alerts=len(pending.data),
    )


def get_history(business_id: str, limit: int = 60) -> list[SensorReadingOut]:
    """Últimas N lecturas para la gráfica del dashboard."""
    db = get_supabase()

    result = (
        db.table("sensor_readings")
        .select("*")
        .eq("business_id", business_id)
        .order("recorded_at", desc=True)
        .limit(limit)
        .execute()
    )

    return [
        SensorReadingOut(
            id=r["id"],
            device_id=r["device_id"],
            temperature_c=r["temperature_c"],
            humidity_pct=r.get("humidity_pct"),
            fan_active=r["fan_active"],
            led_state=r["led_state"],
            recorded_at=r["recorded_at"],
        )
        for r in reversed(result.data)   # cronológico ascendente para la gráfica
    ]


def get_alerts(business_id: str, limit: int = 20) -> list[IotAlert]:
    """Últimas alertas del negocio."""
    db = get_supabase()

    result = (
        db.table("iot_alerts")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return [IotAlert(**r) for r in result.data]


def acknowledge_alert(alert_id: str, business_id: str) -> bool:
    """Marca una alerta como reconocida."""
    db = get_supabase()
    db.table("iot_alerts").update({
        "acknowledged":    True,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", alert_id).eq("business_id", business_id).execute()
    return True


def get_config(business_id: str) -> IotConfigOut:
    """Devuelve la configuración de umbrales del negocio."""
    db = get_supabase()
    result = db.table("iot_config").select("*").eq("business_id", business_id).execute()
    if result.data:
        r = result.data[0]
        return IotConfigOut(
            device_id=r["device_id"],
            temp_warning_c=r["temp_warning_c"],
            temp_critical_c=r["temp_critical_c"],
            humidity_warning_pct=r["humidity_warning_pct"],
            alert_email=r.get("alert_email"),
            alert_cooldown_minutes=r["alert_cooldown_minutes"],
        )
    # Defaults si aún no se configuró
    return IotConfigOut(
        device_id="esp32-cold-room-01",
        temp_warning_c=DEFAULT_TEMP_WARNING,
        temp_critical_c=DEFAULT_TEMP_CRITICAL,
        humidity_warning_pct=DEFAULT_HUMIDITY_WARN,
        alert_email=None,
        alert_cooldown_minutes=DEFAULT_COOLDOWN_MIN,
    )


def update_config(business_id: str, data: dict) -> IotConfigOut:
    """Crea o actualiza la configuración de umbrales."""
    db = get_supabase()
    existing = db.table("iot_config").select("id").eq("business_id", business_id).execute()

    if existing.data:
        db.table("iot_config").update({**data, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("business_id", business_id).execute()
    else:
        db.table("iot_config").insert({"business_id": business_id, **data}).execute()

    return get_config(business_id)


def get_hourly_averages(business_id: str, hours: int = 24) -> list:
    """Promedio de temperatura y humedad por hora — últimas N horas."""
    db = get_supabase()

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    result = (
        db.table("sensor_readings")
        .select("temperature_c, humidity_pct, recorded_at")
        .eq("business_id", business_id)
        .gte("recorded_at", cutoff)
        .order("recorded_at")
        .execute()
    )

    if not result.data:
        return []

    # Agrupar por hora
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for row in result.data:
        hour = row["recorded_at"][:13]   # "2026-06-05T14"
        buckets[hour].append(row)

    averages = []
    for hour, readings in sorted(buckets.items()):
        temps = [r["temperature_c"] for r in readings]
        hums  = [r["humidity_pct"]  for r in readings if r["humidity_pct"] is not None]
        averages.append({
            "hour":           hour,
            "avg_temp_c":     round(sum(temps) / len(temps), 2),
            "min_temp_c":     round(min(temps), 2),
            "max_temp_c":     round(max(temps), 2),
            "avg_humidity":   round(sum(hums) / len(hums), 2) if hums else None,
            "reading_count":  len(readings),
        })

    return averages
