from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ═══════════════════════════════════════════════════════════════
#  PRODUCTOS
# ═══════════════════════════════════════════════════════════════

class ProductCreate(BaseModel):
    name: str
    unit: str = "pieza"          # kg, litro, pieza, caja, manojo...
    buy_price: float = 0.0
    sell_price: float
    stock: float = 0.0
    min_stock: float = 0.0
    is_frequent: bool = False    # aparece en selección rápida
    sort_order: int = 0          # orden en la pantalla de selección rápida

    @field_validator("sell_price", "buy_price", "stock", "min_stock")
    @classmethod
    def must_be_positive(cls, v):
        if v < 0:
            raise ValueError("El valor no puede ser negativo.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Bistec",
                "unit": "kg",
                "buy_price": 100.0,
                "sell_price": 160.0,
                "stock": 20.0,
                "min_stock": 5.0,
                "is_frequent": True,
                "sort_order": 1,
            }
        }
    }


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    stock: Optional[float] = None
    min_stock: Optional[float] = None
    is_frequent: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: str
    business_id: str
    name: str
    unit: str
    buy_price: float
    sell_price: float
    stock: float
    min_stock: float
    is_frequent: bool
    sort_order: int
    is_active: bool
    created_at: datetime
    low_stock: bool = False      # campo calculado: stock <= min_stock


# ── Catálogo base por tipo de negocio ─────────────────────────────────────────
# Cuando el dueño crea su negocio puede importar uno de estos catálogos.

CATALOG_TEMPLATES = {
    "carniceria": [
        {"name": "Carne molida",  "unit": "kg",    "sell_price": 120.0, "is_frequent": True,  "sort_order": 1},
        {"name": "Bistec",        "unit": "kg",    "sell_price": 160.0, "is_frequent": True,  "sort_order": 2},
        {"name": "Chuleta",       "unit": "kg",    "sell_price": 130.0, "is_frequent": True,  "sort_order": 3},
        {"name": "Costilla",      "unit": "kg",    "sell_price": 110.0, "is_frequent": True,  "sort_order": 4},
        {"name": "Milanesa",      "unit": "kg",    "sell_price": 150.0, "is_frequent": True,  "sort_order": 5},
        {"name": "Pollo entero",  "unit": "pieza", "sell_price": 95.0,  "is_frequent": True,  "sort_order": 6},
        {"name": "Pechuga",       "unit": "kg",    "sell_price": 110.0, "is_frequent": True,  "sort_order": 7},
        {"name": "Muslo/pierna",  "unit": "kg",    "sell_price": 85.0,  "is_frequent": False, "sort_order": 8},
        {"name": "Chorizo",       "unit": "kg",    "sell_price": 90.0,  "is_frequent": False, "sort_order": 9},
        {"name": "Cecina",        "unit": "kg",    "sell_price": 180.0, "is_frequent": False, "sort_order": 10},
        {"name": "Hígado",        "unit": "kg",    "sell_price": 70.0,  "is_frequent": False, "sort_order": 11},
        {"name": "Machitos",      "unit": "kg",    "sell_price": 80.0,  "is_frequent": False, "sort_order": 12},
    ],
    "verduleria": [
        {"name": "Jitomate",      "unit": "kg",    "sell_price": 25.0,  "is_frequent": True,  "sort_order": 1},
        {"name": "Cebolla",       "unit": "kg",    "sell_price": 20.0,  "is_frequent": True,  "sort_order": 2},
        {"name": "Chile serrano", "unit": "kg",    "sell_price": 30.0,  "is_frequent": True,  "sort_order": 3},
        {"name": "Papa",          "unit": "kg",    "sell_price": 18.0,  "is_frequent": True,  "sort_order": 4},
        {"name": "Zanahoria",     "unit": "kg",    "sell_price": 15.0,  "is_frequent": True,  "sort_order": 5},
        {"name": "Lechuga",       "unit": "pieza", "sell_price": 12.0,  "is_frequent": True,  "sort_order": 6},
        {"name": "Aguacate",      "unit": "pieza", "sell_price": 18.0,  "is_frequent": False, "sort_order": 7},
        {"name": "Limón",         "unit": "kg",    "sell_price": 22.0,  "is_frequent": False, "sort_order": 8},
    ],
    "abarrotes": [
        {"name": "Refresco 600ml","unit": "pieza", "sell_price": 18.0,  "is_frequent": True,  "sort_order": 1},
        {"name": "Agua 1L",       "unit": "pieza", "sell_price": 12.0,  "is_frequent": True,  "sort_order": 2},
        {"name": "Sabritas",      "unit": "pieza", "sell_price": 18.0,  "is_frequent": True,  "sort_order": 3},
        {"name": "Leche 1L",      "unit": "pieza", "sell_price": 24.0,  "is_frequent": True,  "sort_order": 4},
        {"name": "Pan Bimbo",     "unit": "pieza", "sell_price": 48.0,  "is_frequent": True,  "sort_order": 5},
        {"name": "Huevo kg",      "unit": "kg",    "sell_price": 38.0,  "is_frequent": False, "sort_order": 6},
    ],
}


# ═══════════════════════════════════════════════════════════════
#  VENTAS
# ═══════════════════════════════════════════════════════════════

class SaleItemCreate(BaseModel):
    """Una línea dentro de una venta."""
    product_id: Optional[str] = None   # si viene del catálogo
    description: Optional[str] = None  # si es producto libre (sin catálogo)
    qty: float
    unit_price: float

    @model_validator(mode="after")
    def product_or_description(self):
        if not self.product_id and not self.description:
            raise ValueError("Cada línea necesita product_id o description.")
        if self.qty <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")
        if self.unit_price <= 0:
            raise ValueError("El precio debe ser mayor a 0.")
        return self

    @property
    def subtotal(self) -> float:
        return round(self.qty * self.unit_price, 2)


class SaleCreate(BaseModel):
    items: List[SaleItemCreate]
    notes: Optional[str] = None

    @field_validator("items")
    @classmethod
    def must_have_items(cls, v):
        if not v:
            raise ValueError("Una venta debe tener al menos un producto.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {"product_id": "uuid-del-producto", "qty": 1.5, "unit_price": 160.0},
                    {"description": "Huesos para caldo", "qty": 1.0, "unit_price": 30.0},
                ],
                "notes": "Cliente de confianza",
            }
        }
    }


class SaleItemResponse(BaseModel):
    id: str
    product_id: Optional[str]
    description: Optional[str]
    product_name: Optional[str] = None   # enriquecido desde products
    qty: float
    unit_price: float
    subtotal: float


class SaleResponse(BaseModel):
    id: str
    business_id: str
    user_id: str
    registered_by: Optional[str] = None  # nombre del usuario
    total: float
    payment_type: str
    notes: Optional[str]
    cancelled: bool
    cancelled_reason: Optional[str]
    cancelled_at: Optional[datetime]
    created_at: datetime
    items: List[SaleItemResponse] = []


class SaleUpdate(BaseModel):
    """Solo se pueden editar notas e items mientras no esté cancelada."""
    items: Optional[List[SaleItemCreate]] = None
    notes: Optional[str] = None


class CancelSaleRequest(BaseModel):
    reason: str

    model_config = {
        "json_schema_extra": {
            "example": {"reason": "El cliente se arrepintió"}
        }
    }


# ── Resumen del día ────────────────────────────────────────────────────────────
class DailySummary(BaseModel):
    date: str
    total_sales: float
    sales_count: int
    cancelled_count: int
