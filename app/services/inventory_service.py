"""
Servicio de inventario.

Este es el módulo central del stock. Toda actualización de inventario —
venga de una venta, una compra o un ajuste manual — pasa por aquí.

La función principal es apply_movement(), que:
  1. Calcula el qty_change en unidad de venta
  2. Llama al stored procedure de PostgreSQL que aplica el movimiento
     de forma atómica (stock update + registro en inventory_entries)
"""

from typing import Optional
from fastapi import HTTPException

from app.db.supabase_client import get_supabase
from app.schemas.inventory import (
    EntryType, ENTRY_SIGN, ENTRY_LABELS,
    PurchaseCreate, PurchaseResponse,
    ManualAdjustment,
    InventoryEntryResponse, StockStatusResponse, InventorySummary,
)


# ═══════════════════════════════════════════════════════════════
#  FUNCIÓN CENTRAL — apply_movement
# ═══════════════════════════════════════════════════════════════

def apply_movement(
    *,
    business_id: str,
    product_id: str,
    user_id: str,
    entry_type: EntryType,
    qty_in_sell_unit: float,    # cantidad YA convertida a unidad de venta
    buy_qty: Optional[float] = None,
    buy_unit: Optional[str] = None,
    sale_id: Optional[str] = None,
    notes: Optional[str] = None,
    db=None,
) -> dict:
    """
    Aplica un movimiento de inventario de forma atómica vía stored procedure.

    El qty_in_sell_unit ya debe venir con el signo correcto:
      - Entradas (compra, ajuste+):  positivo
      - Salidas (venta, merma, robo): negativo

    Retorna el registro creado en inventory_entries.
    """
    if db is None:
        db = get_supabase()

    result = db.rpc("apply_inventory_movement", {
        "p_business_id": business_id,
        "p_product_id":  product_id,
        "p_user_id":     user_id,
        "p_entry_type":  entry_type,
        "p_qty_change":  qty_in_sell_unit,
        "p_buy_qty":     buy_qty,
        "p_buy_unit":    buy_unit,
        "p_sale_id":     sale_id,
        "p_notes":       notes,
    }).execute()

    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Error al registrar el movimiento de inventario."
        )

    return result.data


# ═══════════════════════════════════════════════════════════════
#  COMPRAS
# ═══════════════════════════════════════════════════════════════

