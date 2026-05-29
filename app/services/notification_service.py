"""
Servicio de notificaciones por correo usando Resend.
https://resend.com — gratis hasta 3,000 emails/mes.

Instalar: pip install resend
Configurar en .env: RESEND_API_KEY=re_xxxxxxxxxxxx
"""

import resend
from app.core.config import get_settings

settings = get_settings()


def _get_client():
    resend.api_key = settings.resend_api_key


def send_iot_alert(
    to_email: str,
    business_name: str,
    device_id: str,
    alert_type: str,
    severity: str,
    temperature_c: float,
    humidity_pct: float | None,
    message: str,
) -> bool:
    """
    Envía un correo de alerta de temperatura/humedad al dueño del negocio.
    Retorna True si el envío fue exitoso.
    """
    _get_client()

    severity_label = "CRITICA" if severity == "critical" else "ADVERTENCIA"
    color          = "#b91c1c" if severity == "critical" else "#b45309"
    border         = "#fecaca" if severity == "critical" else "#fde68a"
    bg             = "#fef2f2" if severity == "critical" else "#fffbeb"

    humidity_row = (
        f"<tr><td style='padding:8px 12px;color:#6b7280;'>Humedad</td>"
        f"<td style='padding:8px 12px;font-weight:600;'>{humidity_pct:.1f}%</td></tr>"
        if humidity_pct is not None else ""
    )

    html = f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,sans-serif;">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:8px;
              border:1px solid #e5e7eb;overflow:hidden;">

    <!-- Header -->
    <div style="background:{color};padding:24px 28px;">
      <p style="margin:0;color:#fff;font-size:11px;font-weight:700;
                letter-spacing:.1em;text-transform:uppercase;">AbastOS — Alerta IoT</p>
      <p style="margin:8px 0 0;color:rgba(255,255,255,.85);font-size:22px;font-weight:700;">
        Alerta {severity_label}
      </p>
    </div>

    <!-- Body -->
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

    <!-- Footer -->
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
        result = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": [to_email],
            "subject": f"[{severity_label}] Alerta de temperatura — {business_name}",
            "html": html,
        })
        return bool(result.get("id"))
    except Exception as e:
        print(f"[Resend] Error enviando correo: {e}")
        return False
