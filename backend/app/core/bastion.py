"""Minimal Bastion client for projects that keep their own sign-in form.

Copied from bastion-auth/clients/python/bastion_auth_client.py (standard library only).
Local changes: network failures raise BastionUnavailable, error bodies without a
``detail.code`` object are tolerated.
"""

import base64
import json
import urllib.error
import urllib.request
from urllib.parse import quote


class BastionError(Exception):
    def __init__(self, status: int, code: str, retry_after: int | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.retry_after = retry_after


class BastionUnavailable(Exception):
    """Bastion could not be reached or answered with something that is not JSON."""


class BastionClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        credentials = f"{quote(client_id, safe='')}:{quote(client_secret, safe='')}"
        self._auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read() or b"null")
        except urllib.error.HTTPError as err:
            try:
                detail = json.loads(err.read()).get("detail")
            except (ValueError, AttributeError):
                detail = None
            if not isinstance(detail, dict):
                detail = {}
            raise BastionError(
                err.code, detail.get("code", "error"), detail.get("retry_after")
            ) from None
        except (OSError, ValueError) as err:
            # URLError, timeouts, refused connections and non-JSON answers.
            raise BastionUnavailable(str(err)) from None

    def authenticate(
        self, username: str, password: str, totp_code: str | None, end_user_ip: str | None = None
    ) -> dict:
        """Checks password and the code from the authenticator app. Returns the user."""
        headers = {"X-Bastion-End-User-IP": end_user_ip} if end_user_ip else None
        body = {"username": username, "password": password, "totp_code": totp_code}
        return self._call("POST", "/api/v1/authenticate", body, headers)["user"]

    def users(self) -> list[dict]:
        """Everyone who is allowed into this project."""
        return self._call("GET", "/api/v1/users")

    def user(self, user_id: str) -> dict:
        return self._call("GET", f"/api/v1/users/{quote(user_id, safe='')}")
