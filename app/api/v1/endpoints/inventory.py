from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from app.schemas.inventory import (
    PurchaseCreate, PurchaseResponse,
    ManualAdjustment,
    InventoryEntryResponse, StockStatusResponse, InventorySummary,
)
from app.core.security import require_member, require_owner, BusinessContext
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventario"])


# ═══════════════════════════════════════════════════════════════
#  ESTADO DEL STOCK
# ═══════════════════════════════════════════════════════════════

@router.get("/summary", response_model=InventorySummary)
async def get_summary(
    ctx: BusinessContext = Depends(require_member),
):
    """
    Resumen general del inventario.
    Muestra cuántos productos tienen stock bajo o en cero.
    Es el widget de alertas del dashboard principal.
    """
    return inventory_service.get_inventory_summary(ctx.business_id)


@router.get("/stock", response_model=List[StockStatusResponse])
async def get_stock(
    ctx: BusinessContext = Depends(require_member),
):
    """
    Lista todos los productos con su stock actual.
    Incluye indicador low_stock para pintar alertas en la UI.
    """
    return inventory_service.get_stock_status(ctx.business_id)


# ═══════════════════════════════════════════════════════════════
#  COMPRAS
# ═══════════════════════════════════════════════════════════════

@router.post("/purchases", response_model=PurchaseResponse, status_code=201)
async def register_purchase(
    body: PurchaseCreate,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño registra compras
):
    """
    Registra una compra de mercancía y actualiza el stock.

    Soporta unidad dual automáticamente:
    - Si el producto es una carnicería (sell_unit=kg, buy_unit=kg):
        buy_qty=10 → suma 10 kg al stock
    - Si es un mayorista (sell_unit=pieza, buy_unit=caja, buy_unit_qty=24):
        buy_qty=3 cajas → suma 72 piezas al stock

    El campo buy_unit es opcional: si no se envía, se usa el buy_unit
    configurado en el producto.
    """
    return inventory_service.register_purchase(body, ctx.business_id, ctx.user_id)


# ═══════════════════════════════════════════════════════════════
#  AJUSTES MANUALES
# ═══════════════════════════════════════════════════════════════

@router.post("/adjustments", response_model=InventoryEntryResponse, status_code=201)
async def register_adjustment(
    body: ManualAdjustment,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño hace ajustes
):
    """
    Ajuste manual del stock. Solo el DUEÑO puede hacer esto.

    Tipos disponibles:
    - **ajuste_merma**: carne vencida, producto dañado (resta stock)
    - **ajuste_robo**: pérdida o robo (resta stock)
    - **ajuste_correccion**: corrección de conteo físico (suma o resta)
    - **ajuste_inicial**: carga inicial de stock de un producto nuevo

    El motivo (notes) es obligatorio para todos los ajustes.
    """
    return inventory_service.register_adjustment(body, ctx.business_id, ctx.user_id)


# ═══════════════════════════════════════════════════════════════
#  HISTORIAL
# ═══════════════════════════════════════════════════════════════

@router.get("/products/{product_id}/history", response_model=List[InventoryEntryResponse])
async def get_product_history(
    product_id: str,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño ve el historial completo
    limit: int = Query(50, ge=1, le=200),
):
    """
    Historial completo de movimientos de un producto.
    Muestra ventas, compras y ajustes en orden cronológico inverso.
    Solo accesible para el DUEÑO.
    """
    return inventory_service.get_product_history(product_id, ctx.business_id, limit)
