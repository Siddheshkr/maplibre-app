from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the spatial API.

    Values are read from environment variables or a local `.env` file. Database
    credentials are only ever used server-side.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MapLibre Spatial API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api"

    database_url: str | None = None
    database_host: str | None = None
    database_port: int = 5432
    database_name: str | None = None
    database_user: str | None = None
    database_password: str | None = None
    database_sslmode: str | None = "prefer"
    database_schemas: str = "public"
    database_pool_min_size: int = Field(default=1, ge=1, le=20)
    database_pool_max_size: int = Field(default=5, ge=1, le=50)

    cors_origins: str = "http://localhost:4200,http://127.0.0.1:4200"
    statement_timeout_ms: int = Field(default=15_000, ge=500, le=120_000)
    tile_extent: int = Field(default=4096, ge=256, le=8192)
    tile_buffer: int = Field(default=64, ge=0, le=512)
    max_features: int = Field(default=2_000, ge=1, le=50_000)
    default_feature_limit: int = Field(default=500, ge=1, le=50_000)
    max_columns: int = Field(default=40, ge=1, le=100)
    layer_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600)
    default_visible_layers: int | None = Field(default=None, ge=0, le=1000)
    style_config_path: str = "config/layer_styles.json"

    @property
    def schemas(self) -> list[str]:
        return [item.strip() for item in self.database_schemas.split(",") if item.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def resolved_database_url(self) -> str | None:
        if self.database_url:
            return self.database_url

        required = (
            self.database_host,
            self.database_name,
            self.database_user,
        )
        if not all(required):
            return None

        auth = quote_plus(self.database_user or "")
        if self.database_password:
            auth = f"{auth}:{quote_plus(self.database_password)}"

        host = self.database_host or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"

        dsn = (
            f"postgresql://{auth}@{host}:{self.database_port}/"
            f"{self.database_name}"
        )
        if self.database_sslmode:
            dsn = f"{dsn}?sslmode={quote_plus(self.database_sslmode)}"
        return dsn

    @property
    def database_configured(self) -> bool:
        return self.resolved_database_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
