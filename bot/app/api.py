"""Client of the backend's bot API."""

import httpx

from app.config import settings


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class Backend:
    def __init__(self, base_url: str = settings.backend_url, transport=None):
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=60,
            headers={"X-Bot-Secret": settings.bot_api_secret},
            transport=transport,
        )

    async def call(self, method: str, path: str, telegram_id: int | None = None, **kwargs):
        headers = {"X-Telegram-User": str(telegram_id)} if telegram_id else {}
        try:
            response = await self.client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError:
            raise ApiError("Дневник сейчас недоступен. Попробуйте через минуту.") from None
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            if response.status_code == 401 and not isinstance(detail, str):
                detail = "Нажмите /start, чтобы начать."
            raise ApiError(
                detail if isinstance(detail, str) else "Что-то пошло не так. Попробуйте еще раз.",
                response.status_code,
            )
        return response.json() if response.content else None

    async def close(self):
        await self.client.aclose()


backend = Backend()