def register_purchase(
    body: PurchaseCreate,
    business_id: str,
    user_id: str,
) -> PurchaseResponse:
    """
    Registra una compra de mercancía y actualiza el stock.

    La conversión de unidades funciona así:
      qty_en_stock = buy_qty × buy_unit_qty
      (buy_unit_qty está en el producto: ej. 1 caja = 20 kg)

    Si el usuario envía unit_cost, se actualiza el buy_price del producto.
    """
    db = get_supabase()

    # 1. Obtener producto con sus unidades
    prod_result = (
        db.table("products")
        .select("id, name, unit, buy_unit, buy_unit_qty, stock, is_active")
        .eq("id", body.product_id)
        .eq("business_id", business_id)
        .execute()
    )
    if not prod_result.data:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    product = prod_result.data[0]

    if not product["is_active"]:
        raise HTTPException(
            status_code=400,
            detail=f"El producto '{product['name']}' está inactivo."
        )

    # 2. Resolver unidad de compra
    effective_buy_unit = body.buy_unit or product["buy_unit"]
    buy_unit_qty = float(product["buy_unit_qty"])

    # Si la unidad enviada coincide con la de venta, conversión 1:1
    if effective_buy_unit == product["unit"]:
        buy_unit_qty = 1.0

    # 3. Calcular cuántas unidades de venta se suman al stock
    sell_qty_added = round(body.buy_qty * buy_unit_qty, 3)
    stock_before = float(product["stock"])

    # 4. Aplicar movimiento (positivo = entrada)
    apply_movement(
        business_id=business_id,
        product_id=body.product_id,
        user_id=user_id,
        entry_type=EntryType.compra,
        qty_in_sell_unit=+sell_qty_added,
        buy_qty=body.buy_qty,
        buy_unit=effective_buy_unit,
        notes=body.notes or f"Compra: {body.buy_qty} {effective_buy_unit}",
        db=db,
    )

    # 5. Actualizar buy_price si viene unit_cost
    if body.unit_cost is not None:
        db.table("products").update(
            {"buy_price": body.unit_cost}
        ).eq("id", body.product_id).execute()

    # 6. Leer entry recién creada para el response
    entry = (
        db.table("inventory_entries")
        .select("id, created_at, stock_after")
        .eq("product_id", body.product_id)
        .eq("entry_type", EntryType.compra)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data[0]

    return PurchaseResponse(
        product_id=body.product_id,
        product_name=product["name"],
        buy_qty=body.buy_qty,
        buy_unit=effective_buy_unit,
        sell_qty_added=sell_qty_added,
        sell_unit=product["unit"],
        stock_before=stock_before,
        stock_after=entry["stock_after"],
        unit_cost=body.unit_cost,
        entry_id=entry["id"],
        created_at=entry["created_at"],
    )


# ═══════════════════════════════════════════════════════════════
#  AJUSTES MANUALES
# ═══════════════════════════════════════════════════════════════

def register_adjustment(
    body: ManualAdjustment,
    business_id: str,
    user_id: str,
) -> InventoryEntryResponse:
    """
    Registra un ajuste manual de inventario.

    Lógica de signos:
      - merma / robo       → siempre negativo (sale del stock)
      - corrección positiva → suma al stock
      - corrección negativa → resta del stock
    """
    db = get_supabase()

    # Verificar que el producto existe en este negocio
    prod_result = (
        db.table("products")
        .select("id, name, unit")
        .eq("id", body.product_id)
        .eq("business_id", business_id)
        .execute()
    )
    if not prod_result.data:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    product = prod_result.data[0]

    # Calcular signo según tipo
    sign = ENTRY_SIGN[body.entry_type]

    if body.entry_type == EntryType.ajuste_correccion:
        # Para corrección el usuario envía el valor con signo directo
        qty_change = round(body.qty, 3)
    else:
        # Para merma y robo siempre es una salida (negativo)
        qty_change = -abs(round(body.qty, 3))

    apply_movement(
        business_id=business_id,
        product_id=body.product_id,
        user_id=user_id,
        entry_type=body.entry_type,
        qty_in_sell_unit=qty_change,
        notes=body.notes,
        db=db,
    )

    # Leer el entry recién creado
    entry = (
        db.table("inventory_entries")
        .select("*, users!inventory_entries_user_id_fkey(name)")
        .eq("product_id", body.product_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data[0]

    return _build_entry_response(entry, product["name"])


# ═══════════════════════════════════════════════════════════════
#  CONSULTAS
# ═══════════════════════════════════════════════════════════════

def get_product_history(
    product_id: str,
    business_id: str,
    limit: int = 50,
) -> list:
    """Historial de movimientos de un producto, más reciente primero."""
    db = get_supabase()

    # Verificar que el producto pertenece al negocio
    prod_result = (
        db.table("products")
        .select("id, name")
        .eq("id", product_id)
        .eq("business_id", business_id)
        .execute()
    )
    if not prod_result.data:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    product_name = prod_result.data[0]["name"]

    entries = (
        db.table("inventory_entries")
        .select("*, users!inventory_entries_user_id_fkey(name)")
        .eq("product_id", product_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data

    return [_build_entry_response(e, product_name) for e in entries]


def get_inventory_summary(business_id: str) -> InventorySummary:
    """
    Resumen del estado del inventario del negocio.
    Muestra cuántos productos tienen stock bajo o en cero.
    """
    db = get_supabase()

    products = (
        db.table("products")
        .select("id, name, unit, buy_unit, buy_unit_qty, stock, min_stock")
        .eq("business_id", business_id)
        .eq("is_active", True)
        .execute()
    ).data

    low_stock = []
    out_of_stock = 0

    for p in products:
        stock = float(p["stock"])
        min_stock = float(p["min_stock"])
        is_low = stock <= min_stock and min_stock > 0

        if stock == 0:
            out_of_stock += 1

        if is_low:
            low_stock.append(StockStatusResponse(
                product_id=p["id"],
                product_name=p["name"],
                sell_unit=p["unit"],
                buy_unit=p["buy_unit"],
                buy_unit_qty=float(p["buy_unit_qty"]),
                current_stock=stock,
                min_stock=min_stock,
                low_stock=is_low,
                last_movement=None,
            ))

    return InventorySummary(
        total_products=len(products),
        low_stock_count=len(low_stock),
        out_of_stock_count=out_of_stock,
        low_stock_products=low_stock,
    )


def get_stock_status(business_id: str) -> list:
    """Lista todos los productos con su stock actual."""
    db = get_supabase()

    products = (
        db.table("products")
        .select("id, name, unit, buy_unit, buy_unit_qty, stock, min_stock")
        .eq("business_id", business_id)
        .eq("is_active", True)
        .order("name")
        .execute()
    ).data

    result = []
    for p in products:
        stock = float(p["stock"])
        min_stock = float(p["min_stock"])
        result.append(StockStatusResponse(
            product_id=p["id"],
            product_name=p["name"],
            sell_unit=p["unit"],
            buy_unit=p["buy_unit"],
            buy_unit_qty=float(p["buy_unit_qty"]),
            current_stock=stock,
            min_stock=min_stock,
            low_stock=stock <= min_stock and min_stock > 0,
            last_movement=None,
        ))
    return result


# ═══════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ═══════════════════════════════════════════════════════════════

def _build_entry_response(entry: dict, product_name: str) -> InventoryEntryResponse:
    registered_by = None
    if entry.get("users"):
        registered_by = entry["users"]["name"]

    return InventoryEntryResponse(
        id=entry["id"],
        product_id=entry["product_id"],
        product_name=product_name,
        entry_type=entry["entry_type"],
        entry_label=ENTRY_LABELS.get(entry["entry_type"], entry["entry_type"]),
        qty_change=entry["qty_change"],
        buy_qty=entry.get("buy_qty"),
        buy_unit=entry.get("buy_unit"),
        stock_after=entry["stock_after"],
        sale_id=entry.get("sale_id"),
        notes=entry.get("notes"),
        registered_by=registered_by,
        created_at=entry["created_at"],
    )
