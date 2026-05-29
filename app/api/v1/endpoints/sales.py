from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional

from app.schemas.sales import (
    ProductCreate, ProductUpdate, ProductResponse,
    SaleCreate, SaleUpdate, SaleResponse, CancelSaleRequest, DailySummary,
    CATALOG_TEMPLATES,
)
from app.core.security import require_member, require_owner, BusinessContext
from app.db.supabase_client import get_supabase
from app.services import sales_service
from datetime import date

# ═══════════════════════════════════════════════════════════════
#  PRODUCTOS
# ═══════════════════════════════════════════════════════════════

products_router = APIRouter(prefix="/products", tags=["Productos / Catálogo"])


@products_router.get("/frequent", response_model=List[ProductResponse])
async def get_frequent_products(
    ctx: BusinessContext = Depends(require_member),
):
    """
    Devuelve los productos marcados como frecuentes, ordenados por sort_order.
    Este es el endpoint de SELECCIÓN RÁPIDA que carga el teclado de productos
    en la pantalla de registro de ventas.
    """
    db = get_supabase()
    result = (
        db.table("products")
        .select("*")
        .eq("business_id", ctx.business_id)
        .eq("is_frequent", True)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    products = []
    for p in result.data:
        p["low_stock"] = p["stock"] <= p["min_stock"] and p["min_stock"] > 0
        products.append(p)
    return products


@products_router.get("", response_model=List[ProductResponse])
async def list_products(
    ctx: BusinessContext = Depends(require_member),
    active_only: bool = Query(True),
):
    """Lista todo el catálogo del negocio."""
    db = get_supabase()
    query = db.table("products").select("*").eq("business_id", ctx.business_id).order("name")
    if active_only:
        query = query.eq("is_active", True)
    result = query.execute()

    products = []
    for p in result.data:
        p["low_stock"] = p["stock"] <= p["min_stock"] and p["min_stock"] > 0
        products.append(p)
    return products


@products_router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    body: ProductCreate,
    ctx: BusinessContext = Depends(require_owner),   # solo dueño crea productos
):
    """Agrega un producto al catálogo."""
    db = get_supabase()
    result = db.table("products").insert({
        **body.model_dump(),
        "business_id": ctx.business_id,
    }).execute()
    p = result.data[0]
    p["low_stock"] = p["stock"] <= p["min_stock"] and p["min_stock"] > 0
    return p


@products_router.post("/import-catalog", status_code=201)
async def import_catalog(
    ctx: BusinessContext = Depends(require_owner),
    business_type: str = Query(
        ...,
        description="Tipo de negocio: carniceria | verduleria | abarrotes"
    ),
):
    """
    Importa un catálogo base de productos según el tipo de negocio.
    Útil al arrancar: en lugar de capturar uno por uno, se carga el catálogo completo.
    Solo puede ejecutarse si el negocio aún no tiene productos.
    """
    if business_type not in CATALOG_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de negocio no válido. Opciones: {list(CATALOG_TEMPLATES.keys())}"
        )

    db = get_supabase()

    # Verificar que no tenga productos ya
    existing = db.table("products").select("id").eq("business_id", ctx.business_id).execute()
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Este negocio ya tiene productos. Agrega los nuevos uno por uno."
        )

    products = [
        {**p, "business_id": ctx.business_id}
        for p in CATALOG_TEMPLATES[business_type]
    ]
    db.table("products").insert(products).execute()

    return {"detail": f"Catálogo de {business_type} importado.", "count": len(products)}


@products_router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    body: ProductUpdate,
    ctx: BusinessContext = Depends(require_owner),
):
    """Actualiza precio, stock o cualquier campo de un producto. Solo el dueño."""
    db = get_supabase()
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar.")

    result = (
        db.table("products")
        .update(data)
        .eq("id", product_id)
        .eq("business_id", ctx.business_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    p = result.data[0]
    p["low_stock"] = p["stock"] <= p["min_stock"] and p["min_stock"] > 0
    return p


@products_router.delete("/{product_id}", status_code=204)
async def deactivate_product(
    product_id: str,
    ctx: BusinessContext = Depends(require_owner),
):
    """Desactiva un producto (no se borra para conservar historial en ventas)."""
    db = get_supabase()
    db.table("products").update({"is_active": False}).eq(
        "id", product_id
    ).eq("business_id", ctx.business_id).execute()


# ═══════════════════════════════════════════════════════════════
#  VENTAS
# ═══════════════════════════════════════════════════════════════

sales_router = APIRouter(prefix="/sales", tags=["Ventas"])


@sales_router.post("", response_model=SaleResponse, status_code=201)
async def create_sale(
    body: SaleCreate,
    ctx: BusinessContext = Depends(require_member),   # dueño Y empleado pueden registrar
):
    """
    Registra una venta nueva.
    - Acepta productos del catálogo (product_id) o descripción libre
    - Calcula el total automáticamente
    - Descuenta el stock de cada producto
    - Pago siempre en efectivo
    """
    return sales_service.create_sale(body, ctx.business_id, ctx.user_id)


@sales_router.get("", response_model=List[SaleResponse])
async def list_sales(
    ctx: BusinessContext = Depends(require_member),
    date_from: Optional[str] = Query(None, description="Formato: 2026-03-01"),
    date_to:   Optional[str] = Query(None, description="Formato: 2026-03-31"),
    include_cancelled: bool = Query(False),
):
    """
    Lista ventas del negocio.
    - Sin filtros devuelve todas las ventas activas
    - Con date_from/date_to filtra por rango de fechas
    """
    return sales_service.list_sales(
        ctx.business_id, date_from, date_to, include_cancelled
    )


@sales_router.get("/summary/today", response_model=DailySummary)
async def today_summary(
    ctx: BusinessContext = Depends(require_member),
):
    """
    Resumen del día actual: total vendido, número de ventas.
    Es el dato principal del dashboard.
    """
    db = get_supabase()
    today = date.today().isoformat()

    result = (
        db.table("sales")
        .select("total, cancelled")
        .eq("business_id", ctx.business_id)
        .gte("created_at", f"{today}T00:00:00")
        .lte("created_at", f"{today}T23:59:59")
        .execute()
    )

    active    = [s for s in result.data if not s["cancelled"]]
    cancelled = [s for s in result.data if s["cancelled"]]

    return DailySummary(
        date=today,
        total_sales=round(sum(s["total"] for s in active), 2),
        sales_count=len(active),
        cancelled_count=len(cancelled),
    )


@sales_router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    ctx: BusinessContext = Depends(require_member),
):
    """Detalle completo de una venta con todos sus items."""
    return sales_service.get_sale(sale_id, ctx.business_id)


@sales_router.patch("/{sale_id}", response_model=SaleResponse)
async def update_sale(
    sale_id: str,
    body: SaleUpdate,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño puede editar
):
    """
    Edita una venta existente.
    Permite cambiar notas o reemplazar los items completos.
    No se puede editar una venta cancelada.
    Solo el DUEÑO puede editar ventas.
    """
    return sales_service.update_sale(sale_id, ctx.business_id, ctx.user_id, body)


@sales_router.post("/{sale_id}/cancel", response_model=SaleResponse)
async def cancel_sale(
    sale_id: str,
    body: CancelSaleRequest,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño cancela
):
    """
    Cancela una venta.
    - Revierte el stock de todos los productos involucrados
    - Guarda el motivo y quién canceló
    - No elimina el registro (queda en historial)
    Solo el DUEÑO puede cancelar ventas.
    """
    return sales_service.cancel_sale(sale_id, ctx.business_id, ctx.user_id, body.reason)
