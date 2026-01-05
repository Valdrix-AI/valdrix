from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    APP_NAME: str = "CloudSentinel AI"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # We will add AWS/OpenAI keys here later
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_ignore_empty=True
    )

@lru_cache
def get_settings():
    return Settings()