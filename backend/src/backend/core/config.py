from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=15432, ge=1, le=65535)
    postgres_user: str = "ai_agent"
    postgres_password: SecretStr = Field(min_length=1)
    postgres_db: str = "ai_agent"

    redis_host: str = "127.0.0.1"
    redis_port: int = Field(default=16379, ge=1, le=65535)
    redis_password: SecretStr = Field(min_length=1)
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_port: int = Field(default=15673, ge=1, le=65535)
    rabbitmq_user: str = "ai_agent"
    rabbitmq_vhost: str = "ai_agent_dev"
    rabbitmq_password: SecretStr = Field(min_length=1)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def checkpoint_url(self) -> str:
        return self.database_url.render_as_string(hide_password=False).replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    @property
    def celery_broker_url(self) -> str:
        user = quote(self.rabbitmq_user, safe="")
        password = quote(self.rabbitmq_password.get_secret_value(), safe="")
        vhost = quote(self.rabbitmq_vhost, safe="")
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{vhost}"

    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    app_url: str = "http://localhost:9988"
    smtp_security: Literal["ssl", "starttls"] = "ssl"
    email_verification_secret: SecretStr = SecretStr("")
    imap_owner_id: str = ""
    imap_host: str = ""
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_username: str = ""
    imap_password: SecretStr = SecretStr("")
    imap_folder: str = "INBOX"
    ocr_model: str = ""

    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    assistant_summary_queue: str = "assistant-summary"
    ai_max_active_runs: int = Field(default=1, ge=1, le=1000)
    ai_chat_per_minute: int = Field(default=20, ge=1, le=1000000)
    ai_chat_per_day: int = Field(default=200, ge=1, le=1000000)
    ai_transcription_per_minute: int = Field(default=10, ge=1, le=1000000)
    ai_transcription_per_day: int = Field(default=100, ge=1, le=1000000)
    ai_reindex_per_minute: int = Field(default=1, ge=1, le=1000000)
    ai_reindex_per_day: int = Field(default=10, ge=1, le=1000000)
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANG_SMITH_API_KEY"),
    )
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = ""
    langsmith_workspace_id: str = ""
    embedding_model: str = ""
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    transcription_model: str = ""
    transcription_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    transcription_api_key: SecretStr = SecretStr("")

    app_env: str = "development"
    email_scheduler_enabled: bool = True
    cookie_secure: bool = True
    allowed_origins: list[str] = ["http://localhost:9988", "http://127.0.0.1:9988"]
    trusted_proxies: list[str] = []
    redis_namespace: str = "ai-agent:"
    cursor_secret: SecretStr = Field(min_length=32)

    @model_validator(mode="after")
    def secure_cookie(self):
        if not self.cookie_secure and self.app_env != "development":
            raise ValueError("仅 development 允许关闭 Secure Cookie")
        if "*" in self.allowed_origins:
            raise ValueError("Origin必须精确指定")
        return self
