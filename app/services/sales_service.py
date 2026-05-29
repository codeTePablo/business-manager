"""
Servicio de ventas.
Los movimientos de stock se delegan a inventory_service.apply_movement
para que todo quede registrado en inventory_entries.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException

from app.db.supabase_client import get_supabase
from app.schemas.sales import SaleCreate, SaleResponse, SaleItemResponse
from app.schemas.inventory import EntryType
from app.services import inventory_service


# ═══════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ═══════════════════════════════════════════════════════════════

def _enrich_items(items: list, db) -> List[SaleItemResponse]:
    product_ids = [i["product_id"] for i in items if i.get("product_id")]
    names = {}
    if product_ids:
        result = db.table("products").select("id, name").in_("id", product_ids).execute()
        names = {p["id"]: p["name"] for p in result.data}

    return [
        SaleItemResponse(
            id=item["id"],
            product_id=item.get("product_id"),
            description=item.get("description"),
            product_name=names.get(item.get("product_id")),
            qty=item["qty"],
            unit_price=item["unit_price"],
            subtotal=item["subtotal"],
        )
        for item in items
    ]


def _build_sale_response(sale: dict, items: list, db) -> SaleResponse:
    return SaleResponse(
        id=sale["id"],
        business_id=sale["business_id"],
        user_id=sale["user_id"],
        registered_by=sale.get("registered_by"),
        total=sale["total"],
        payment_type=sale["payment_type"],
        notes=sale.get("notes"),
        cancelled=sale["cancelled"],
        cancelled_reason=sale.get("cancelled_reason"),
        cancelled_at=sale.get("cancelled_at"),
        created_at=sale["created_at"],
        items=_enrich_items(items, db),
    )


# ═══════════════════════════════════════════════════════════════
#  OPERACIONES PRINCIPALES
# ═══════════════════════════════════════════════════════════════

def create_sale(body: SaleCreate, business_id: str, user_id: str) -> SaleResponse:
    db = get_supabase()

    # 1. Validar productos
    product_ids = [i.product_id for i in body.items if i.product_id]
    catalog = {}
    if product_ids:
        result = (
            db.table("products")
            .select("id, name, sell_price, stock, is_active")
            .in_("id", product_ids)
            .eq("business_id", business_id)
            .execute()
        )
        catalog = {p["id"]: p for p in result.data}

        for item in body.items:
            if item.product_id and item.product_id not in catalog:
                raise HTTPException(
                    status_code=404,
                    detail=f"Producto {item.product_id} no encontrado en este negocio."
                )
            if item.product_id and not catalog[item.product_id]["is_active"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"El producto '{catalog[item.product_id]['name']}' está inactivo."
                )

    # 2. Calcular total
    total = sum(round(i.qty * i.unit_price, 2) for i in body.items)

    # 3. Insertar cabecera
    sale_result = db.table("sales").insert({
        "business_id":  business_id,
        "user_id":      user_id,
        "total":        total,
        "payment_type": "efectivo",
        "notes":        body.notes,
        "cancelled":    False,
    }).execute()

    sale = sale_result.data[0]
    sale_id = sale["id"]

    # 4. Insertar items
    items_to_insert = [
        {
            "sale_id":     sale_id,
            "product_id":  item.product_id,
            "description": item.description or (
                catalog[item.product_id]["name"] if item.product_id else None
            ),
            "qty":         item.qty,
            "unit_price":  item.unit_price,
            "subtotal":    round(item.qty * item.unit_price, 2),
        }
        for item in body.items
    ]
    items_result = db.table("sale_items").insert(items_to_insert).execute()

    # 5. Descontar stock via inventory_service (queda registrado en inventory_entries)
    for item in body.items:
        if item.product_id:
            inventory_service.apply_movement(
                business_id=business_id,
                product_id=item.product_id,
                user_id=user_id,
                entry_type=EntryType.venta,
                qty_in_sell_unit=-item.qty,   # negativo = salida
                sale_id=sale_id,
                notes=f"Venta registrada",
                db=db,
            )

    return _build_sale_response(sale, items_result.data, db)


def get_sale(sale_id: str, business_id: str) -> SaleResponse:
    db = get_supabase()

    sale_result = (
        db.table("sales")
        .select("*, users!sales_user_id_fkey(name)")
        .eq("id", sale_id)
        .eq("business_id", business_id)
        .execute()
    )
    if not sale_result.data:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    sale = sale_result.data[0]
    if sale.get("users"):
        sale["registered_by"] = sale["users"]["name"]

    items_result = (
        db.table("sale_items").select("*").eq("sale_id", sale_id).execute()
    )
    return _build_sale_response(sale, items_result.data, db)


def list_sales(
    business_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_cancelled: bool = False,
) -> list:
    db = get_supabase()

    query = (
        db.table("sales")
        .select("*, users!sales_user_id_fkey(name)")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
    )
    if not include_cancelled:
        query = query.eq("cancelled", False)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)

    result = query.execute()
    sales = []
    for sale in result.data:
        if sale.get("users"):
            sale["registered_by"] = sale["users"]["name"]
        sale["items"] = []
        sales.append(sale)
    return sales


def update_sale(sale_id: str, business_id: str, user_id: str, body) -> SaleResponse:
    db = get_supabase()

    sale_result = (
        db.table("sales").select("*")
        .eq("id", sale_id).eq("business_id", business_id).execute()
    )
    if not sale_result.data:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    sale = sale_result.data[0]
    if sale["cancelled"]:
        raise HTTPException(status_code=400, detail="No se puede editar una venta cancelada.")

    updates = {}
    if body.notes is not None:
        updates["notes"] = body.notes

    if body.items:
        # Revertir stock de items anteriores via inventory_service
        old_items = db.table("sale_items").select("*").eq("sale_id", sale_id).execute().data
        for old in old_items:
            if old.get("product_id"):
                inventory_service.apply_movement(
                    business_id=business_id,
                    product_id=old["product_id"],
                    user_id=user_id,
                    entry_type=EntryType.ajuste_correccion,
                    qty_in_sell_unit=+old["qty"],   # devolver al stock
                    notes=f"Reversión por edición de venta {sale_id[:8]}",
                    db=db,
                )

        db.table("sale_items").delete().eq("sale_id", sale_id).execute()

        # Insertar items nuevos
        product_ids = [i.product_id for i in body.items if i.product_id]
        catalog = {}
        if product_ids:
            result = db.table("products").select("id, name, stock").in_("id", product_ids).execute()
            catalog = {p["id"]: p for p in result.data}

        new_items = []
        new_total = 0
        for item in body.items:
            subtotal = round(item.qty * item.unit_price, 2)
            new_total += subtotal
            new_items.append({
                "sale_id":     sale_id,
                "product_id":  item.product_id,
                "description": item.description or (
                    catalog[item.product_id]["name"] if item.product_id else None
                ),
                "qty":         item.qty,
                "unit_price":  item.unit_price,
                "subtotal":    subtotal,
            })

        db.table("sale_items").insert(new_items).execute()
        updates["total"] = round(new_total, 2)

        for item in body.items:
            if item.product_id:
                inventory_service.apply_movement(
                    business_id=business_id,
                    product_id=item.product_id,
                    user_id=user_id,
                    entry_type=EntryType.venta,
                    qty_in_sell_unit=-item.qty,
                    sale_id=sale_id,
                    notes="Venta editada",
                    db=db,
                )

    if updates:
        db.table("sales").update(updates).eq("id", sale_id).execute()

    return get_sale(sale_id, business_id)


def cancel_sale(sale_id: str, business_id: str, user_id: str, reason: str) -> SaleResponse:
    db = get_supabase()

    sale_result = (
        db.table("sales").select("*")
        .eq("id", sale_id).eq("business_id", business_id).execute()
    )
    if not sale_result.data:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")

    sale = sale_result.data[0]
    if sale["cancelled"]:
        raise HTTPException(status_code=400, detail="La venta ya está cancelada.")

    # Revertir stock via inventory_service (queda registrado)
    items = db.table("sale_items").select("*").eq("sale_id", sale_id).execute().data
    for item in items:
        if item.get("product_id"):
            inventory_service.apply_movement(
                business_id=business_id,
                product_id=item["product_id"],
                user_id=user_id,
                entry_type=EntryType.venta_revertida,
                qty_in_sell_unit=+item["qty"],   # positivo = regresa al stock
                sale_id=sale_id,
                notes=f"Cancelación: {reason}",
                db=db,
            )

    db.table("sales").update({
        "cancelled":        True,
        "cancelled_reason": reason,
        "cancelled_at":     datetime.now(timezone.utc).isoformat(),
        "cancelled_by":     user_id,
    }).eq("id", sale_id).execute()

    return get_sale(sale_id, business_id)
