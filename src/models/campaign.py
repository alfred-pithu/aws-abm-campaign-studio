from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    PREVIEW = "PREVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REVISION = "REVISION"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"


class CampaignBrief(BaseModel):
    campaign_id: str
    product: str
    audience: str
    goal: str
    channel: Literal["email"] = "email"
    tone: str
    key_message: str
    additional_context: str = ""


class CampaignStrategy(BaseModel):
    audience: str
    content_angle: str
    key_points: list[str]
    recommended_cta: str
    required_claims: list[str]
    tone_guidance: str
    content_constraints: list[str]


class AuditEvent(BaseModel):
    timestamp: datetime
    event: str
    agent: str | None = None
    version: int
    details: str | None = None


class BrandRules(BaseModel):
    brand_name: str
    tone: list[str]
    avoid: list[str]
    writing_rules: list[str]
    cta_style: str


class ProductClaim(BaseModel):
    claim_id: str
    product: str
    claim: str
    source: str
    approved: bool
