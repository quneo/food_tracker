"""Prompt text sent to Codex: fixed instructions, then the person's context."""

from functools import cache
from importlib import resources


@cache
def template(name: str) -> str:
    return resources.files("app.ai").joinpath(f"templates/{name}.md").read_text(encoding="utf-8")


def instructions() -> str:
    return template("assistant")


def assemble(context: str, mode: str = "turn") -> str:
    """mode "review" adds the instructions for a review of the recent days, "web" those
    for a meal sent from the site's form."""
    parts = [instructions().strip()]
    if mode in ("review", "web"):
        parts.append(template(mode).strip())
    return "\n\n".join(parts) + f"\n\n# Context\n\n{context}\n"
