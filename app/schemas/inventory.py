from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Tipos de movimiento ───────────────────────────────────────────────────────
class EntryType(str, Enum):
    venta           = "venta"
    venta_revertida = "venta_revertida"
    compra          = "compra"
    ajuste_merma    = "ajuste_merma"
    ajuste_robo     = "ajuste_robo"
    ajuste_correccion = "ajuste_correccion"
    ajuste_inicial  = "ajuste_inicial"


# Tipos que solo puede hacer el dueño
OWNER_ONLY_TYPES = {
    EntryType.ajuste_merma,
    EntryType.ajuste_robo,
    EntryType.ajuste_correccion,
    EntryType.ajuste_inicial,
    EntryType.compra,
}

# Signo de cada tipo: positivo (+) o negativo (-)
ENTRY_SIGN = {
    EntryType.venta:              -1,
    EntryType.venta_revertida:    +1,
    EntryType.compra:             +1,
    EntryType.ajuste_merma:       -1,
    EntryType.ajuste_robo:        -1,
    EntryType.ajuste_correccion:   0,   # puede ser + o -, lo define el usuario
    EntryType.ajuste_inicial:     +1,
}

ENTRY_LABELS = {
    EntryType.venta:              "Venta",
    EntryType.venta_revertida:    "Venta cancelada",
    EntryType.compra:             "Compra de mercancía",
    EntryType.ajuste_merma:       "Ajuste — Merma",
    EntryType.ajuste_robo:        "Ajuste — Robo/Pérdida",
    EntryType.ajuste_correccion:  "Ajuste — Corrección de conteo",
    EntryType.ajuste_inicial:     "Carga inicial",
}


# ═══════════════════════════════════════════════════════════════
#  SCHEMAS DE COMPRA
# ═══════════════════════════════════════════════════════════════

class PurchaseCreate(BaseModel):
    """
    Registra una compra de mercancía.
    Soporta unidad dual: se ingresan las unidades de compra (cajas, costales...)
    y el sistema convierte automáticamente a unidades de venta para el stock.

    Ejemplo carnicería:
        product_id: "uuid-bistec"
        buy_qty: 5          ← 5 kg comprados
        buy_unit: "kg"      ← misma unidad que sell_unit
        unit_cost: 100.0    ← costo por kg

    Ejemplo mayorista:
        product_id: "uuid-refresco"
        buy_qty: 3          ← 3 cajas compradas
        buy_unit: "caja"    ← distinta a sell_unit (pieza)
        unit_cost: 180.0    ← costo por caja
        (el sistema sabe que 1 caja = 24 piezas y suma 72 piezas al stock)
    """
    product_id: str
    buy_qty: float                  # cantidad en unidad de COMPRA
    buy_unit: Optional[str] = None  # si None, se usa el buy_unit del producto
    unit_cost: Optional[float] = None  # costo por unidad de compra (actualiza buy_price)
    notes: Optional[str] = None

    @field_validator("buy_qty")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")
        return v


class PurchaseResponse(BaseModel):
    product_id: str
    product_name: str
    buy_qty: float
    buy_unit: str
    sell_qty_added: float           # cuántas unidades de venta se sumaron al stock
    sell_unit: str
    stock_before: float
    stock_after: float
    unit_cost: Optional[float]
    entry_id: str
    created_at: datetime


# ═══════════════════════════════════════════════════════════════
#  SCHEMAS DE AJUSTE MANUAL
# ═══════════════════════════════════════════════════════════════

class ManualAdjustment(BaseModel):
    """
    Ajuste manual del inventario.
    Para merma, robo o corrección de conteo físico.

    - ajuste_merma / ajuste_robo: qty es siempre positivo,
      el sistema lo convierte en negativo automáticamente.
    - ajuste_correccion: qty puede ser positivo o negativo
      (positivo = agregar, negativo = quitar).
    """
    product_id: str
    entry_type: EntryType
    qty: float          # siempre positivo para merma/robo; +/- para corrección
    notes: str          # obligatorio para ajustes manuales

    @field_validator("entry_type")
    @classmethod
    def must_be_manual(cls, v):
        manual = {
            EntryType.ajuste_merma,
            EntryType.ajuste_robo,
            EntryType.ajuste_correccion,
            EntryType.ajuste_inicial,
        }
        if v not in manual:
            raise ValueError(
                "Solo se permiten ajustes manuales: "
                "ajuste_merma, ajuste_robo, ajuste_correccion, ajuste_inicial"
            )
        return v

    @field_validator("notes")
    @classmethod
    def notes_required(cls, v):
        if not v or not v.strip():
            raise ValueError("El motivo del ajuste es obligatorio.")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_id": "uuid-del-producto",
                "entry_type": "ajuste_merma",
                "qty": 2.5,
                "notes": "Carne vencida — se desechó el martes",
            }
        }
    }


# ═══════════════════════════════════════════════════════════════
#  SCHEMAS DE RESPUESTA
# ═══════════════════════════════════════════════════════════════

class InventoryEntryResponse(BaseModel):
    id: str
    product_id: str
    product_name: Optional[str] = None
    entry_type: str
    entry_label: str               # etiqueta legible
    qty_change: float
    buy_qty: Optional[float]
    buy_unit: Optional[str]
    stock_after: float
    sale_id: Optional[str]
    notes: Optional[str]
    registered_by: Optional[str]
    created_at: datetime


class StockStatusResponse(BaseModel):
    """Estado actual del stock de un producto."""
    product_id: str
    product_name: str
    sell_unit: str
    buy_unit: str
    buy_unit_qty: float
    current_stock: float
    min_stock: float
    low_stock: bool
    last_movement: Optional[datetime]


class InventorySummary(BaseModel):
    """Resumen de inventario del negocio."""
    total_products: int
    low_stock_count: int
    out_of_stock_count: int
    low_stock_products: List[StockStatusResponse]
