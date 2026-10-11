"""Calls the Codex runner (runner/food_codex_runner.py) over SSH or locally.

The request is one JSON document on stdin; the command line is fixed and never contains
anything the person wrote. On the VPS the SSH key is bound to the runner with a forced
command, so this key cannot start anything else there."""

import asyncio
import base64
import json
import logging
import sys
import time
from dataclasses import dataclass

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
PROTOCOL = 1


class RunnerError(Exception):
    def __init__(self, code: str, message: str = "", transient: bool = False):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.transient = transient


@dataclass
class RunnerResult:
    output: dict
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


def command(settings: Settings) -> list[str]:
    if settings.ai_runner == "local":
        return [sys.executable, settings.ai_local_runner]
    if not settings.ai_ssh_target:
        raise RunnerError("not_configured", "AI_SSH_TARGET is empty")
    return [
        "ssh",
        "-T",
        "-p",
        str(settings.ai_ssh_port),
        "-i",
        settings.ai_ssh_key,
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"UserKnownHostsFile={settings.ai_ssh_known_hosts}",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=20",
        "-o",
        "ServerAliveCountMax=3",
        settings.ai_ssh_target,
        # Ignored by the forced command on the VPS; names the action for the logs.
        "run",
    ]


def request(prompt: str, schema: dict, images: list[bytes], settings: Settings) -> dict:
    return {
        "version": PROTOCOL,
        "prompt": prompt,
        "schema": schema,
        "images": [base64.b64encode(image).decode() for image in images],
        "model": settings.ai_model,
        "effort": settings.ai_reasoning_effort,
        "timeout": settings.ai_timeout,
    }


async def run(prompt: str, schema: dict, images: list[bytes]) -> RunnerResult:
    settings = get_settings()
    if settings.ai_runner == "off":
        raise RunnerError("off", "AI is turned off")
    body = json.dumps(request(prompt, schema, images, settings)).encode()
    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *command(settings),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise RunnerError("start_failed", str(error), transient=True) from error
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(body), timeout=settings.ai_timeout + 30
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RunnerError("timeout", "runner did not answer in time", transient=True) from None
    duration = int((time.monotonic() - started) * 1000)
    try:
        answer = json.loads(stdout)
    except ValueError:
        # 255 is ssh's own failure (network, key, host key): worth another try.
        message = stderr.decode(errors="replace").strip()[-300:]
        raise RunnerError(
            "ssh" if process.returncode == 255 else "bad_answer",
            message,
            transient=process.returncode == 255,
        ) from None
    if not answer.get("ok"):
        code = answer.get("error", "failed")
        raise RunnerError(
            code, answer.get("message", ""), transient=code in {"busy", "timeout", "codex_failed"}
        )
    usage = answer.get("usage") or {}
    log.info("runner answered in %d ms (model %s)", duration, answer.get("model"))
    return RunnerResult(
        output=answer["output"],
        model=answer.get("model"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        duration_ms=duration,
    )
