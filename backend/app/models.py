"""Every table, imported in one place for Alembic and create_all."""

from app.ai.models import AiJob, MemoryFact
from app.chat.models import ChatMessage, ChatState, OutboxMessage, PendingAction
from app.media.models import Media, PendingDeletion
from app.nutrition.models import DayMark, Meal, MealItem, Product
from app.progress.models import Measurement, ProgressEntry, ProgressPhoto, WeightEntry
from app.reminders.models import Reminder
from app.users.models import Invite, LoginRequest, Profile, User, WebSession

__all__ = [
    "AiJob",
    "ChatMessage",
    "ChatState",
    "DayMark",
    "Invite",
    "LoginRequest",
    "Meal",
    "MealItem",
    "Measurement",
    "Media",
    "MemoryFact",
    "OutboxMessage",
    "PendingAction",
    "PendingDeletion",
    "Product",
    "Profile",
    "ProgressEntry",
    "ProgressPhoto",
    "Reminder",
    "User",
    "WebSession",
    "WeightEntry",
]
