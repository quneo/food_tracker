from fastapi import APIRouter, BackgroundTasks, File, Response, UploadFile

from app.api.deps import CurrentUser, Db, Files, purge_later
from app.core.exceptions import DomainError
from app.media import service as media
from app.nutrition import products as service
from app.nutrition.schemas import ProductIn, ProductOut, ProductPatch

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(user: CurrentUser, db: Db, q: str | None = None):
    return [service.product_out(product) for product in service.list_products(db, user.id, q)]


@router.post("", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, user: CurrentUser, db: Db):
    if service.by_name(db, user.id, data.name):
        raise DomainError("Продукт с таким названием уже есть", 409)
    product = service.save(db, user.id, data.model_dump())
    db.commit()
    db.refresh(product)
    return service.product_out(product)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, user: CurrentUser, db: Db):
    return service.product_out(service.owned(db, product_id, user.id))


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductPatch, user: CurrentUser, db: Db):
    product = service.owned(db, product_id, user.id)
    values = data.model_dump(exclude_unset=True)
    if "name" in values:
        twin = service.by_name(db, user.id, values["name"] or "")
        if twin and twin.id != product.id:
            raise DomainError("Продукт с таким названием уже есть", 409)
    service.save(db, user.id, values, product)
    db.commit()
    db.refresh(product)
    return service.product_out(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int, user: CurrentUser, db: Db, files: Files, background: BackgroundTasks
):
    service.delete(db, service.owned(db, product_id, user.id))
    db.commit()
    purge_later(background, db, files)
    return Response(status_code=204)


@router.post("/{product_id}/photos", response_model=ProductOut)
def add_photo(product_id: int, user: CurrentUser, db: Db, files: Files, photo: UploadFile = File()):
    product = service.owned(db, product_id, user.id)
    service.upload_photo(db, files, user.id, product, photo.file.read())
    db.commit()
    db.refresh(product)
    return service.product_out(product)


@router.delete("/{product_id}/photos/{media_id}", response_model=ProductOut)
def delete_photo(
    product_id: int,
    media_id: int,
    user: CurrentUser,
    db: Db,
    files: Files,
    background: BackgroundTasks,
):
    product = service.owned(db, product_id, user.id)
    item = media.owned(db, media_id, user.id)
    if item.product_id != product.id:
        raise DomainError("Фото не относится к этому продукту", 404)
    media.drop(db, [item])
    db.commit()
    purge_later(background, db, files)
    db.refresh(product)
    return service.product_out(product)
