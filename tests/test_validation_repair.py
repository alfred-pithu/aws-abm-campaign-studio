from src.models.validation import CheckStatus, ValidationCheck, ValidationResult
from src.services.claims import load_brand_rules
from src.services.validation_repair import (
    apply_deterministic_content_fixes,
    asset_only_failures,
    content_failure_names,
    failed_checks,
    format_repair_feedback,
)
from src.services.validators import CTA_MAX, validate_campaign
from tests.conftest import knowledge, sample_asset, sample_content, sample_strategy


def test_failed_checks_returns_only_fails():
    result = ValidationResult.from_checks(
        [
            ValidationCheck(check="claims", status=CheckStatus.PASS, details="ok"),
            ValidationCheck(
                check="brand_forbidden_phrases",
                status=CheckStatus.FAIL,
                details="Forbidden phrases detected: effortless.",
            ),
        ]
    )
    failed = failed_checks(result)
    assert [check.check for check in failed] == ["brand_forbidden_phrases"]


def test_content_vs_asset_failure_classification():
    content_fail = ValidationCheck(
        check="brand_forbidden_phrases",
        status=CheckStatus.FAIL,
        details="Forbidden phrases detected: effortless.",
    )
    asset_fail = ValidationCheck(
        check="asset",
        status=CheckStatus.FAIL,
        details="No asset was selected.",
    )
    assert content_failure_names([content_fail]) == {"brand_forbidden_phrases"}
    assert asset_only_failures([asset_fail]) is True
    assert asset_only_failures([content_fail, asset_fail]) is False


def test_format_repair_feedback_mentions_forbidden_phrases():
    brand_rules = load_brand_rules()
    checks = [
        ValidationCheck(
            check="brand_forbidden_phrases",
            status=CheckStatus.FAIL,
            details="Forbidden phrases detected: effortless.",
        )
    ]
    feedback = format_repair_feedback(checks, brand_rules)
    assert "effortless" in feedback.lower()
    assert "forbidden" in feedback.lower()


def test_deterministic_fix_removes_effortless_and_passes_brand_check():
    brand_rules, claims, assets = knowledge()
    content = sample_content(
        body_paragraphs=[
            "Amazon Bedrock provides effortless access to foundation models through a managed service.",
            "Teams can build generative AI applications with enterprise-ready controls.",
        ]
    )
    before = validate_campaign(content, sample_asset(), claims, assets, brand_rules)
    brand_check = next(
        item for item in before.checks if item.check == "brand_forbidden_phrases"
    )
    assert brand_check.status == CheckStatus.FAIL

    updated = apply_deterministic_content_fixes(
        content, claims, sample_strategy(), brand_rules
    )
    assert "effortless" not in " ".join(
        [updated.subject, updated.preheader, updated.headline, updated.cta_text, *updated.body_paragraphs]
    ).lower()
    after = validate_campaign(updated, sample_asset(), claims, assets, brand_rules)
    brand_after = next(
        item for item in after.checks if item.check == "brand_forbidden_phrases"
    )
    assert brand_after.status == CheckStatus.PASS
    assert after.passed is True


def test_deterministic_fix_clamps_overlong_cta():
    brand_rules, claims, _assets = knowledge()
    content = sample_content(
        cta_text="Discover how Amazon Bedrock can empower your engineering team."
    )
    updated = apply_deterministic_content_fixes(
        content, claims, sample_strategy(), brand_rules
    )
    assert len(updated.cta_text) <= CTA_MAX
