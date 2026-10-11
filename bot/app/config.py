from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: str
    # socks5://host:port when Telegram is reachable only through a proxy.
    telegram_proxy: str | None = None
    bot_api_secret: str = Field(min_length=32)
    backend_url: str = "http://backend:8000/api"
    # The web app (https).
    public_url: str | None = None
    # Put the web app on the chat's menu button (a Mini App). Off: the button would show
    # the site's address to anyone who opens the bot.
    menu_button: bool = False
    outbox_interval: float = 1.5

    @field_validator("telegram_proxy", "public_url", mode="before")
    @classmethod
    def empty_is_none(cls, value):
        return value or None


settings = Settings()
