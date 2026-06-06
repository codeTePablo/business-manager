"""
Servicio de notificaciones por correo usando Resend.
https://resend.com — gratis hasta 3,000 emails/mes.

Instalar: pip install resend
Configurar en .env: RESEND_API_KEY=re_xxxxxxxxxxxx
"""

from __future__ import annotations

import resend
from app.core.config import get_settings
from app.db.supabase_client import get_supabase


settings = get_settings()


def _get_client() -> None:
    """Configura la API key de Resend."""
    resend.api_key = settings.resend_api_key


def get_historical_stats(business_id: str) -> dict:
    """
    Obtiene estadísticas globales de TODO el historial del negocio.
    Calcula promedio, mínima, máxima de temperatura y promedio de humedad.
    """
    db = get_supabase()

    result = (
        db.table("sensor_readings")
        .select("temperature_c, humidity_pct")
        .eq("business_id", business_id)
        .execute()
    )

    if not result.data:
        return {}

    temps = [
        row["temperature_c"]
        for row in result.data
        if row.get("temperature_c") is not None
    ]

    hums = [
        row["humidity_pct"]
        for row in result.data
        if row.get("humidity_pct") is not None
    ]

    if not temps:
        return {}

    return {
        "avg_temp_c": round(sum(temps) / len(temps), 2),
        "min_temp_c": round(min(temps), 2),
        "max_temp_c": round(max(temps), 2),
        "avg_humidity": round(sum(hums) / len(hums), 2) if hums else None,
        "reading_count": len(result.data),
    }


def send_iot_alert(
    to_email: str,
    business_name: str,
    device_id: str,
    alert_type: str,
    severity: str,
    temperature_c: float,
    humidity_pct: float | None,
    message: str,
    avg_temp_c: float | None = None,
    avg_humidity: float | None = None,
    min_temp_c: float | None = None,
    max_temp_c: float | None = None,
    reading_count: int | None = None,
) -> bool:
    """
    Envía un correo de alerta de temperatura/humedad al dueño del negocio.
    Retorna True si el envío fue exitoso.
    """
    _get_client()

    severity_label = "CRITICA" if severity == "critical" else "ADVERTENCIA"
    color = "#b91c1c" if severity == "critical" else "#b45309"
    border = "#fecaca" if severity == "critical" else "#fde68a"
    bg = "#fef2f2" if severity == "critical" else "#fffbeb"

    humidity_row = (
        f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Humedad</td>
          <td style="padding:8px 12px;font-weight:600;">{humidity_pct:.1f}%</td>
        </tr>
        """
        if humidity_pct is not None
        else ""
    )

    historical_block = ""
    if avg_temp_c is not None and min_temp_c is not None and max_temp_c is not None:
        historical_block = f"""
        <tr>
          <td colspan="2" style="padding:12px 12px 4px;color:#6b7280;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;border-top:1px solid #e5e7eb;">
            Comportamiento histórico — Todo el historial
          </td>
        </tr>
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Temperatura promedio</td>
          <td style="padding:8px 12px;font-weight:600;">{avg_temp_c:.1f} °C</td>
        </tr>
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Mínima / Máxima</td>
          <td style="padding:8px 12px;font-weight:600;">{min_temp_c:.1f} °C / {max_temp_c:.1f} °C</td>
        </tr>
        """

        if avg_humidity is not None:
            historical_block += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Humedad promedio</td>
          <td style="padding:8px 12px;font-weight:600;">{avg_humidity:.1f}%</td>
        </tr>
            """

        if reading_count is not None:
            historical_block += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Lecturas analizadas</td>
          <td style="padding:8px 12px;font-weight:600;">{reading_count}</td>
        </tr>
            """

    html = f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,sans-serif;">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:8px;
              border:1px solid #e5e7eb;overflow:hidden;">

    <div style="background:{color};padding:24px 28px;">
      <p style="margin:0;color:#fff;font-size:11px;font-weight:700;
                letter-spacing:.1em;text-transform:uppercase;">AbastOS — Alerta IoT</p>
      <p style="margin:8px 0 0;color:rgba(255,255,255,.85);font-size:22px;font-weight:700;">
        Alerta {severity_label}
      </p>
    </div>

    <div style="padding:28px;">
      <div style="background:{bg};border:1px solid {border};border-radius:6px;
                  padding:16px 20px;margin-bottom:20px;">
        <p style="margin:0;font-size:14px;color:{color};">{message}</p>
      </div>

      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Negocio</td>
          <td style="padding:8px 12px;font-weight:600;">{business_name}</td>
        </tr>
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Dispositivo</td>
          <td style="padding:8px 12px;font-family:monospace;font-size:12px;">{device_id}</td>
        </tr>
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:8px 12px;color:#6b7280;">Temperatura</td>
          <td style="padding:8px 12px;font-weight:700;font-size:18px;color:{color};">
            {temperature_c:.1f} °C
          </td>
        </tr>
        {humidity_row}
        {historical_block}
        <tr>
          <td style="padding:8px 12px;color:#6b7280;">Tipo</td>
          <td style="padding:8px 12px;">{alert_type.replace("_", " ").title()}</td>
        </tr>
      </table>

      <p style="margin:20px 0 0;font-size:13px;color:#6b7280;line-height:1.6;">
        Revisa el estado de tu camara de refrigeracion lo antes posible.
        Ingresa a AbastOS para ver el historial completo.
      </p>
    </div>

    <div style="padding:16px 28px;border-top:1px solid #e5e7eb;background:#f9fafb;">
      <p style="margin:0;font-size:11px;color:#9ca3af;">
        AbastOS IoT Monitor — notificacion automatica
      </p>
    </div>
  </div>
</body>
</html>
"""

    try:
        result = resend.Emails.send(
            {
                "from": "onboarding@resend.dev",
                "to": [to_email],
                "subject": f"[{severity_label}] Alerta de temperatura — {business_name}",
                "html": html,
            }
        )
        return bool(result.get("id"))
    except Exception as e:
        print(f"[Resend] Error enviando correo: {e}")
        return False
