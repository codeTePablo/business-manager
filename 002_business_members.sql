-- ═══════════════════════════════════════════════════════════════
--  AbastOS — Migración: Multi-negocio y Roles
--  Ejecuta esto en: supabase.com → SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- ── TABLA DE MEMBRESÍAS ───────────────────────────────────────────
-- Esta tabla es el puente entre usuarios y negocios.
-- Un usuario puede pertenecer a N negocios con roles diferentes.
-- Ejemplo: Jose es DUEÑO del negocio A y EMPLEADO del negocio B.

create table if not exists business_members (
    id          uuid primary key default uuid_generate_v4(),
    business_id uuid not null references businesses(id) on delete cascade,
    user_id     uuid not null references users(id)     on delete cascade,
    role        text not null default 'empleado',
                -- 'dueno'    → acceso total
                -- 'empleado' → solo registrar ventas y gastos, sin reportes
    invited_by  uuid references users(id),   -- quién lo agregó
    is_active   boolean default true,
    joined_at   timestamptz default now(),

    unique(business_id, user_id)             -- un usuario, un rol por negocio
);

-- Índices para búsquedas frecuentes
create index if not exists idx_bm_user     on business_members(user_id);
create index if not exists idx_bm_business on business_members(business_id);

-- ── TRIGGER: al crear un negocio, el creador se convierte en DUEÑO ─
-- Así nunca queda un negocio sin dueño y no hay que hacerlo manualmente.

create or replace function auto_add_owner()
returns trigger as $$
begin
    insert into business_members (business_id, user_id, role)
    values (NEW.id, NEW.user_id, 'dueno');
    return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_auto_add_owner on businesses;
create trigger trg_auto_add_owner
    after insert on businesses
    for each row execute function auto_add_owner();

-- ── VERIFICACIÓN: los negocios existentes también deben tener dueño ─
-- Corre esto solo si ya tienes negocios creados antes de esta migración.
-- insert into business_members (business_id, user_id, role)
-- select id, user_id, 'dueno' from businesses
-- on conflict (business_id, user_id) do nothing;
