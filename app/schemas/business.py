from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


# ── Enum de roles ─────────────────────────────────────────────────────────────
class Role(str, Enum):
    dueno    = "dueno"
    empleado = "empleado"
    contador = "contador"


# ── Negocios ──────────────────────────────────────────────────────────────────
class BusinessCreate(BaseModel):
    name: str
    type: Optional[str] = None     # carniceria, verduleria, etc.
    address: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Carnes El Toro",
                "type": "carniceria",
                "address": "Local 142, Central de Abastos CDMX",
            }
        }
    }


class BusinessResponse(BaseModel):
    id: str
    name: str
    type: Optional[str]
    address: Optional[str]
    is_active: bool
    created_at: datetime

    # Campo extra: rol del usuario que hace la consulta en ESTE negocio
    my_role: Optional[str] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    address: Optional[str] = None


# ── Miembros / Empleados ──────────────────────────────────────────────────────
class InviteMemberRequest(BaseModel):
    email: str            # email del usuario a invitar
    role: Role = Role.empleado

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "empleado@ejemplo.com",
                "role": "empleado",
            }
        }
    }


class MemberResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    is_active: bool
    joined_at: datetime


class UpdateRoleRequest(BaseModel):
    role: Role


# ── Contexto de sesión ────────────────────────────────────────────────────────
# Esto es lo que se inyecta en cada endpoint protegido.
# Contiene user_id + business_id + role ya validados.
class BusinessContext(BaseModel):
    user_id: str
    business_id: str
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == Role.dueno

    @property
    def is_employee(self) -> bool:
        return self.role == Role.empleado
