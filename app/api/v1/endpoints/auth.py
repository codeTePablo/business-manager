from fastapi import APIRouter, HTTPException, status, Depends

from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.core.security import hash_password, verify_password, create_access_token, get_current_user_id
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest):
    """
    Registra un nuevo usuario.
    - Verifica que el email no exista
    - Hashea la contraseña antes de guardarla
    - Devuelve un token JWT listo para usar
    """
    db = get_supabase()

    # 1. Verificar si el email ya existe
    existing = db.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una cuenta con ese correo.",
        )

    # 2. Guardar usuario con contraseña hasheada
    result = db.table("users").insert({
        "name": body.name,
        "email": body.email,
        "password_hash": hash_password(body.password),
    }).execute()

    user = result.data[0]

    # 3. Crear y devolver token
    token = create_access_token(user_id=user["id"])
    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        name=user["name"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """
    Login con email y contraseña.
    Devuelve un token JWT si las credenciales son correctas.
    """
    db = get_supabase()

    # 1. Buscar usuario por email
    result = db.table("users").select("*").eq("email", body.email).execute()
    if not result.data:
        # Mismo mensaje para no revelar si el email existe o no
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    user = result.data[0]

    # 2. Verificar contraseña
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    # 3. Crear y devolver token
    token = create_access_token(user_id=user["id"])
    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        name=user["name"],
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user_id: str = Depends(get_current_user_id)):
    """
    Devuelve los datos del usuario autenticado.
    Requiere token en el header: Authorization: Bearer <token>

    Ejemplo de uso desde el frontend:
        fetch('/api/v1/auth/me', {
            headers: { Authorization: `Bearer ${token}` }
        })
    """
    db = get_supabase()
    result = db.table("users").select("id, name, email").eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    return result.data[0]

@router.post("/logout", status_code=200)
async def logout(user_id: str = Depends(get_current_user_id)):
    """
    Cierra la sesión del usuario.
 
    IMPORTANTE — cómo funciona JWT:
    El token no se puede invalidar en el servidor porque JWT es stateless
    (el servidor no guarda sesiones). El logout real ocurre en el CLIENTE
    borrando el token del almacenamiento local.
 
    Este endpoint existe para que el frontend tenga un contrato formal de
    logout y pueda hacer limpieza en el servidor si en el futuro se agrega
    un blacklist de tokens.
 
    El frontend debe:
        1. Llamar a este endpoint
        2. Borrar el token de localStorage / sessionStorage
        3. Redirigir al login
    """
    return {"detail": "Sesión cerrada correctamente."}