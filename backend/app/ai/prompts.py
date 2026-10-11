"""Prompt text sent to Codex: fixed instructions, then the person's context."""

from functools import cache
from importlib import resources


@cache
def instructions() -> str:
    return resources.files("app.ai").joinpath("templates/assistant.md").read_text(encoding="utf-8")


def assemble(context: str) -> str:
    return f"{instructions().strip()}\n\n# Context\n\n{context}\n"
