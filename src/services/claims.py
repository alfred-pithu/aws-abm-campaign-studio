"""Load brand rules, claims, products, and assets.

Products and claims are JSON files in data/. This is a file-backed registry,
not a DAM, CRM, or vector store.
"""

import json
import re
from functools import lru_cache

from src.config import get_settings
from src.models.assets import AssetRecord
from src.models.campaign import BrandRules, ProductClaim
from src.models.product import ProductProfile, ProductProfileDraft


class DuplicateProductError(ValueError):
    """Raised when a product name is already approved."""


def clear_registry_caches() -> None:
    load_brand_rules.cache_clear()
    load_claims.cache_clear()
    load_products.cache_clear()
    load_assets.cache_clear()


def _read_json_list(path) -> list:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array")
    return data


def _write_json_list(path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=1)
def load_brand_rules() -> BrandRules:
    path = get_settings().data_dir / "brand_rules.json"
    return BrandRules.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_claims() -> list[ProductClaim]:
    path = get_settings().data_dir / "product_claims.json"
    return [ProductClaim.model_validate(item) for item in _read_json_list(path)]


@lru_cache(maxsize=1)
def load_products() -> list[ProductProfile]:
    path = get_settings().data_dir / "products.json"
    return [ProductProfile.model_validate(item) for item in _read_json_list(path)]


def save_products(products: list[ProductProfile]) -> None:
    path = get_settings().data_dir / "products.json"
    _write_json_list(path, [product.model_dump() for product in products])
    load_products.cache_clear()


def save_claims(claims: list[ProductClaim]) -> None:
    path = get_settings().data_dir / "product_claims.json"
    _write_json_list(path, [claim.model_dump() for claim in claims])
    load_claims.cache_clear()


def get_claim(claim_id: str) -> ProductClaim | None:
    for claim in load_claims():
        if claim.claim_id == claim_id:
            return claim
    return None


_PRODUCT_STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "for",
    "at",
    "of",
    "and",
    "with",
    "on",
    "promote",
}


def _normalize_product_name(product: str) -> str:
    """Treat AWS/Amazon as the same product family for registry lookup."""
    text = " ".join(product.strip().lower().split())
    text = text.replace("amazon web services", "amazon")
    tokens: list[str] = []
    for token in text.split():
        if token in _PRODUCT_STOPWORDS:
            continue
        tokens.append("amazon" if token == "aws" else token)
    return " ".join(tokens)


def approved_claims_for_product(product: str) -> list[ProductClaim]:
    needle = _normalize_product_name(product)
    if not needle:
        return []
    matched: list[ProductClaim] = []
    for claim in load_claims():
        if not claim.approved:
            continue
        name = _normalize_product_name(claim.product)
        if needle == name or needle in name or name in needle:
            matched.append(claim)
    return matched


def find_approved_product(name: str) -> ProductProfile | None:
    needle = _normalize_product_name(name)
    if not needle:
        return None
    matches: list[tuple[bool, ProductProfile]] = []
    for product in load_products():
        if product.status != "approved":
            continue
        hay = _normalize_product_name(product.name)
        if needle == hay or needle in hay or hay in needle:
            matches.append((needle == hay, product))
    if not matches:
        return None
    exact = [product for is_exact, product in matches if is_exact]
    if exact:
        return exact[0]
    return matches[0][1]


def _slugify(name: str) -> str:
    text = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return slug or "product"


def _next_product_id(name: str, existing: list[ProductProfile]) -> str:
    base = f"prod_{_slugify(name)}"
    taken = {product.product_id for product in existing}
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def approve_product(draft: ProductProfileDraft) -> ProductProfile:
    """Persist an edited draft as an approved product plus approved claims."""
    name = draft.profile.name.strip()
    if not name:
        raise ValueError("Product name is required.")
    if find_approved_product(name) is not None:
        raise DuplicateProductError(
            f"An approved profile for {name} already exists."
        )

    products = list(load_products())
    claims = list(load_claims())
    product_id = _next_product_id(name, products)
    slug = _slugify(name)
    taken_claim_ids = {claim.claim_id for claim in claims}

    approved_claims: list[ProductClaim] = []
    index = 1
    for raw in draft.claims:
        text = raw.claim.strip()
        if not text:
            continue
        while True:
            claim_id = f"{slug}_{index:03d}"
            index += 1
            if claim_id not in taken_claim_ids:
                break
        claim = ProductClaim(
            claim_id=claim_id,
            product=name,
            claim=text,
            source=raw.source.strip() or "Marketer-approved product profile",
            approved=True,
        )
        taken_claim_ids.add(claim_id)
        approved_claims.append(claim)

    profile = draft.profile.model_copy(
        update={
            "product_id": product_id,
            "name": name,
            "status": "approved",
        }
    )
    products.append(profile)
    claims.extend(approved_claims)
    save_products(products)
    save_claims(claims)
    return profile


@lru_cache(maxsize=1)
def load_assets() -> list[AssetRecord]:
    path = get_settings().data_dir / "assets.json"
    raw = path.read_text(encoding="utf-8")
    return [AssetRecord.model_validate(item) for item in json.loads(raw)]


def get_asset(asset_id: str) -> AssetRecord | None:
    for asset in load_assets():
        if asset.asset_id == asset_id:
            return asset
    return None
