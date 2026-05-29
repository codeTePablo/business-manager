from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.schemas.business import (
    BusinessCreate, BusinessResponse, BusinessUpdate,
    InviteMemberRequest, MemberResponse, UpdateRoleRequest,
    BusinessContext,
)
from app.core.security import get_current_user_id, require_member, require_owner
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/businesses", tags=["Negocios"])


# ═══════════════════════════════════════════════════════════════
#  GESTIÓN DE NEGOCIOS
# ═══════════════════════════════════════════════════════════════

@router.post("", response_model=BusinessResponse, status_code=201)
async def create_business(
    body: BusinessCreate,
    user_id: str = Depends(get_current_user_id),
):
    """
    Crea un nuevo negocio.
    El creador queda automáticamente como DUEÑO (via trigger en BD).
    No requiere X-Business-ID porque el negocio aún no existe.
    """
    db = get_supabase()

    result = db.table("businesses").insert({
        "user_id": user_id,
        "name": body.name,
        "type": body.type,
        "address": body.address,
    }).execute()

    business = result.data[0]
    business["my_role"] = "dueno"
    return business


@router.get("", response_model=List[BusinessResponse])
async def list_my_businesses(
    user_id: str = Depends(get_current_user_id),
):
    """
    Lista todos los negocios a los que pertenece el usuario autenticado,
    incluyendo su rol en cada uno.

    Útil para el selector de negocio al iniciar sesión.
    """
    db = get_supabase()

    # JOIN: business_members → businesses
    result = (
        db.table("business_members")
        .select("role, is_active, businesses(*)")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )

    businesses = []
    for row in result.data:
        b = row["businesses"]
        b["my_role"] = row["role"]
        businesses.append(b)

    return businesses


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    ctx: BusinessContext = Depends(require_member),
):
    """
    Detalle de un negocio específico.
    Requiere ser miembro del negocio (header X-Business-ID).
    """
    db = get_supabase()
    result = (
        db.table("businesses")
        .select("*")
        .eq("id", ctx.business_id)
        .execute()
    )
    business = result.data[0]
    business["my_role"] = ctx.role
    return business


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    body: BusinessUpdate,
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño
):
    """
    Actualiza nombre, tipo o dirección del negocio.
    Solo el DUEÑO puede modificar esto.
    """
    db = get_supabase()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar.")

    result = (
        db.table("businesses")
        .update(data)
        .eq("id", ctx.business_id)
        .execute()
    )
    business = result.data[0]
    business["my_role"] = ctx.role
    return business


# ═══════════════════════════════════════════════════════════════
#  GESTIÓN DE MIEMBROS (solo el dueño puede gestionar)
# ═══════════════════════════════════════════════════════════════

@router.get("/{business_id}/members", response_model=List[MemberResponse])
async def list_members(
    ctx: BusinessContext = Depends(require_owner),   # solo el dueño ve esto
):
    """
    Lista todos los miembros del negocio con su rol.
    Solo accesible para el DUEÑO.
    """
    db = get_supabase()

    result = (
        db.table("business_members")
        .select("user_id, role, is_active, joined_at, users!business_members_user_id_fkey(name, email)")
        .eq("business_id", ctx.business_id)
        .execute()
    )

    members = []
    for row in result.data:
        members.append({
            "user_id":   row["user_id"],
            "name":      row["users"]["name"],
            "email":     row["users"]["email"],
            "role":      row["role"],
            "is_active": row["is_active"],
            "joined_at": row["joined_at"],
        })
    return members


@router.post("/{business_id}/members", response_model=MemberResponse, status_code=201)
async def invite_member(
    body: InviteMemberRequest,
    ctx: BusinessContext = Depends(require_owner),
):
    """
    Agrega un empleado al negocio por su email.
    El usuario debe tener cuenta registrada en AbastOS.
    Solo el DUEÑO puede invitar miembros.
    """
    db = get_supabase()

    # 1. Buscar usuario por email
    user_result = (
        db.table("users")
        .select("id, name, email")
        .eq("email", body.email)
        .execute()
    )
    if not user_result.data:
        raise HTTPException(
            status_code=404,
            detail=f"No existe ningún usuario con el correo {body.email}. "
                   "Pídele que se registre primero."
        )

    target_user = user_result.data[0]

    # 2. Verificar que no sea ya miembro activo
    existing = (
        db.table("business_members")
        .select("id, is_active")
        .eq("business_id", ctx.business_id)
        .eq("user_id", target_user["id"])
        .execute()
    )
    if existing.data and existing.data[0]["is_active"]:
        raise HTTPException(
            status_code=400,
            detail="Este usuario ya es miembro del negocio."
        )

    # 3. Insertar o reactivar
    if existing.data:
        # reactivar si fue desactivado antes
        db.table("business_members").update({
            "role": body.role,
            "is_active": True,
            "invited_by": ctx.user_id,
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        db.table("business_members").insert({
            "business_id": ctx.business_id,
            "user_id":     target_user["id"],
            "role":        body.role,
            "invited_by":  ctx.user_id,
        }).execute()

    return {
        "user_id":   target_user["id"],
        "name":      target_user["name"],
        "email":     target_user["email"],
        "role":      body.role,
        "is_active": True,
        "joined_at": None,
    }


@router.patch("/{business_id}/members/{member_user_id}/role")
async def update_member_role(
    member_user_id: str,
    body: UpdateRoleRequest,
    ctx: BusinessContext = Depends(require_owner),
):
    """
    Cambia el rol de un miembro (empleado → dueño o viceversa).
    Solo el DUEÑO puede hacer esto.
    No puedes cambiar tu propio rol.
    """
    if member_user_id == ctx.user_id:
        raise HTTPException(
            status_code=400,
            detail="No puedes cambiar tu propio rol."
        )

    db = get_supabase()
    db.table("business_members").update({"role": body.role}).eq(
        "business_id", ctx.business_id
    ).eq("user_id", member_user_id).execute()

    return {"detail": f"Rol actualizado a '{body.role}' correctamente."}


@router.delete("/{business_id}/members/{member_user_id}", status_code=204)
async def remove_member(
    member_user_id: str,
    ctx: BusinessContext = Depends(require_owner),
):
    """
    Desactiva el acceso de un miembro al negocio.
    No elimina el registro, solo lo desactiva (para mantener historial).
    Solo el DUEÑO puede hacer esto.
    """
    if member_user_id == ctx.user_id:
        raise HTTPException(
            status_code=400,
            detail="No puedes removerte a ti mismo del negocio."
        )

    db = get_supabase()
    db.table("business_members").update({"is_active": False}).eq(
        "business_id", ctx.business_id
    ).eq("user_id", member_user_id).execute()
