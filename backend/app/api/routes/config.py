from datetime import datetime

from ..fastapi_compat import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..common import db_session, dt, error, json_body
from ...models.config import ProductType, Recipe, RecipeMaterial

config_bp = Blueprint("config", __name__, url_prefix="/api/config")


@config_bp.get("/product-types")
def list_product_types():
    with db_session() as db:
        rows = db.execute(select(ProductType).order_by(ProductType.name.asc())).scalars().all()

    return jsonify([row.name for row in rows])


def _serialize_product_type(product_type: ProductType) -> dict:
    return {
        "id": product_type.id,
        "name": product_type.name,
        "created_at": dt(product_type.created_at),
        "last_modified_at": dt(product_type.last_modified_at or product_type.created_at),
    }


@config_bp.get("/product-types/manage")
def list_product_types_manage():
    with db_session() as db:
        rows = db.execute(select(ProductType).order_by(ProductType.name.asc())).scalars().all()

    return jsonify([_serialize_product_type(row) for row in rows])


@config_bp.post("/product-types")
def add_product_type():
    return error("Product type is created from recipes. Add or rename recipe instead.")


@config_bp.put("/product-types/<int:product_type_id>")
def update_product_type(product_type_id: int):
    name = request.args.get("name", "").strip()
    if not name:
        return error("Product type name is required")

    with db_session() as db:
        row = db.get(ProductType, product_type_id)
        if not row:
            return error("Product type not found", 404)

        existing = (
            db.execute(
                select(ProductType).where(
                    func.lower(ProductType.name) == name.lower(),
                    ProductType.id != product_type_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if existing:
            return error("Product type already exists")

        row.name = name
        row.last_modified_at = datetime.utcnow()
        db.flush()
        return jsonify(_serialize_product_type(row))


@config_bp.delete("/product-types/<int:product_type_id>")
def delete_product_type(product_type_id: int):
    with db_session() as db:
        row = db.get(ProductType, product_type_id)
        if not row:
            return error("Product type not found", 404)

        db.delete(row)
        db.flush()
        return jsonify({"id": product_type_id, "deleted": True})


def _parse_recipe_materials(materials: object) -> list[dict]:
    if not isinstance(materials, list) or len(materials) == 0:
        raise ValueError("materials is required and must be a non-empty list")

    parsed: list[dict] = []
    seen_rm_names: set[str] = set()
    for index, item in enumerate(materials, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"materials[{index}] must be an object")

        rm_name = str(item.get("rm_name") or "").strip()
        if not rm_name:
            raise ValueError(f"materials[{index}].rm_name is required")
        rm_key = rm_name.lower()
        if rm_key in seen_rm_names:
            raise ValueError(f"materials[{index}].rm_name is duplicated")
        seen_rm_names.add(rm_key)

        try:
            quantity = float(
                item.get("quantity")
                if item.get("quantity") not in (None, "")
                else item.get("percentage")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"materials[{index}].quantity must be a number") from exc
        if quantity <= 0:
            raise ValueError(f"materials[{index}].quantity must be greater than 0")

        parsed.append({"rm_name": rm_name, "quantity": quantity})

    return parsed


def _serialize_recipe(recipe: Recipe) -> dict:
    return {
        "id": recipe.id,
        "name": recipe.name,
        "created_at": dt(recipe.created_at),
        "last_modified_at": dt(recipe.last_modified_at or recipe.created_at),
        "materials": [
            {
                "id": item.id,
                "recipe_id": item.recipe_id,
                "rm_name": item.rm_name,
                "quantity": item.quantity,
                "created_at": dt(item.created_at),
            }
            for item in sorted(recipe.materials, key=lambda value: value.id)
        ],
    }


@config_bp.get("/recipes")
def list_recipes():
    with db_session() as db:
        rows = (
            db.execute(select(Recipe).options(selectinload(Recipe.materials)).order_by(Recipe.name.asc()))
            .scalars()
            .all()
        )
    return jsonify([_serialize_recipe(row) for row in rows])


@config_bp.post("/recipes")
def add_recipe():
    try:
        payload = json_body()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        materials = _parse_recipe_materials(payload.get("materials"))
    except ValueError as exc:
        return error(str(exc))

    with db_session() as db:
        existing_recipe = (
            db.execute(select(Recipe).where(func.lower(Recipe.name) == name.lower()))
            .scalars()
            .one_or_none()
        )
        if existing_recipe:
            return error("Recipe name already exists")

        recipe = Recipe(name=name, last_modified_at=datetime.utcnow())
        db.add(recipe)
        db.flush()

        for item in materials:
            db.add(
                RecipeMaterial(
                    recipe_id=recipe.id,
                    rm_name=item["rm_name"],
                    quantity=item["quantity"],
                )
            )

        # Keep legacy product type list in sync.
        existing_product_type = (
            db.execute(select(ProductType).where(func.lower(ProductType.name) == name.lower()))
            .scalars()
            .one_or_none()
        )
        if not existing_product_type:
            db.add(ProductType(name=name, last_modified_at=datetime.utcnow()))

        db.flush()
        db.refresh(recipe)
        recipe = (
            db.execute(select(Recipe).options(selectinload(Recipe.materials)).where(Recipe.id == recipe.id))
            .scalars()
            .one()
        )
        return jsonify(_serialize_recipe(recipe))


@config_bp.put("/recipes/<int:recipe_id>")
def update_recipe(recipe_id: int):
    try:
        payload = json_body()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        materials = _parse_recipe_materials(payload.get("materials"))
    except ValueError as exc:
        return error(str(exc))

    with db_session() as db:
        recipe = db.get(Recipe, recipe_id)
        if not recipe:
            return error("Recipe not found", 404)

        existing_recipe = (
            db.execute(
                select(Recipe).where(
                    func.lower(Recipe.name) == name.lower(),
                    Recipe.id != recipe_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if existing_recipe:
            return error("Recipe name already exists")

        recipe.name = name
        recipe.last_modified_at = datetime.utcnow()

        for row in list(recipe.materials):
            db.delete(row)
        db.flush()

        for item in materials:
            db.add(
                RecipeMaterial(
                    recipe_id=recipe.id,
                    rm_name=item["rm_name"],
                    quantity=item["quantity"],
                )
            )

        # Ensure product type exists for dispatch/stock usage.
        existing_product_type = (
            db.execute(select(ProductType).where(func.lower(ProductType.name) == name.lower()))
            .scalars()
            .one_or_none()
        )
        if not existing_product_type:
            db.add(ProductType(name=name, last_modified_at=datetime.utcnow()))

        db.flush()
        recipe = (
            db.execute(select(Recipe).options(selectinload(Recipe.materials)).where(Recipe.id == recipe.id))
            .scalars()
            .one()
        )
        return jsonify(_serialize_recipe(recipe))


@config_bp.delete("/recipes/<int:recipe_id>")
def delete_recipe(recipe_id: int):
    with db_session() as db:
        recipe = db.get(Recipe, recipe_id)
        if not recipe:
            return error("Recipe not found", 404)

        db.delete(recipe)

        db.flush()
        return jsonify({"id": recipe_id, "deleted": True})
