-- ═══════════════════════════════════════════════════════════════
--  AbastOS — Migración 005: Lecturas IoT y Alertas
--  Ejecuta esto en: supabase.com → SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- ── TABLA: lecturas del sensor ────────────────────────────────────
-- Una fila por envío del ESP32 (cada 60 segundos recomendado)
create table if not exists sensor_readings (
    id              uuid primary key default uuid_generate_v4(),
    business_id     uuid not null references businesses(id) on delete cascade,
    device_id       text not null,           -- ej: "esp32-cold-room-01"
    temperature_c   numeric(5, 2) not null,
    humidity_pct    numeric(5, 2),
    fan_active      boolean default false,
    led_state       text default 'green',    -- 'green' | 'yellow' | 'red'
    recorded_at     timestamptz default now()
);

create index if not exists idx_sr_business_time
    on sensor_readings(business_id, recorded_at desc);

create index if not exists idx_sr_device_time
    on sensor_readings(device_id, recorded_at desc);

-- ── TABLA: alertas generadas ──────────────────────────────────────
-- Una fila cada vez que se cruza un umbral y se manda el correo
create table if not exists iot_alerts (
    id              uuid primary key default uuid_generate_v4(),
    business_id     uuid not null references businesses(id) on delete cascade,
    device_id       text not null,
    alert_type      text not null,   -- 'high_temp' | 'critical_temp' | 'high_humidity'
    severity        text not null,   -- 'warning' | 'critical'
    temperature_c   numeric(5, 2),
    humidity_pct    numeric(5, 2),
    message         text not null,
    email_sent      boolean default false,
    email_sent_at   timestamptz,
    acknowledged    boolean default false,
    acknowledged_at timestamptz,
    created_at      timestamptz default now()
);

create index if not exists idx_alerts_business
    on iot_alerts(business_id, created_at desc);

-- ── TABLA: configuración de umbrales por negocio ──────────────────
-- El dueño puede ajustar los umbrales desde el frontend
create table if not exists iot_config (
    id                      uuid primary key default uuid_generate_v4(),
    business_id             uuid not null unique references businesses(id) on delete cascade,
    device_id               text not null default 'esp32-cold-room-01',
    temp_warning_c          numeric(4, 1) default 5.0,   -- LED amarillo + fan ON
    temp_critical_c         numeric(4, 1) default 8.0,   -- LED rojo + email
    humidity_warning_pct    numeric(4, 1) default 85.0,
    alert_email             text,           -- correo donde llegan las alertas
    alert_cooldown_minutes  int default 30, -- no repetir email antes de N minutos
    updated_at              timestamptz default now()
);
