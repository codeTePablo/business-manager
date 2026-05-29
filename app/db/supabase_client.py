"""
Cliente de Supabase.
Se inicializa una vez y se reutiliza en toda la app (patrón singleton).
"""

from supabase import create_client, Client
from app.core.config import get_settings
from functools import lru_cache

settings = get_settings()


@lru_cache()
def get_supabase() -> Client:
    """
    Retorna el cliente de Supabase.
    Usa service_role_key para que el backend tenga acceso completo
    (bypasea Row Level Security cuando es necesario para operaciones admin).
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
