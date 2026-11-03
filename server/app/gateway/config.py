from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='AI_', extra='ignore', allow_inf_nan=False,
        env_file=str(Path(__file__).resolve().parents[2] / '.env'), env_file_encoding='utf-8')
    redis_url: str = 'redis://localhost:6379/0'
    auth_redis_url: str = ''  # Must be the main Spring server's blacklist Redis DB.
    jwt_secret_base64: str = ''  # Spring ACCESS key, not refresh key.
    limit_pool: str = 'interactive-llm-v1'
    global_rpm: int = Field(54, ge=1, le=100000)
    user_rpm: int = Field(30, ge=1, le=100000)
    model_concurrency: int = Field(4, ge=1, le=1000)
    lease_seconds: int = Field(75, ge=5, le=600)
    deadline_seconds: float = Field(60, gt=0, le=300)
    max_attempts: int = Field(2, ge=1, le=3)
    max_input_chars: int = Field(24000, ge=1, le=200000)
    max_output_tokens: int = Field(2048, ge=1, le=32768)
    gemini_model: str = 'gemini-2.5-flash'
    groq_model: str = 'qwen/qwen3-32b'
    usage_retention_days: int = Field(90, ge=1, le=3650)
    input_usd_per_million: float | None = Field(None, ge=0)
    output_usd_per_million: float | None = Field(None, ge=0)

    @model_validator(mode='after')
    def validate_deadline(self):
        if self.deadline_seconds + 5 >= self.lease_seconds:
            raise ValueError('Lease must exceed request deadline by more than 5 seconds')
        return self
