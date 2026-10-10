"""Content Agent.

Allowed context: brief, strategy, brand rules, approved claims.
Must not: emit HTML, select assets, invent claims, or publish.
"""

from src.models.campaign import BrandRules, CampaignBrief, CampaignStrategy, ProductClaim
from src.models.content import EmailContent
from src.services.claims import load_claims
from src.services.llm import generate_structured
from src.services.validators import CTA_MAX, PREHEADER_MAX, SUBJECT_MAX

SYSTEM_PROMPT = """
You are the Content Agent in an enterprise marketing workflow.

Your job is to write email content using the supplied campaign strategy,
brand rules, and approved product claims.

Role: Write structured email copy only.

Allowed context: campaign brief, campaign strategy, brand rules, and approved
claims. You do not receive the asset registry, HTML templates, or publishing tools.

Objective: Return EmailContent with subject, preheader, headline, body_paragraphs,
cta_text, and claim_ids.

Constraints:
- Do not invent product facts. Only use supplied approved claims.
- claim_ids MUST be a non-empty list of approved claim_id values (for example bedrock_001). Never leave it empty. Never put claim sentences in claim_ids.
- Subject <= 80 characters, preheader <= 120, CTA <= 40.
- Avoid prohibited phrases from brand rules.
- Prefer technical, clear, confident, practical language.
- Keep CTAs direct.

What you must NOT do:
- Create HTML
- Select assets
- Publish content
- Use unapproved or invented claim IDs

Return only the requested structured output.
""".strip()


def write_content(
    brief: CampaignBrief,
    strategy: CampaignStrategy,
    brand_rules: BrandRules,
    claims: list[ProductClaim],
    revision_feedback: str | None = None,
) -> EmailContent:
    payload = {
        "brief": brief.model_dump(),
        "strategy": strategy.model_dump(),
        "brand_rules": brand_rules.model_dump(),
        "approved_claims": [claim.model_dump() for claim in claims],
    }
    if revision_feedback:
        payload["revision_feedback"] = revision_feedback
    allowed_ids = [claim.claim_id for claim in claims if claim.approved]
    content = generate_structured(
        SYSTEM_PROMPT,
        (
            "Write structured email content. Do not emit HTML. "
            f"Set claim_ids to a non-empty subset of: {allowed_ids}\n"
            f"{payload}"
        ),
        EmailContent,
        agent_name="content_agent",
    )
    content = attach_approved_claim_ids(content, claims, strategy.required_claims)
    return enforce_content_limits(content, strategy.recommended_cta)


def attach_approved_claim_ids(
    content: EmailContent,
    claims: list[ProductClaim],
    required_ids: list[str] | None = None,
) -> EmailContent:
    """Keep only approved IDs. If the model omitted them, attach registry IDs."""
    allowed = [claim.claim_id for claim in claims if claim.approved]
    if not allowed:
        allowed = [claim.claim_id for claim in load_claims() if claim.approved]
    allowed_set = set(allowed)
    kept = [cid for cid in content.claim_ids if cid in allowed_set]
    if kept:
        content.claim_ids = kept
        return content
    required = [cid for cid in (required_ids or []) if cid in allowed_set]
    content.claim_ids = required or list(allowed)
    return content


def _fit(text: str, max_len: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    trimmed = cleaned[:max_len].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0].rstrip()
    return trimmed[:max_len]


def enforce_content_limits(content: EmailContent, recommended_cta: str = "") -> EmailContent:
    """Clamp copy to validator limits. The model is not trusted to count characters."""
    content.subject = _fit(content.subject, SUBJECT_MAX)
    content.preheader = _fit(content.preheader, PREHEADER_MAX)
    if len(content.cta_text.strip()) > CTA_MAX:
        fallback = recommended_cta.strip()
        content.cta_text = (
            fallback if fallback and len(fallback) <= CTA_MAX else "Explore Amazon Bedrock"
        )
        if len(content.cta_text) > CTA_MAX:
            content.cta_text = _fit(content.cta_text, CTA_MAX)
    else:
        content.cta_text = content.cta_text.strip()
    return content
