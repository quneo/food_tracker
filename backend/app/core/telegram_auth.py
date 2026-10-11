"""Checks of data signed by Telegram with the bot token.

Login Widget: https://core.telegram.org/widgets/login#checking-authorization
Mini Apps:    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE = 24 * 3600


class InvalidSignature(Exception):
    pass


def _check(fields: dict[str, str], secret: bytes, max_age: int, now: float | None) -> None:
    received = fields.pop("hash", "")
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(expected, received):
        raise InvalidSignature("bad hash")
    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError):
        raise InvalidSignature("no auth_date") from None
    if (now or time.time()) - auth_date > max_age:
        raise InvalidSignature("expired")


def check_widget(data: dict, bot_token: str, max_age: int = MAX_AGE, now=None) -> dict:
    """Login Widget payload -> {"id", "first_name", ...}."""
    fields = {key: str(value) for key, value in data.items() if value is not None}
    _check(fields, hashlib.sha256(bot_token.encode()).digest(), max_age, now)
    return {**fields, "id": int(fields["id"])}


def check_webapp(init_data: str, bot_token: str, max_age: int = MAX_AGE, now=None) -> dict:
    """Mini App initData query string -> the "user" object."""
    # Every field except "hash" is signed, "signature" (for third parties) included.
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    _check(fields, secret, max_age, now)
    try:
        user = json.loads(fields["user"])
        user["id"] = int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise InvalidSignature("no user") from None
    return user
