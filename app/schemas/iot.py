from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ── Lo que el ESP32 envía en cada POST ───────────────────────────────────────
class SensorReading(BaseModel):
    """
    Payload que manda el ESP32 a POST /api/v1/iot/reading

    El ESP32 envía esto en el body como JSON:
    {
        "device_id": "esp32-cold-room-01",
        "temperature_c": 3.4,
        "humidity_pct": 76.2,
        "fan_active": false,
        "led_state": "green",
        "api_key": "TU_DEVICE_API_KEY"
    }
    """
    device_id:     str
    temperature_c: float
    humidity_pct:  Optional[float] = None
    fan_active:    bool = False
    led_state:     str  = "green"   # 'green' | 'yellow' | 'red'
    api_key:       str               # clave larga del dispositivo (no JWT de usuario)

    @field_validator("temperature_c")
    @classmethod
    def valid_temp(cls, v):
        if not -40 <= v <= 125:
            raise ValueError("Temperatura fuera de rango del sensor DHT22")
        return round(v, 2)

    @field_validator("led_state")
    @classmethod
    def valid_led(cls, v):
        if v not in ("green", "yellow", "red"):
            raise ValueError("led_state debe ser green, yellow o red")
        return v


# ── Respuesta al ESP32 ────────────────────────────────────────────────────────
class SensorReadingResponse(BaseModel):
    """
    Lo que el ESP32 recibe como respuesta.
    Puede usar 'command' para ajustar su comportamiento si quieres control remoto futuro.
    """
    id:            str
    recorded_at:   datetime
    alert_created: bool    = False   # True si se generó una alerta con este envío
    command:       Optional[str] = None  # "fan_on" | "fan_off" | None


# ── Para el dashboard del frontend ───────────────────────────────────────────
class SensorReadingOut(BaseModel):
    id:            str
    device_id:     str
    temperature_c: float
    humidity_pct:  Optional[float]
    fan_active:    bool
    led_state:     str
    recorded_at:   datetime


class IotStatus(BaseModel):
    """Estado actual del dispositivo (última lectura)."""
    device_id:        str
    temperature_c:    float
    humidity_pct:     Optional[float]
    fan_active:       bool
    led_state:        str
    last_seen:        datetime
    is_online:        bool       # True si la última lectura fue hace menos de 3 minutos
    pending_alerts:   int        # alertas no reconocidas


class IotAlert(BaseModel):
    id:             str
    device_id:      str
    alert_type:     str
    severity:       str
    temperature_c:  Optional[float]
    humidity_pct:   Optional[float]
    message:        str
    email_sent:     bool
    acknowledged:   bool
    created_at:     datetime


# ── Configuración de umbrales ─────────────────────────────────────────────────
class IotConfigUpdate(BaseModel):
    temp_warning_c:         Optional[float] = None
    temp_critical_c:        Optional[float] = None
    humidity_warning_pct:   Optional[float] = None
    alert_email:            Optional[str]   = None
    alert_cooldown_minutes: Optional[int]   = None


class IotConfigOut(BaseModel):
    device_id:              str
    temp_warning_c:         float
    temp_critical_c:        float
    humidity_warning_pct:   float
    alert_email:            Optional[str]
    alert_cooldown_minutes: int
