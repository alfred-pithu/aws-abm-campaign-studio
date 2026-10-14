from src.agents.content_agent import attach_approved_claim_ids, enforce_content_limits
from src.services.claims import approved_claims_for_product
from src.services.validators import CTA_MAX
from tests.conftest import sample_content


def test_verbose_product_name_still_matches_bedrock_claims():
    claims = approved_claims_for_product(
        "Amazon Bedrock for CTOs at AI startups"
    )
    ids = {claim.claim_id for claim in claims}
    assert "bedrock_001" in ids
    assert "bedrock_unapproved" not in ids


def test_exact_product_name_matches():
    claims = approved_claims_for_product("Amazon Bedrock")
    assert {claim.claim_id for claim in claims} == {
        "bedrock_001",
        "bedrock_002",
        "bedrock_003",
        "bedrock_004",
    }


def test_unknown_product_does_not_match():
    assert approved_claims_for_product("Salesforce") == []


def test_aws_bedrock_alias_matches_amazon_bedrock_claims():
    for name in ("AWS Bedrock", "aws bedrock", "Promote AWS Bedrock to CTOs"):
        ids = {claim.claim_id for claim in approved_claims_for_product(name)}
        assert "bedrock_001" in ids, name
        assert "bedrock_unapproved" not in ids


def test_empty_claim_list_does_not_steal_registry_ids():
    content = sample_content(claim_ids=[])
    updated = attach_approved_claim_ids(content, claims=[], required_ids=[])
    assert updated.claim_ids == []


def test_empty_claim_ids_are_filled_from_required():
    content = sample_content(claim_ids=[])
    claims = approved_claims_for_product("Amazon Bedrock")
    updated = attach_approved_claim_ids(
        content, claims, ["bedrock_002", "not_real"]
    )
    assert updated.claim_ids == ["bedrock_002"]


def test_invalid_claim_ids_are_replaced_with_approved():
    content = sample_content(claim_ids=["totally_made_up"])
    claims = approved_claims_for_product("Amazon Bedrock")
    updated = attach_approved_claim_ids(content, claims, [])
    assert updated.claim_ids
    assert all(cid.startswith("bedrock_") for cid in updated.claim_ids)
    assert "bedrock_unapproved" not in updated.claim_ids


def test_long_cta_is_replaced_with_short_fallback():
    content = sample_content(
        cta_text="Discover how Amazon Bedrock can empower your engineering team."
    )
    updated = enforce_content_limits(
        content,
        recommended_cta="Discover how Amazon Bedrock can empower your engineering team.",
    )
    assert len(updated.cta_text) <= CTA_MAX
    assert updated.cta_text == "Explore Amazon Bedrock"


def test_short_recommended_cta_is_used_when_model_overruns():
    content = sample_content(cta_text="This call to action is definitely longer than forty chars")
    updated = enforce_content_limits(content, recommended_cta="Explore Amazon Bedrock")
    assert updated.cta_text == "Explore Amazon Bedrock"


def test_valid_claim_ids_are_kept():
    content = sample_content(claim_ids=["bedrock_001", "bedrock_unapproved"])
    claims = approved_claims_for_product("Amazon Bedrock")
    updated = attach_approved_claim_ids(content, claims, ["bedrock_004"])
    assert updated.claim_ids == ["bedrock_001"]
