"""Deterministic campaign validators. No LLM calls."""

from pathlib import Path

from src.config import PROJECT_ROOT
from src.models.assets import AssetRecord, SelectedAsset
from src.models.campaign import BrandRules, ProductClaim
from src.models.content import EmailContent
from src.models.validation import CheckStatus, ValidationCheck, ValidationResult

SUBJECT_MAX = 80
PREHEADER_MAX = 120
CTA_MAX = 40


def _text_blob(content: EmailContent) -> str:
    return " ".join(
        [
            content.subject,
            content.preheader,
            content.headline,
            content.cta_text,
            *content.body_paragraphs,
        ]
    )


def _required_fields(content: EmailContent) -> ValidationCheck:
    missing: list[str] = []
    if not content.subject.strip():
        missing.append("subject")
    if not content.headline.strip():
        missing.append("headline")
    if not any(paragraph.strip() for paragraph in content.body_paragraphs):
        missing.append("body")
    if not content.cta_text.strip():
        missing.append("cta")
    if not content.claim_ids:
        missing.append("claim_ids")
    if missing:
        return ValidationCheck(
            check="required_fields",
            status=CheckStatus.FAIL,
            details=f"Missing required fields: {', '.join(missing)}.",
        )
    return ValidationCheck(
        check="required_fields",
        status=CheckStatus.PASS,
        details="Subject, headline, body, CTA, and claim IDs are present.",
    )


def _brand_phrases(content: EmailContent, brand_rules: BrandRules) -> ValidationCheck:
    blob = _text_blob(content).lower()
    hits = [phrase for phrase in brand_rules.avoid if phrase.lower() in blob]
    if hits:
        return ValidationCheck(
            check="brand_forbidden_phrases",
            status=CheckStatus.FAIL,
            details=f"Forbidden phrases detected: {', '.join(hits)}.",
        )
    return ValidationCheck(
        check="brand_forbidden_phrases",
        status=CheckStatus.PASS,
        details="No forbidden phrases detected.",
    )


def _cta_present(content: EmailContent) -> ValidationCheck:
    if not content.cta_text.strip():
        return ValidationCheck(
            check="cta_present",
            status=CheckStatus.FAIL,
            details="CTA is missing or empty.",
        )
    return ValidationCheck(
        check="cta_present",
        status=CheckStatus.PASS,
        details="CTA is present.",
    )


def _character_limits(content: EmailContent) -> ValidationCheck:
    failures: list[str] = []
    if len(content.subject) > SUBJECT_MAX:
        failures.append(f"subject is {len(content.subject)} characters (max {SUBJECT_MAX})")
    if len(content.preheader) > PREHEADER_MAX:
        failures.append(
            f"preheader is {len(content.preheader)} characters (max {PREHEADER_MAX})"
        )
    if len(content.cta_text) > CTA_MAX:
        failures.append(f"CTA is {len(content.cta_text)} characters (max {CTA_MAX})")
    if failures:
        return ValidationCheck(
            check="character_limits",
            status=CheckStatus.FAIL,
            details="; ".join(failures) + ".",
        )
    return ValidationCheck(
        check="character_limits",
        status=CheckStatus.PASS,
        details="Subject, preheader, and CTA are within character limits.",
    )


def _claims(content: EmailContent, claims: list[ProductClaim]) -> ValidationCheck:
    by_id = {claim.claim_id: claim for claim in claims}
    problems: list[str] = []
    for claim_id in content.claim_ids:
        record = by_id.get(claim_id)
        if record is None:
            problems.append(f"{claim_id} does not exist")
        elif not record.approved:
            problems.append(f"{claim_id} is not approved")
    if problems:
        return ValidationCheck(
            check="claims",
            status=CheckStatus.FAIL,
            details="Unsupported claim: " + "; ".join(problems) + ".",
        )
    return ValidationCheck(
        check="claims",
        status=CheckStatus.PASS,
        details="All referenced claim IDs exist and are approved.",
    )


def _asset(
    selected: SelectedAsset | None,
    assets: list[AssetRecord],
    channel: str,
) -> ValidationCheck:
    if selected is None:
        return ValidationCheck(
            check="asset",
            status=CheckStatus.FAIL,
            details="No asset was selected.",
        )
    by_id = {asset.asset_id: asset for asset in assets}
    record = by_id.get(selected.asset_id)
    if record is None:
        return ValidationCheck(
            check="asset",
            status=CheckStatus.FAIL,
            details=f"Asset {selected.asset_id} is not in the registry.",
        )
    if not record.approved:
        return ValidationCheck(
            check="asset",
            status=CheckStatus.FAIL,
            details=f"Asset {record.asset_id} is not approved.",
        )
    if channel not in record.allowed_channels:
        return ValidationCheck(
            check="asset",
            status=CheckStatus.FAIL,
            details=f"Asset {record.asset_id} is not allowed for channel {channel}.",
        )
    disk_path = PROJECT_ROOT / record.path
    if not Path(disk_path).is_file():
        return ValidationCheck(
            check="asset",
            status=CheckStatus.FAIL,
            details=f"Asset file is missing on disk: {record.path}.",
        )
    return ValidationCheck(
        check="asset",
        status=CheckStatus.PASS,
        details="Selected asset exists, is approved, and is allowed for this channel.",
    )


def validate_campaign(
    content: EmailContent,
    selected_asset: SelectedAsset | None,
    claims: list[ProductClaim],
    assets: list[AssetRecord],
    brand_rules: BrandRules,
    channel: str = "email",
) -> ValidationResult:
    checks = [
        _required_fields(content),
        _brand_phrases(content, brand_rules),
        _cta_present(content),
        _character_limits(content),
        _claims(content, claims),
        _asset(selected_asset, assets, channel),
    ]
    return ValidationResult.from_checks(checks)
