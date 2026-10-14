"""Approved product catalog models. Claims stay on ProductClaim."""

from typing import Literal

from pydantic import BaseModel, Field

from src.models.campaign import ProductClaim


class ProductProfile(BaseModel):
    product_id: str
    name: str
    short_description: str = ""
    category: str = ""
    capabilities: list[str] = Field(default_factory=list)
    target_audiences: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    source_url: str = ""
    status: Literal["draft", "approved"] = "draft"


class ProductProfileDraft(BaseModel):
    profile: ProductProfile
    claims: list[ProductClaim] = Field(default_factory=list)
    insufficient_source: bool = False
    warning: str = ""
