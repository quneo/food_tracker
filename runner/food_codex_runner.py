#!/usr/bin/env python3
"""Runs one food tracker request through Codex CLI and prints the answer as JSON.

Installed on the VPS as the forced command of the backend's SSH key, so that key can do
nothing else. Python standard library only.

stdin:  {"version": 1, "prompt": str, "schema": {...}, "images": [base64, ...],
         "model": str | null, "effort": str | null, "timeout": int}
stdout: {"ok": true, "output": {...}, "model": str | null, "usage": {...},
         "duration_ms": int}
     or {"ok": false, "error": code, "message": str}

Photos live only in a private temporary directory for the duration of the call and are
deleted afterwards. Codex runs with its own CODEX_HOME (config without shell, web search
or other tools), a read-only sandbox, no session files, in an empty working directory.
The command line is built from fixed parts; request text only ever goes to stdin.
"""

import base64
import binascii
import contextlib
import errno
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HOME = os.path.expanduser("~")
CODEX = os.environ.get("FOOD_RUNNER_CODEX") or shutil.which("codex") or "codex"
CODEX_HOME = os.environ.get("FOOD_RUNNER_CODEX_HOME", os.path.join(HOME, "codex-home"))
WORK = os.environ.get("FOOD_RUNNER_WORK", os.path.join(HOME, "work"))
SLOTS = int(os.environ.get("FOOD_RUNNER_SLOTS", "2"))
SLOT_WAIT = 90  # seconds to wait for a free slot

MAX_INPUT = 48 * 1024 * 1024
MAX_PROMPT = 300_000
MAX_IMAGES = 8
MAX_IMAGE = 10 * 1024 * 1024
MAX_TIMEOUT = 900
MODEL = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
EFFORTS = {"low", "medium", "high", "xhigh"}
# Item types that mean Codex used a tool: the config forbids them, so treat as failure.
TOOL_ITEMS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}
SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp"),
)


