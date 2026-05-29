from pydantic import BaseModel, EmailStr


# ── Request bodies (lo que recibe el endpoint) ────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Jose García",
                "email": "jose@ejemplo.com",
                "password": "mi_password_seguro",
            }
        }
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Response bodies (lo que devuelve el endpoint) ─────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
