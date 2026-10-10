from src.services.validators import validate_campaign
from tests.conftest import knowledge, sample_asset, sample_content


def test_forbidden_phrase_detected():
    brand_rules, claims, assets = knowledge()
    content = sample_content(
        body_paragraphs=[
            "Amazon Bedrock provides guaranteed results for every generative AI workload."
        ]
    )
    result = validate_campaign(content, sample_asset(), claims, assets, brand_rules)
    check = next(item for item in result.checks if item.check == "brand_forbidden_phrases")
    assert check.status.value == "FAIL"
    assert result.passed is False


def test_missing_cta_detected():
    brand_rules, claims, assets = knowledge()
    content = sample_content(cta_text=" ")
    result = validate_campaign(content, sample_asset(), claims, assets, brand_rules)
    assert any(
        item.check in {"cta_present", "required_fields"} and item.status.value == "FAIL"
        for item in result.checks
    )
    assert result.passed is False


def test_invalid_claim_rejected():
    brand_rules, claims, assets = knowledge()
    content = sample_content(claim_ids=["does_not_exist"])
    result = validate_campaign(content, sample_asset(), claims, assets, brand_rules)
    check = next(item for item in result.checks if item.check == "claims")
    assert check.status.value == "FAIL"
    assert result.passed is False


def test_unapproved_claim_rejected():
    brand_rules, claims, assets = knowledge()
    content = sample_content(claim_ids=["bedrock_unapproved"])
    result = validate_campaign(content, sample_asset(), claims, assets, brand_rules)
    check = next(item for item in result.checks if item.check == "claims")
    assert check.status.value == "FAIL"
    assert "not approved" in check.details
    assert result.passed is False


def test_valid_content_passes():
    brand_rules, claims, assets = knowledge()
    result = validate_campaign(
        sample_content(), sample_asset(), claims, assets, brand_rules
    )
    assert result.passed is True
    assert all(item.status.value == "PASS" for item in result.checks)
