from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MONGODB_URI: str
    DB_NAME: str
    STORAGE_ROOT: str = "storage"
    API_PREFIX: str = "/api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
