from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache
from typing import List, Union

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Supabase
    supabase_url: str
    supabase_key: str  # service_role key

    # BigQuery
    google_application_credentials: str
    bigquery_project_id: str = "ybh-deployment-testing"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # SMB Paths
    smb_base_path: str = r"\\192.168.1.6\Share3"
    smb_output_path: str = r"\\192.168.1.6\Share3\Public\video-compilation"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Temp
    temp_dir: str = "temp"

    # Output
    output_dir: str = "output"

    # CORS
    cors_origins: Union[str, List[str]] = "http://localhost:3000,http://192.168.1.173:3000"

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',')]
        return v

@lru_cache()
def get_settings():
    return Settings()