class Failure(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message


def log(text):
    sys.stderr.write(f"food-codex-runner: {text}\n")


def answer(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()


def read_request():
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise Failure("bad_request", "request too large")
    try:
        request = json.loads(raw)
    except ValueError:
        raise Failure("bad_request", "request is not JSON") from None
    if not isinstance(request, dict) or request.get("version") != 1:
        raise Failure("bad_request", "unsupported protocol version")
    prompt = request.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise Failure("bad_request", "prompt missing or too long")
    if not isinstance(request.get("schema"), dict):
        raise Failure("bad_request", "schema must be an object")
    model = request.get("model")
    if model is not None and not (isinstance(model, str) and MODEL.match(model)):
        raise Failure("bad_request", "bad model name")
    effort = request.get("effort")
    if effort is not None and effort not in EFFORTS:
        raise Failure("bad_request", "bad reasoning effort")
    timeout = request.get("timeout", 240)
    if not isinstance(timeout, int) or not 10 <= timeout <= MAX_TIMEOUT:
        raise Failure("bad_request", "bad timeout")
    images = request.get("images") or []
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise Failure("bad_request", f"at most {MAX_IMAGES} images")
    decoded = []
    for item in images:
        try:
            data = base64.b64decode(item, validate=True)
        except (TypeError, ValueError, binascii.Error):
            raise Failure("bad_request", "image is not base64") from None
        if len(data) > MAX_IMAGE:
            raise Failure("bad_request", "image too large")
        extension = next((ext for magic, ext in SIGNATURES if data.startswith(magic)), None)
        if extension == "webp" and data[8:12] != b"WEBP":
            extension = None
        if not extension:
            raise Failure("bad_request", "images must be JPEG, PNG or WebP")
        decoded.append((data, extension))
    return prompt, request["schema"], decoded, model, effort, timeout


@contextlib.contextmanager
def slot():
    """At most SLOTS Codex processes at a time, across all SSH sessions."""
    import fcntl

    deadline = time.monotonic() + SLOT_WAIT
    while True:
        for number in range(SLOTS):
            handle = open(os.path.join(WORK, f"slot-{number}.lock"), "w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                handle.close()
                if error.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                continue
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
            return
        if time.monotonic() > deadline:
            raise Failure("busy", "all runner slots are busy")
        time.sleep(1)


def configured_model():
    try:
        with open(os.path.join(CODEX_HOME, "config.toml"), encoding="utf-8") as handle:
            for line in handle:
                match = re.match(r'^\s*model\s*=\s*"([^"]+)"', line)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return None


def parse_events(stdout):
    """Codex --json prints JSONL events; collect the answer, usage, errors and tool use."""
    text, usage, errors, tools = None, {}, [], []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        item = event.get("item") or {}
        if kind == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text")
        elif kind in ("item.started", "item.completed") and item.get("type") in TOOL_ITEMS:
            tools.append(item.get("type"))
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
        elif kind == "turn.failed":
            errors.append((event.get("error") or {}).get("message", "turn failed"))
        elif kind == "error":
            errors.append(event.get("message", "error"))
    return text, usage, errors, tools


def run_codex(prompt, schema, images, model, effort, timeout):
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="req-", dir=WORK)
    try:
        empty = os.path.join(workdir, "cwd")
        os.mkdir(empty, 0o700)
        schema_path = os.path.join(workdir, "schema.json")
        with open(schema_path, "w", encoding="utf-8") as handle:
            json.dump(schema, handle)
        last_path = os.path.join(workdir, "last.json")
        argv = [
            CODEX,
            "exec",
            "--cd",
            empty,
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--json",
            "--output-schema",
            schema_path,
            "--output-last-message",
            last_path,
        ]
        if model:
            argv += ["--model", model]
        if effort:
            argv += ["--config", f'model_reasoning_effort="{effort}"']
        for number, (data, extension) in enumerate(images, 1):
            path = os.path.join(workdir, f"photo-{number}.{extension}")
            with open(path, "wb") as handle:
                handle.write(data)
            argv += ["--image", path]
        # "--" ends the image list; "-" reads the prompt from stdin.
        argv += ["--", "-"]
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": HOME,
            "CODEX_HOME": CODEX_HOME,
            "LANG": "C.UTF-8",
            "TMPDIR": workdir,
        }
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=empty,
                env=env,
                start_new_session=True,
            )
        except FileNotFoundError:
            raise Failure("not_installed", "codex is not installed on the VPS") from None
        try:
            stdout, stderr = process.communicate(prompt.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise Failure("timeout", f"codex did not finish in {timeout} s") from None
        duration = int((time.monotonic() - started) * 1000)
        text, usage, errors, tools = parse_events(stdout.decode("utf-8", "replace"))
        if tools:
            raise Failure("tool_use", "codex used tools: " + ", ".join(sorted(set(tools))))
        if os.path.exists(last_path):
            with open(last_path, encoding="utf-8") as handle:
                text = handle.read().strip() or text
        if process.returncode != 0 or not text:
            detail = "; ".join(errors) or stderr.decode("utf-8", "replace").strip()[-400:]
            raise Failure("codex_failed", detail or f"exit code {process.returncode}")
        try:
            output = json.loads(text)
        except ValueError:
            raise Failure("bad_output", "final message is not JSON") from None
        return {
            "ok": True,
            "output": output,
            "model": model or configured_model(),
            "usage": {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            },
            "duration_ms": duration,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    started = time.monotonic()
    try:
        prompt, schema, images, model, effort, timeout = read_request()
        os.makedirs(WORK, mode=0o700, exist_ok=True)
        with slot():
            result = run_codex(prompt, schema, images, model, effort, timeout)
        log(f"ok in {result['duration_ms']} ms, {len(images)} image(s)")
        answer(result)
    except Failure as failure:
        log(f"{failure.code}: {failure.message} after {time.monotonic() - started:.1f} s")
        answer({"ok": False, "error": failure.code, "message": failure.message})
    except Exception as error:  # the backend must always get JSON
        log(f"crash: {error!r}")
        answer({"ok": False, "error": "crash", "message": type(error).__name__})


def selftest():
    """`food-codex-runner --selftest` on the VPS: one tiny call to check login and config.
    (Through SSH the forced command never gets arguments, so this is local only.)"""
    schema = {
        "type": "object",
        "properties": {"reply": {"type": "string"}},
        "required": ["reply"],
        "additionalProperties": False,
    }
    os.makedirs(WORK, mode=0o700, exist_ok=True)
    try:
        result = run_codex('Answer with {"reply": "ok"}.', schema, [], None, "low", 180)
    except Failure as failure:
        print(f"FAILED: {failure.code}: {failure.message}")
        sys.exit(1)
    print(f"OK in {result['duration_ms']} ms, model {result['model']}: {result['output']}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main()
