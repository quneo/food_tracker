class DomainError(Exception):
    """An error with a message for people; the API returns it as {"detail": message}."""

    def __init__(self, message: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra or {}


class NotFound(DomainError):
    def __init__(self, message: str = "Запись не найдена"):
        super().__init__(message, 404)
