"""Long-term memory: facts about the person, and picking the ones that matter now."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import MEMORY_CATEGORIES, MemoryFact
from app.core.exceptions import DomainError, NotFound
from app.database import utcnow

MAX_FACTS = 300
ALL_UP_TO = 40  # fewer facts than this: the assistant sees all of them
# Always relevant: what is unsafe, what the person is after, and how they like to be
# talked to.
CORE = {"allergy", "health", "goal", "dislike", "preference"}
WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
ENDINGS = re.compile(
    r"(ами|ями|ого|его|ому|ему|ыми|ими|ах|ях|ов|ев|ей|ой|ий|ый|ая|яя|ое|ее|ом|ем|ую|юю|"
    r"ам|ям|ы|и|а|я|о|е|у|ю|ь)$"
)


def stems(text: str) -> set[str]:
    """Crude Russian stems: enough to match "гречку" with "гречка"."""
    words = (word.lower().replace("ё", "е") for word in WORD.findall(text))
    return {ENDINGS.sub("", word)[:6] for word in words if len(word) >= 3}


def facts(db: Session, user_id: int) -> list[MemoryFact]:
    return list(
        db.scalars(
            select(MemoryFact)
            .where(MemoryFact.user_id == user_id)
            .order_by(MemoryFact.category, MemoryFact.id)
        )
    )


def relevant(db: Session, user_id: int, message: str, limit: int = 40) -> list[MemoryFact]:
    every = facts(db, user_id)
    if len(every) <= ALL_UP_TO:
        chosen = every
    else:
        words = stems(message)
        core = [fact for fact in every if fact.category in CORE]
        others = [fact for fact in every if fact.category not in CORE]

        def score(fact: MemoryFact):
            overlap = len(words & stems(fact.text))
            used = fact.last_used_at or fact.created_at
            return (overlap, used)

        others.sort(key=score, reverse=True)
        chosen = core[: limit // 2] + others[: limit - min(len(core), limit // 2)]
    now = utcnow()
    for fact in chosen:
        fact.last_used_at = now
    return chosen


def owned(db: Session, fact_id: int, user_id: int) -> MemoryFact:
    fact = db.get(MemoryFact, fact_id)
    if not fact or fact.user_id != user_id:
        raise NotFound("Факт не найден")
    return fact


def add(db: Session, user_id: int, category: str, text: str, source: str) -> MemoryFact:
    text = " ".join(text.split())[:500]
    if not text:
        raise DomainError("Пустой факт")
    if category not in MEMORY_CATEGORIES:
        category = "other"
    existing = facts(db, user_id)
    for fact in existing:
        if fact.text.lower() == text.lower():
            return fact
    if len(existing) >= MAX_FACTS:
        raise DomainError(f"В памяти уже {MAX_FACTS} фактов. Удалите лишние на сайте")
    fact = MemoryFact(user_id=user_id, category=category, text=text, source=source)
    db.add(fact)
    db.flush()
    return fact
