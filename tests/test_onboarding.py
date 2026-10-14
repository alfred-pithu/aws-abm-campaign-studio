import pytest

from src.agents.content_agent import attach_approved_claim_ids
from src.agents.onboarding_agent import (
    _GeneratedClaim,
    _GeneratedProfile,
    generate_product_profile,
)
from src.graph.workflow import run_generate
from src.models.campaign import ProductClaim
from src.models.product import ProductProfile, ProductProfileDraft
from src.services.claims import (
    DuplicateProductError,
    approve_product,
    approved_claims_for_product,
    clear_registry_caches,
    find_approved_product,
)
from src.services.web import fetch_page
from tests.conftest import sample_brief, sample_content


def _generated_profile() -> _GeneratedProfile:
    return _GeneratedProfile(
        short_description="Incident summaries for engineering leaders.",
        category="AI operations",
        capabilities=["Summarize incidents"],
        target_audiences=["CTOs"],
        use_cases=["Incident review"],
        differentiators=["Works with existing tickets"],
        claims=[
            _GeneratedClaim(
                claim="Acme AI Platform summarizes incidents from existing tickets.",
                source="docs",
            ),
            _GeneratedClaim(
                claim="Acme AI Platform guarantees a 90% reduction in outages.",
                source="hype",
            ),
        ],
    )


def _acme_draft() -> ProductProfileDraft:
    return ProductProfileDraft(
        profile=ProductProfile(
            product_id="",
            name="Acme AI Platform",
            short_description="Incident summaries for engineering leaders.",
            category="AI operations",
            capabilities=["Summarize incidents"],
            target_audiences=["CTOs"],
            status="draft",
        ),
        claims=[
            ProductClaim(
                claim_id="",
                product="Acme AI Platform",
                claim="Acme AI Platform summarizes incidents from existing tickets.",
                source="docs",
                approved=False,
            )
        ],
    )


@pytest.fixture
def registry_dir(tmp_path, monkeypatch):
    (tmp_path / "products.json").write_text("[]\n", encoding="utf-8")
    (tmp_path / "product_claims.json").write_text("[]\n", encoding="utf-8")

    class Settings:
        data_dir = tmp_path

    monkeypatch.setattr("src.services.claims.get_settings", lambda: Settings())
    clear_registry_caches()
    yield tmp_path
    clear_registry_caches()


def test_generate_from_text_produces_unapproved_claims(monkeypatch):
    monkeypatch.setattr(
        "src.agents.onboarding_agent.fetch_page",
        lambda url: (_ for _ in ()).throw(AssertionError("fetch should not run")),
    )
    monkeypatch.setattr(
        "src.agents.onboarding_agent.generate_structured",
        lambda *args, **kwargs: _generated_profile(),
    )
    draft = generate_product_profile(
        "Acme AI Platform",
        description="Acme AI Platform helps CTOs summarize incidents from tickets.",
    )
    assert draft.insufficient_source is False
    assert draft.claims
    assert all(claim.approved is False for claim in draft.claims)
    assert all(claim.claim_id == "" for claim in draft.claims)


def test_missing_source_is_insufficient_and_does_not_invent(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not run without source material")

    monkeypatch.setattr(
        "src.agents.onboarding_agent.generate_structured", fail_if_called
    )
    monkeypatch.setattr(
        "src.agents.onboarding_agent.fetch_page",
        lambda url: type("Result", (), {"text": "", "error": "The page timed out."})(),
    )
    draft = generate_product_profile("Acme AI Platform", url="https://example.com/acme")
    assert draft.insufficient_source is True
    assert draft.claims == []
    assert "timed out" in draft.warning


def test_draft_is_not_in_approved_claims(registry_dir, monkeypatch):
    monkeypatch.setattr(
        "src.agents.onboarding_agent.generate_structured",
        lambda *args, **kwargs: _generated_profile(),
    )
    draft = generate_product_profile(
        "Acme AI Platform",
        description="Acme AI Platform helps CTOs summarize incidents from tickets.",
    )
    assert approved_claims_for_product("Acme AI Platform") == []
    assert find_approved_product("Acme AI Platform") is None
    assert all(claim.approved is False for claim in draft.claims)


def test_approve_persists_and_name_match_returns_claims(registry_dir):
    saved = approve_product(_acme_draft())
    assert saved.status == "approved"
    assert saved.name == "Acme AI Platform"
    assert find_approved_product("Acme") is not None
    assert find_approved_product("Acme").name == "Acme AI Platform"
    claims = approved_claims_for_product("Promote Acme AI Platform to CTOs")
    assert {claim.claim for claim in claims} == {
        "Acme AI Platform summarizes incidents from existing tickets."
    }
    assert all(claim.approved for claim in claims)
    assert all(claim.claim_id.startswith("acme_ai_platform_") for claim in claims)


def test_duplicate_name_rejected(registry_dir):
    approve_product(_acme_draft())
    with pytest.raises(DuplicateProductError):
        approve_product(_acme_draft())


def test_bedrock_still_matches_aws_and_amazon_names():
    clear_registry_caches()
    for name in ("AWS Bedrock", "Amazon Bedrock", "Promote AWS Bedrock to CTOs"):
        product = find_approved_product(name)
        assert product is not None, name
        assert product.name == "Amazon Bedrock"
        ids = {claim.claim_id for claim in approved_claims_for_product(name)}
        assert "bedrock_001" in ids
        assert "bedrock_unapproved" not in ids


def test_unknown_product_does_not_attach_bedrock_claim_ids():
    content = sample_content(claim_ids=["bedrock_001"])
    updated = attach_approved_claim_ids(content, claims=[], required_ids=["bedrock_001"])
    assert updated.claim_ids == []


def test_unknown_product_stops_generate():
    brief = sample_brief()
    brief.product = "Salesforce"
    result = run_generate(brief)
    assert result.workflow_status.value == "DRAFT"
    assert result.strategy is None
    assert result.content is None
    assert "Salesforce" in (result.error_message or "")
    assert "Products" in (result.error_message or "")


def test_fetch_page_rejects_non_http():
    result = fetch_page("file:///etc/passwd")
    assert result.text == ""
    assert "http" in result.error.lower()
