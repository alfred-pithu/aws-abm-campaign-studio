"""Strategy Agent.

Allowed context: brief, brand rules, approved claims.
Must not: write the final email, select assets, or publish.
"""

from src.models.campaign import BrandRules, CampaignBrief, CampaignStrategy, ProductClaim
from src.services.llm import generate_structured

SYSTEM_PROMPT = """
You are the Strategy Agent in an enterprise marketing workflow.

Role: Decide what AWS should say to the target audience.

Allowed context: the normalized campaign brief, brand rules, and approved product
claims. You do not receive assets, HTML templates, CRM data, or publishing tools.

Objective: Produce a CampaignStrategy with audience, content_angle, key_points,
recommended_cta, required_claims, tone_guidance, and content_constraints.

Constraints:
- required_claims must be claim IDs from the approved list you were given.
- Do not invent product facts.
- Do not write the final email body, subject, or HTML.

What you must NOT do:
- Write finished email copy
- Select images
- Publish
- Use unapproved claims

Return only the requested structured output.
""".strip()


def build_strategy(
    brief: CampaignBrief,
    brand_rules: BrandRules,
    claims: list[ProductClaim],
    revision_feedback: str | None = None,
) -> CampaignStrategy:
    payload = {
        "brief": brief.model_dump(),
        "brand_rules": brand_rules.model_dump(),
        "approved_claims": [claim.model_dump() for claim in claims],
    }
    if revision_feedback:
        payload["revision_feedback"] = revision_feedback
    strategy = generate_structured(
        SYSTEM_PROMPT,
        (
            "Create a campaign strategy. Use only the approved claim IDs supplied.\n"
            f"{payload}"
        ),
        CampaignStrategy,
        agent_name="strategy_agent",
    )
    allowed = [claim.claim_id for claim in claims if claim.approved]
    allowed_set = set(allowed)
    strategy.required_claims = [
        cid for cid in strategy.required_claims if cid in allowed_set
    ]
    if not strategy.required_claims:
        strategy.required_claims = list(allowed)
    return strategy
