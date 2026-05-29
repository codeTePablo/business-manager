-- ═══════════════════════════════════════════════════════════════
--  AbastOS — Migración: Inventario con unidad dual
--  Ejecuta esto en: supabase.com → SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- ── 1. EXTENDER TABLA PRODUCTS ────────────────────────────────────
-- Unidad dual: el stock SIEMPRE se guarda en sell_unit
-- buy_unit_qty indica cuántas sell_units hay en una buy_unit
--
-- Ejemplos:
--   Carnicería → sell_unit=kg,    buy_unit=kg,   buy_unit_qty=1
--   Mayorista  → sell_unit=kg,    buy_unit=caja, buy_unit_qty=20
--   Abarrotes  → sell_unit=pieza, buy_unit=caja, buy_unit_qty=24

alter table products
    add column if not exists buy_unit      text             default 'kg',
    add column if not exists buy_unit_qty  numeric(10, 3)   default 1;

-- Migración de dato: los productos existentes asumen buy_unit = sell_unit
update products
set buy_unit     = unit,
    buy_unit_qty = 1
where buy_unit is null or buy_unit_qty is null;


-- ── 2. TABLA DE MOVIMIENTOS DE INVENTARIO ─────────────────────────
-- Libro mayor del inventario. Cada entrada o salida queda registrada.
-- El stock actual = SUM(qty_change) por producto.
--
-- Tipos de movimiento:
--   venta          → generado automáticamente al registrar una venta  (negativo)
--   venta_revertida→ cuando se cancela una venta                      (positivo)
--   compra         → cuando se registra una compra de mercancía       (positivo)
--   ajuste_merma   → merma, caducidad, desperdicio                    (negativo)
--   ajuste_robo    → robo o pérdida                                   (negativo)
--   ajuste_correccion → corrección de conteo físico                   (+ o -)
--   ajuste_inicial → carga inicial de stock al dar de alta el producto(positivo)

create table if not exists inventory_entries (
    id           uuid primary key default uuid_generate_v4(),
    business_id  uuid not null references businesses(id) on delete cascade,
    product_id   uuid not null references products(id)   on delete cascade,
    user_id      uuid not null references users(id),

    -- Tipo de movimiento
    entry_type   text not null,

    -- Cantidad en unidad de VENTA (sell_unit del producto)
    -- Positivo = entrada al stock, Negativo = salida del stock
    qty_change   numeric(10, 3) not null,

    -- Para compras: también guardamos en unidad de COMPRA para trazabilidad
    buy_qty      numeric(10, 3),   -- ej: 3 cajas
    buy_unit     text,             -- ej: caja

    -- Stock resultante después de este movimiento (snapshot)
    stock_after  numeric(10, 3) not null,

    -- Referencia opcional al documento que originó el movimiento
    sale_id      uuid references sales(id),
    notes        text,

    created_at   timestamptz default now()
);

-- Índices para consultas frecuentes
create index if not exists idx_inv_product   on inventory_entries(product_id, created_at desc);
create index if not exists idx_inv_business  on inventory_entries(business_id, created_at desc);
create index if not exists idx_inv_type      on inventory_entries(entry_type);


-- ── 3. FUNCIÓN: aplicar movimiento de inventario ──────────────────
-- Centraliza la lógica de stock para que sea consistente
-- desde ventas, compras y ajustes manuales.

create or replace function apply_inventory_movement(
    p_business_id  uuid,
    p_product_id   uuid,
    p_user_id      uuid,
    p_entry_type   text,
    p_qty_change   numeric,   -- en unidad de venta
    p_buy_qty      numeric    default null,
    p_buy_unit     text       default null,
    p_sale_id      uuid       default null,
    p_notes        text       default null
) returns inventory_entries as $$
declare
    v_current_stock  numeric;
    v_new_stock      numeric;
    v_entry          inventory_entries;
begin
    -- Obtener stock actual con bloqueo para evitar race conditions
    select stock into v_current_stock
    from products
    where id = p_product_id
    for update;

    v_new_stock := v_current_stock + p_qty_change;

    -- El stock nunca puede quedar negativo
    if v_new_stock < 0 then
        v_new_stock := 0;
    end if;

    -- Actualizar stock en products
    update products
    set stock = v_new_stock
    where id = p_product_id;

    -- Registrar el movimiento
    insert into inventory_entries (
        business_id, product_id, user_id,
        entry_type, qty_change,
        buy_qty, buy_unit,
        stock_after, sale_id, notes
    ) values (
        p_business_id, p_product_id, p_user_id,
        p_entry_type, p_qty_change,
        p_buy_qty, p_buy_unit,
        v_new_stock, p_sale_id, p_notes
    )
    returning * into v_entry;

    return v_entry;
end;
$$ language plpgsql;
