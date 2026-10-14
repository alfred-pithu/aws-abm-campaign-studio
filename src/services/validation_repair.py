"""Deterministic validation repair helpers. No LLM calls."""

from __future__ import annotations

import re

from src.agents.content_agent import attach_approved_claim_ids, enforce_content_limits
from src.models.campaign import BrandRules, CampaignStrategy, ProductClaim
from src.models.content import EmailContent
from src.models.validation import CheckStatus, ValidationCheck, ValidationResult

CONTENT_CHECKS = {
    "required_fields",
    "brand_forbidden_phrases",
    "cta_present",
    "character_limits",
    "claims",
}
ASSET_CHECK = "asset"


def failed_checks(result: ValidationResult) -> list[ValidationCheck]:
    return [check for check in result.checks if check.status == CheckStatus.FAIL]


def content_failure_names(checks: list[ValidationCheck]) -> set[str]:
    return {check.check for check in checks if check.check in CONTENT_CHECKS}


def asset_only_failures(checks: list[ValidationCheck]) -> bool:
    names = {check.check for check in checks}
    return bool(names) and names <= {ASSET_CHECK}


def format_repair_feedback(
    checks: list[ValidationCheck],
    brand_rules: BrandRules,
) -> str:
    failed = [check for check in checks if check.status == CheckStatus.FAIL]
    if not failed:
        return ""
    lines = ["Validation failed. Fix the copy so every check passes. Do not invent facts."]
    names = {check.check for check in failed}
    if "brand_forbidden_phrases" in names:
        avoid = ", ".join(brand_rules.avoid)
        lines.append(f"Remove forbidden phrases: {avoid}.")
    for check in failed:
        lines.append(f"- {check.check}: {check.details}")
    lines.append("Keep approved claim IDs only. Do not invent product claims.")
    return "\n".join(lines)


def _scrub_forbidden(text: str, phrases: list[str]) -> str:
    result = text
    for phrase in sorted(phrases, key=len, reverse=True):
        cleaned = phrase.strip()
        if not cleaned:
            continue
        result = re.sub(rf"\b{re.escape(cleaned)}\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    return result.strip()


def apply_deterministic_content_fixes(
    content: EmailContent,
    claims: list[ProductClaim],
    strategy: CampaignStrategy,
    brand_rules: BrandRules,
) -> EmailContent:
    updated = content.model_copy(deep=True)
    avoid = brand_rules.avoid
    updated.subject = _scrub_forbidden(updated.subject, avoid)
    updated.preheader = _scrub_forbidden(updated.preheader, avoid)
    updated.headline = _scrub_forbidden(updated.headline, avoid)
    updated.cta_text = _scrub_forbidden(updated.cta_text, avoid)
    paragraphs = [_scrub_forbidden(paragraph, avoid) for paragraph in updated.body_paragraphs]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    updated.body_paragraphs = paragraphs or [""]
    updated = attach_approved_claim_ids(updated, claims, strategy.required_claims)
    return enforce_content_limits(updated, strategy.recommended_cta)
