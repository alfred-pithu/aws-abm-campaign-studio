"""Load static brand rules, claims, and assets from local JSON files.

This is a file-backed registry, not a DAM, CRM, or vector store.
"""

import json
from functools import lru_cache

from src.config import get_settings
from src.models.assets import AssetRecord
from src.models.campaign import BrandRules, ProductClaim


@lru_cache(maxsize=1)
def load_brand_rules() -> BrandRules:
    path = get_settings().data_dir / "brand_rules.json"
    return BrandRules.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_claims() -> list[ProductClaim]:
    path = get_settings().data_dir / "product_claims.json"
    raw = path.read_text(encoding="utf-8")
    return [ProductClaim.model_validate(item) for item in json.loads(raw)]


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
