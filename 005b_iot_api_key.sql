-- ═══════════════════════════════════════════════════════════════
--  Ejecuta esto DESPUÉS de 005_iot_readings.sql
--  Agrega la columna api_key a iot_config y crea un index único
-- ═══════════════════════════════════════════════════════════════

-- Agrega api_key a iot_config para autenticar el ESP32
-- Genera una api_key aleatoria para registros existentes (si los hay)
alter table iot_config
    add column if not exists api_key text unique;

update iot_config
set api_key = encode(gen_random_bytes(24), 'hex')
where api_key is null;

-- ═══════════════════════════════════════════════════════════════
--  Cómo crear una api_key para tu ESP32
-- ═══════════════════════════════════════════════════════════════
-- Ejecuta esto en Supabase SQL Editor para crear la config inicial
-- de tu negocio con una api_key que copiarás al ESP32:
--
-- INSERT INTO iot_config (
--   business_id,
--   device_id,
--   api_key,
--   alert_email,
--   temp_warning_c,
--   temp_critical_c,
--   humidity_warning_pct,
--   alert_cooldown_minutes
-- ) VALUES (
--   'TU_BUSINESS_UUID_AQUI',
--   'esp32-cold-room-01',
--   encode(gen_random_bytes(24), 'hex'),  -- genera clave aleatoria
--   'dueno@ejemplo.com',
--   5.0,
--   8.0,
--   85.0,
--   30
-- )
-- RETURNING api_key;   -- <-- copia este valor al ESP32
