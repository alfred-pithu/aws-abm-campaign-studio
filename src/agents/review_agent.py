"""Review Agent.

Allowed context: brief, strategy, content, validation results, brand rules, claims.
Must not: publish. Scores are evaluation signals, not objective truth.
"""

from src.models.campaign import BrandRules, CampaignBrief, CampaignStrategy, ProductClaim
from src.models.content import EmailContent
from src.models.validation import ReviewResult, ValidationResult
from src.services.llm import generate_structured

SYSTEM_PROMPT = """
You are the Review Agent in an enterprise marketing workflow.

Role: Critique completed email content. You did not write this copy.

Allowed context: campaign brief, strategy, generated content, deterministic
validation results, brand rules, and the approved claims referenced by the copy.

Objective: Return ReviewResult with audience_fit, brand_alignment, clarity,
technical_quality (each 1-10), overall_assessment, issues, and recommendation
(APPROVE or REVISE).

Constraints:
- These scores are evaluation signals, not objective truth.
- Check whether factual statements appear supported by the referenced claims.
- If validation failed, mention that in issues and prefer REVISE.
- Do not rewrite the email. Do not select assets.

What you must NOT do:
- Publish content
- Bypass human approval
- Invent new product facts

Return only the requested structured output.
""".strip()


def review_content(
    brief: CampaignBrief,
    strategy: CampaignStrategy,
    content: EmailContent,
    validation_results: ValidationResult,
    brand_rules: BrandRules,
    claims: list[ProductClaim],
) -> ReviewResult:
    used_claims = [claim.model_dump() for claim in claims if claim.claim_id in set(content.claim_ids)]
    payload = {
        "brief": brief.model_dump(),
        "strategy": strategy.model_dump(),
        "content": content.model_dump(),
        "validation_results": validation_results.model_dump(),
        "brand_rules": brand_rules.model_dump(),
        "referenced_claims": used_claims,
    }
    return generate_structured(
        SYSTEM_PROMPT,
        (
            "Evaluate this campaign. Flag any statement not supported by the "
            "referenced claims.\n"
            f"{payload}"
        ),
        ReviewResult,
        agent_name="review_agent",
    )
