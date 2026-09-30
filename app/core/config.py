from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App settings
    PROJECT_NAME: str = "Vaan Vibes Cafe & Restro Backend"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Allowed Hosts & CORS
    ALLOWED_HOSTS: str = "*"
    BACKEND_CORS_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://localhost:5432/vaan_vibes_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Security & Auth
    SECRET_KEY: str = "vaan_vibes_super_secret_jwt_key_2026_production_grade"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CAFE_ID: str = "van-vibes"
    CAFE_SECRET_KEY: str = "vv_cafe_standee_hmac_secret_2026"

    # Frontend URLs
    CUSTOMER_FRONTEND_URL: str = "http://localhost:3000"
    MANAGEMENT_FRONTEND_URL: str = "http://localhost:3001"

    @property
    def allowed_hosts_list(self) -> list[str]:
        if not self.ALLOWED_HOSTS or self.ALLOWED_HOSTS == "*":
            return ["*"]
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.BACKEND_CORS_ORIGINS or self.BACKEND_CORS_ORIGINS == "*":
            return [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "*",
            ]
        return [i.strip() for i in self.BACKEND_CORS_ORIGINS.split(",") if i.strip()]

    @property
    def cors_methods_list(self) -> list[str]:
        if self.CORS_ALLOW_METHODS == "*":
            return ["*"]
        return [i.strip() for i in self.CORS_ALLOW_METHODS.split(",") if i.strip()]

    @property
    def cors_headers_list(self) -> list[str]:
        if self.CORS_ALLOW_HEADERS == "*":
            return ["*"]
        return [i.strip() for i in self.CORS_ALLOW_HEADERS.split(",") if i.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
