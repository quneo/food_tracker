from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/food.db"
    # The bot calls the API with this secret plus the Telegram id of the person it serves.
    bot_api_secret: str = Field(min_length=32)
    # Used only to check Telegram Login and Mini App signatures; the backend never calls
    # the Telegram API itself.
    telegram_bot_token: str = Field(min_length=20)
    telegram_bot_username: str = Field(pattern=r"^[A-Za-z0-9_]{3,64}$")
    # Address of the web app, for links in the bot (e.g. https://food.example.com).
    public_url: str | None = Field(default=None, pattern=r"^(https?://\S+)?$")
    # Who may join:
    # "bastion": people sign in on the site with Bastion (groups of the project decide),
    #            then link their Telegram; the bot serves linked accounts only;
    # "invite":  new people need an invite link from an admin; "open": anyone.
    registration: Literal["bastion", "invite", "open"] = "invite"
    # Telegram ids that are admins; comma separated in the environment.
    admin_telegram_ids: str = ""
    # Bastion logins that are admins (REGISTRATION=bastion); comma separated.
    admin_usernames: str = ""

    # Bastion: the project's own sign-in form (POST /api/v1/authenticate).
    bastion_url: str | None = Field(default=None, pattern=r"^(https?://\S+)?$")
    bastion_client_id: str | None = None
    bastion_client_secret: str | None = None
    # Address people open in the browser (to bind a phone); defaults to bastion_url.
    bastion_public_url: str | None = Field(default=None, pattern=r"^(https?://\S+)?$")
    default_timezone: str = "Asia/Krasnoyarsk"
    session_days: int = 30
    cookie_secure: bool = False

    # Photo storage: MinIO (any S3 API).
    s3_endpoint: str = "minio:9000"
    s3_access_key: str = Field(min_length=3)
    s3_secret_key: str = Field(min_length=8)
    s3_bucket: str = "food-tracker"
    s3_secure: bool = False
    max_upload_mb: int = 15

    # AI: Codex CLI behind the runner (runner/food_codex_runner.py).
    # "ssh" runs it on the VPS, "local" runs the runner on this machine, "off" disables AI.
    ai_runner: Literal["ssh", "local", "off"] = "off"
    ai_ssh_target: str | None = Field(default=None, pattern=r"^([\w.-]+@[\w.-]+)?$")
    ai_ssh_port: int = 22
    ai_ssh_key: str = "/run/codex-ssh/id_ed25519"
    ai_ssh_known_hosts: str = "/run/codex-ssh/known_hosts"
    ai_local_runner: str = "runner/food_codex_runner.py"
    ai_model: str | None = Field(default=None, pattern=r"^([\w.:-]+)?$")
    ai_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    ai_timeout: int = Field(default=240, ge=30, le=900)
    ai_max_parallel: int = Field(default=2, ge=1, le=8)

    @field_validator(
        "ai_ssh_target",
        "ai_model",
        "public_url",
        "bastion_url",
        "bastion_client_id",
        "bastion_client_secret",
        "bastion_public_url",
        mode="before",
    )
    @classmethod
    def empty_is_none(cls, value):
        return value or None

    @property
    def admin_ids(self) -> set[int]:
        return {int(part) for part in self.admin_telegram_ids.replace(" ", "").split(",") if part}

    @property
    def admin_logins(self) -> set[str]:
        return {part.strip().lower() for part in self.admin_usernames.split(",") if part.strip()}

    @property
    def bastion_ready(self) -> bool:
        return bool(self.bastion_url and self.bastion_client_id and self.bastion_client_secret)

    @property
    def bastion_link(self) -> str | None:
        url = self.bastion_public_url or self.bastion_url
        return url.rstrip("/") if url else None

    @property
    def app_url(self) -> str | None:
        return self.public_url.rstrip("/") if self.public_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
