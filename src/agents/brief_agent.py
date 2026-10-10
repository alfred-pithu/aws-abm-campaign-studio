"""Brief Agent.

Allowed context: campaign input only.
Must not: generate final content, select assets, publish, access CRM, approve.
"""

from datetime import datetime

from src.models.campaign import CampaignBrief
from src.services.llm import generate_structured

SYSTEM_PROMPT = """
You are the Brief Agent in an enterprise marketing workflow.

Role: Normalize a marketer's campaign request into a clean structured brief.

Allowed context: the campaign input only. You do not receive brand rules, claims,
assets, generated copy, or approval state.

Objective: Clean up user input, identify audience, identify objective, normalize
tone, extract the key message, and confirm the channel is email.

Output schema: CampaignBrief with campaign_id, product, audience, goal, channel,
tone, key_message, additional_context.

Constraints:
- Preserve marketer intent.
- Channel must be "email".
- Keep campaign_id if provided; do not invent a new product.
- Do not invent product facts or performance claims.

What you must NOT do:
- Generate final email copy
- Select assets
- Publish anything
- Access CRM
- Make approval decisions

Return only the requested structured output.
""".strip()

PARSE_PROMPT = """
You are the Brief Agent in an enterprise marketing workflow.

Role: Parse a marketer's free-text Slack-style request into a structured brief.

Allowed context: the marketer's message only.

Objective: Identify product, audience, goal, tone, and key message. Channel is email.

Output schema: CampaignBrief with campaign_id, product, audience, goal, channel,
tone, key_message, additional_context.

Constraints:
- Preserve marketer intent.
- Channel must be "email".
- Put the original message in additional_context.
- If tone is not stated, use technical, clear, and practical.
- Do not invent product facts.

What you must NOT do:
- Generate final email copy
- Select assets
- Publish
- Make approval decisions

Return only the requested structured output.
""".strip()


def _assign_campaign_id(brief: CampaignBrief) -> CampaignBrief:
    if not brief.campaign_id.strip():
        brief.campaign_id = datetime.now().strftime("campaign_%Y%m%d_%H%M%S")
    return brief


def _trim(brief: CampaignBrief) -> CampaignBrief:
    cleaned = brief.model_copy()
    cleaned.product = brief.product.strip()
    cleaned.audience = brief.audience.strip()
    cleaned.goal = brief.goal.strip()
    cleaned.tone = brief.tone.strip()
    cleaned.key_message = brief.key_message.strip()
    cleaned.additional_context = brief.additional_context.strip()
    cleaned.channel = "email"
    return _assign_campaign_id(cleaned)


def parse_marketer_request(text: str) -> CampaignBrief:
    """Turn a Slack-style free-text request into a CampaignBrief."""
    campaign_id = datetime.now().strftime("campaign_%Y%m%d_%H%M%S")
    parsed = generate_structured(
        PARSE_PROMPT,
        (
            "Parse this marketer request into a campaign brief. "
            "Channel must be email.\n\n"
            f"{text.strip()}"
        ),
        CampaignBrief,
        agent_name="brief_agent",
    )
    parsed.campaign_id = campaign_id
    parsed.channel = "email"
    parsed.additional_context = text.strip()
    return _trim(parsed)


def normalize_brief(brief: CampaignBrief) -> CampaignBrief:
    """Trim and id a brief. Skip the LLM when product and audience are already set."""
    cleaned = _trim(brief)
    if cleaned.product and cleaned.audience:
        return cleaned
    normalized = generate_structured(
        SYSTEM_PROMPT,
        (
            "Normalize this campaign brief. Keep campaign_id unchanged.\n"
            f"{cleaned.model_dump_json(indent=2)}"
        ),
        CampaignBrief,
        agent_name="brief_agent",
    )
    normalized.campaign_id = cleaned.campaign_id
    normalized.channel = "email"
    return _trim(normalized)
