"""Tests of the runner with a fake `codex` (POSIX only: the runner uses flock).

python -m pytest runner/test_runner.py
"""

import base64
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="the runner runs on Linux")
RUNNER = Path(__file__).with_name("food_codex_runner.py")
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64

FAKE_CODEX = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys, time
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    images = [argv[i + 1] for i, a in enumerate(argv) if a == "--image"]
    record = {"argv": argv, "prompt": prompt, "cwd": os.getcwd(),
              "images_exist": [os.path.exists(p) for p in images],
              "codex_home": os.environ.get("CODEX_HOME")}
    # The runner passes codex a clean environment: settings come through CODEX_HOME.
    home = os.environ["CODEX_HOME"]
    with open(os.path.join(home, "log.json"), "w") as f:
        json.dump(record, f)
    mode_file = os.path.join(home, "mode")
    mode = open(mode_file).read() if os.path.exists(mode_file) else "ok"
    if mode == "sleep":
        time.sleep(30)
    events = [{"type": "thread.started"}, {"type": "turn.started"}]
    if mode == "tool":
        events.append({"type": "item.completed", "item": {"type": "command_execution"}})
    if mode == "fail":
        events.append({"type": "turn.failed", "error": {"message": "not logged in"}})
        print("\\n".join(json.dumps(e) for e in events))
        sys.exit(1)
    answer = json.dumps({"reply": "ok", "actions": []})
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": answer}})
    events.append({"type": "turn.completed",
                   "usage": {"input_tokens": 1200, "cached_input_tokens": 1000,
                             "output_tokens": 80, "reasoning_output_tokens": 30,
                             "total_tokens": 1280}})
    out = argv[argv.index("--output-last-message") + 1]
    with open(out, "w") as f:
        f.write(answer)
    print("\\n".join(json.dumps(e) for e in events))
    """
)


@pytest.fixture
def env(tmp_path):
    codex = tmp_path / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text('model = "gpt-test"\n')
    return {
        **os.environ,
        "FOOD_RUNNER_CODEX": str(codex),
        "FOOD_RUNNER_CODEX_HOME": str(home),
        "FOOD_RUNNER_WORK": str(tmp_path / "work"),
    }


def run(env, request, mode="ok"):
    Path(env["FOOD_RUNNER_CODEX_HOME"], "mode").write_text(mode)
    process = subprocess.run(
        [sys.executable, str(RUNNER)],
        input=json.dumps(request).encode(),
        capture_output=True,
        env=env,
        timeout=60,
    )
    return json.loads(process.stdout)


def codex_log(env) -> Path:
    return Path(env["FOOD_RUNNER_CODEX_HOME"], "log.json")


def request(**changes):
    return {
        "version": 1,
        "prompt": "Пользователь: '; rm -rf / #",
        "schema": {"type": "object"},
        "images": [base64.b64encode(JPEG).decode()],
        "model": None,
        "effort": "low",
        "timeout": 20,
        **changes,
    }


def test_runs_codex_without_putting_text_on_the_command_line(env):
    answer = run(env, request())
    assert answer["ok"] and answer["output"] == {"reply": "ok", "actions": []}
    assert answer["model"] == "gpt-test"
    assert answer["usage"] == {
        "input_tokens": 1200,
        "cached_input_tokens": 1000,
        "output_tokens": 80,
        "reasoning_output_tokens": 30,
    }
    log = json.loads(codex_log(env).read_text())
    argv = log["argv"]
    assert argv[:2] == ["exec", "--cd"] and argv[-2:] == ["--", "-"]
    for flag in ("--ephemeral", "--skip-git-repo-check", "--json", "--output-schema"):
        assert flag in argv
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert 'model_reasoning_effort="low"' in argv
    assert log["prompt"].startswith("Пользователь") and not any("rm -rf" in a for a in argv)
    assert log["images_exist"] == [True] and log["codex_home"] == env["FOOD_RUNNER_CODEX_HOME"]
    # Photos and the working directory are gone after the call.
    assert list(Path(env["FOOD_RUNNER_WORK"]).glob("req-*")) == []


def test_rejects_bad_requests(env):
    assert run(env, request(images=["bm90IGFuIGltYWdl"]))["error"] == "bad_request"
    assert run(env, request(model="gpt; rm -rf /"))["error"] == "bad_request"
    assert run(env, request(version=2))["error"] == "bad_request"
    assert not codex_log(env).exists()  # codex never started


def test_reports_codex_failures(env):
    failed = run(env, request(), mode="fail")
    assert failed == {"ok": False, "error": "codex_failed", "message": "not logged in"}
    assert run(env, request(), mode="tool")["error"] == "tool_use"
    slow = run(env, request(timeout=10), mode="sleep")
    assert slow["error"] == "timeout"
    assert list(Path(env["FOOD_RUNNER_WORK"]).glob("req-*")) == []
