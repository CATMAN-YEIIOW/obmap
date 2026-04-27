from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql://obmap:obmap123456@postgres:5432/obmap"
    redis_url: str = "redis://redis:6379"
    simulator_enabled: bool = True

    # MQTT Configuration
    mqtt_broker_host: str = "emqx"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "admin"
    mqtt_password: str = "asdfghjkl66"

    class Config:
        env_file = ".env"
        # Allow field aliasing for env vars with underscores
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()