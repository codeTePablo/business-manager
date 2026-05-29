from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 horas

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Resend (correos de alerta)
    resend_api_key: str = ""   # re_xxxxxxxxxxxx — obten en resend.com

    # App
    app_env: str = "development"
    app_debug: bool = True
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()  # Se lee el .env una sola vez y se cachea
def get_settings() -> Settings:
    return Settings()
