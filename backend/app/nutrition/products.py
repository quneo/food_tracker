"""Saved products: the person's own milk, bars, yogurts with numbers from their labels.

The assistant refers to them by id; the meal's numbers are then computed here from the
label (per 100 g) and the amount, not guessed."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import utc_iso
from app.database import utcnow
from app.media import service as media
from app.media.models import Media
from app.media.storage import Storage
from app.nutrition.models import Product

MAX_PRODUCTS = 500
MAX_PHOTOS = 4
FIELDS = (
    "name",
    "brand",
    "kcal",
    "protein",
    "fat",
    "carbs",
    "portion_name",
    "portion_grams",
    "package_grams",
    "comment",
)


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower().replace("ё", "е"))


def product_out(product: Product) -> dict:
    return {
        **{field: getattr(product, field) for field in FIELDS},
        "id": product.id,
        "uses": product.uses,
        "last_used_at": utc_iso(product.last_used_at),
        "created_at": utc_iso(product.created_at),
        "photos": product.photos,
    }


def owned(db: Session, product_id: int, user_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product or product.user_id != user_id:
        raise NotFound("Продукт не найден")
    return product


def owned_ids(db: Session, user_id: int, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    return set(
        db.scalars(select(Product.id).where(Product.user_id == user_id, Product.id.in_(ids)))
    )


def list_products(db: Session, user_id: int, q: str | None = None) -> list[Product]:
    query = select(Product).where(Product.user_id == user_id)
    products = list(db.scalars(query.order_by(Product.uses.desc(), Product.name)))
    # SQLite's lower() knows only ASCII: match Cyrillic here (a person has few products).
    if q and q.strip():
        wanted = norm(q)
        products = [p for p in products if wanted in norm(f"{p.name} {p.brand or ''}")]
    return products


def by_name(db: Session, user_id: int, name: str) -> Product | None:
    wanted = norm(name)
    for product in db.scalars(select(Product).where(Product.user_id == user_id)):
        if norm(product.name) == wanted:
            return product
    return None


def save(db: Session, user_id: int, values: dict, product: Product | None = None) -> Product:
    """Creates a product, or changes the given one with the fields in `values`."""
    if product is None:
        count = db.scalar(select(func.count(Product.id)).where(Product.user_id == user_id))
        if count >= MAX_PRODUCTS:
            raise DomainError(f"Продуктов уже {MAX_PRODUCTS}. Удалите ненужные")
        product = Product(user_id=user_id)
        db.add(product)
    for field, value in values.items():
        if field not in FIELDS:
            continue
        if isinstance(value, str):
            value = " ".join(value.split()) or None
        if field == "name" and not value:
            raise DomainError("У продукта должно быть название")
        setattr(product, field, value)
    if product.kcal is None:
        product.kcal = 0
    db.flush()
    return product


def scaled(product: Product, grams: float) -> dict:
    """The product's numbers for this amount (values are per 100 g)."""
    share = grams / 100
    return {
        "kcal": round(product.kcal * share, 1),
        "protein": round(product.protein * share, 1),
        "fat": round(product.fat * share, 1),
        "carbs": round(product.carbs * share, 1),
    }


def used(product: Product):
    product.uses += 1
    product.last_used_at = utcnow()


def attach(db: Session, product: Product, items: list[Media]):
    """Photos from a chat message become the product's label photos."""
    room = MAX_PHOTOS - len(product.photos)
    for item in items[: max(room, 0)]:
        item.kind = "product"
        item.product_id = product.id
        item.meal_id = None
    db.flush()


def upload_photo(db: Session, storage: Storage, user_id: int, product: Product, data: bytes):
    if len(product.photos) >= MAX_PHOTOS:
        raise DomainError(f"К продукту — не больше {MAX_PHOTOS} фото")
    item = media.save_photo(db, storage, user_id, data, "product")
    item.product_id = product.id
    db.flush()
    return item


def delete(db: Session, product: Product):
    media.drop(db, list(product.photos))
    db.delete(product)


def describe(product: Product) -> str:
    """For the bot: «Молоко 2,5%: 52 ккал, Б 2,9, Ж 2,5, У 4,7 на 100 г»."""

    def n(value):
        return f"{value:g}".replace(".", ",")

    return (
        f"«{product.name}»: {n(product.kcal)} ккал, Б {n(product.protein)}, "
        f"Ж {n(product.fat)}, У {n(product.carbs)} на 100 г"
    )
