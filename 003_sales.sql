-- ═══════════════════════════════════════════════════════════════
--  AbastOS — Migración: Ventas y Catálogo
--  Ejecuta esto en: supabase.com → SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- Columna para marcar productos frecuentes (selección rápida)
alter table products
    add column if not exists is_frequent boolean default false,
    add column if not exists sort_order  int     default 0;

-- Columna cancelled_reason para saber por qué se canceló una venta
alter table sales
    add column if not exists cancelled_reason text,
    add column if not exists cancelled_at     timestamptz,
    add column if not exists cancelled_by     uuid references users(id);

-- ── FUNCIÓN: recalcular total de venta desde sus items ────────────
-- Se llama desde el backend después de editar items.
create or replace function recalculate_sale_total(p_sale_id uuid)
returns void as $$
begin
    update sales
    set total = (
        select coalesce(sum(subtotal), 0)
        from sale_items
        where sale_id = p_sale_id
    )
    where id = p_sale_id;
end;
$$ language plpgsql;

-- ── CATÁLOGO BASE PARA CARNICERÍA ─────────────────────────────────
-- Se inserta usando la función de servicio del backend, pero si quieres
-- hacerlo directo en SQL puedes adaptar este bloque con el business_id real.
--
-- insert into products (business_id, name, unit, sell_price, is_frequent, sort_order)
-- values
--   ('<tu-business-id>', 'Carne molida',      'kg',    120.00, true,  1),
--   ('<tu-business-id>', 'Bistec',            'kg',    160.00, true,  2),
--   ('<tu-business-id>', 'Chuleta',           'kg',    130.00, true,  3),
--   ('<tu-business-id>', 'Costilla',          'kg',    110.00, true,  4),
--   ('<tu-business-id>', 'Milanesa',          'kg',    150.00, true,  5),
--   ('<tu-business-id>', 'Pollo entero',      'pieza', 95.00,  true,  6),
--   ('<tu-business-id>', 'Pechuga',           'kg',    110.00, true,  7),
--   ('<tu-business-id>', 'Chorizo',           'kg',    90.00,  false, 8),
--   ('<tu-business-id>', 'Cecina',            'kg',    180.00, false, 9),
--   ('<tu-business-id>', 'Hígado',            'kg',    70.00,  false, 10);
