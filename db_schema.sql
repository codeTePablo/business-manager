-- ═══════════════════════════════════════════════════════════════
--  AbastOS — Schema inicial para Supabase (PostgreSQL)
--  Ejecuta esto en: supabase.com → tu proyecto → SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- Extensión para generar UUIDs automáticamente
create extension if not exists "uuid-ossp";

-- ── USUARIOS ─────────────────────────────────────────────────────
create table users (
    id            uuid primary key default uuid_generate_v4(),
    name          text not null,
    email         text not null unique,
    password_hash text not null,
    created_at    timestamptz default now(),
    updated_at    timestamptz default now()
);

-- ── NEGOCIOS ─────────────────────────────────────────────────────
create table businesses (
    id         uuid primary key default uuid_generate_v4(),
    user_id    uuid not null references users(id) on delete cascade,
    name       text not null,
    type       text,                  -- 'carniceria', 'verduleria', etc.
    address    text,
    is_active  boolean default true,
    created_at timestamptz default now()
);

-- ── PRODUCTOS / CATÁLOGO ─────────────────────────────────────────
create table products (
    id           uuid primary key default uuid_generate_v4(),
    business_id  uuid not null references businesses(id) on delete cascade,
    name         text not null,
    unit         text default 'pieza',   -- kg, litro, pieza, caja...
    buy_price    numeric(10,2) default 0,
    sell_price   numeric(10,2) default 0,
    stock        numeric(10,3) default 0,
    min_stock    numeric(10,3) default 0,
    is_active    boolean default true,
    created_at   timestamptz default now()
);

-- ── VENTAS (cabecera) ─────────────────────────────────────────────
create table sales (
    id           uuid primary key default uuid_generate_v4(),
    business_id  uuid not null references businesses(id) on delete cascade,
    user_id      uuid not null references users(id),
    total        numeric(10,2) not null,
    payment_type text default 'efectivo',  -- efectivo | transferencia | fiado
    notes        text,
    cancelled    boolean default false,
    created_at   timestamptz default now()
);

-- ── DETALLE DE VENTA ──────────────────────────────────────────────
create table sale_items (
    id          uuid primary key default uuid_generate_v4(),
    sale_id     uuid not null references sales(id) on delete cascade,
    product_id  uuid references products(id),
    description text,                       -- para ventas sin producto en catálogo
    qty         numeric(10,3) not null,
    unit_price  numeric(10,2) not null,
    subtotal    numeric(10,2) not null
);

-- ── GASTOS ────────────────────────────────────────────────────────
create table expenses (
    id          uuid primary key default uuid_generate_v4(),
    business_id uuid not null references businesses(id) on delete cascade,
    category    text not null,   -- mercancia | renta | servicios | nomina | otro
    concept     text not null,
    amount      numeric(10,2) not null,
    supplier    text,
    created_at  timestamptz default now()
);

-- ── EMPLEADOS ────────────────────────────────────────────────────
create table employees (
    id             uuid primary key default uuid_generate_v4(),
    business_id    uuid not null references businesses(id) on delete cascade,
    name           text not null,
    role           text,
    salary         numeric(10,2) not null,
    salary_period  text default 'semanal',  -- diario | semanal | quincenal
    is_active      boolean default true,
    created_at     timestamptz default now()
);

-- ── ASISTENCIA ───────────────────────────────────────────────────
create table attendance (
    id          uuid primary key default uuid_generate_v4(),
    employee_id uuid not null references employees(id) on delete cascade,
    date        date not null,
    status      text default 'presente',  -- presente | falta | media_jornada
    hours       numeric(4,1) default 8,
    created_at  timestamptz default now(),
    unique(employee_id, date)             -- un registro por empleado por día
);

-- ── ANTICIPOS ────────────────────────────────────────────────────
create table advances (
    id          uuid primary key default uuid_generate_v4(),
    employee_id uuid not null references employees(id) on delete cascade,
    amount      numeric(10,2) not null,
    description text,
    created_at  timestamptz default now()
);

-- ── PAGOS DE NÓMINA ──────────────────────────────────────────────
create table payroll (
    id           uuid primary key default uuid_generate_v4(),
    employee_id  uuid not null references employees(id) on delete cascade,
    period_start date not null,
    period_end   date not null,
    gross        numeric(10,2) not null,
    deductions   numeric(10,2) default 0,
    net          numeric(10,2) not null,
    paid_at      timestamptz default now()
);

-- ═══════════════════════════════════════════════════════════════
--  ÍNDICES — aceleran las consultas más frecuentes
-- ═══════════════════════════════════════════════════════════════
create index idx_sales_business_date      on sales(business_id, created_at);
create index idx_expenses_business_date   on expenses(business_id, created_at);
create index idx_products_business        on products(business_id);
create index idx_attendance_employee_date on attendance(employee_id, date);
create index idx_businesses_user          on businesses(user_id);
