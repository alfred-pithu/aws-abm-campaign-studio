"""Asset Agent.

Allowed context: brief, strategy, local asset registry.
Must not: invent filesystem paths, write copy, or publish.
"""

from pydantic import BaseModel

from src.models.assets import AssetRecord, SelectedAsset
from src.models.campaign import CampaignBrief, CampaignStrategy
from src.services.llm import generate_structured

SYSTEM_PROMPT = """
You are the Asset Agent in an enterprise marketing workflow.

Role: Choose one approved local asset for this email campaign.

Allowed context: campaign brief, campaign strategy, and the asset registry.
You do not receive HTML templates, claims to rewrite, or publishing tools.

Objective: Return asset_id and a short reason. asset_id MUST be one of the
IDs in the registry.

Constraints:
- Never invent an asset path or a new asset_id.
- Prefer assets whose description matches the product and message.

What you must NOT do:
- Invent paths
- Write email copy
- Publish

Return only the requested structured output.
""".strip()


class AssetChoice(BaseModel):
    asset_id: str
    reason: str


def _fallback_asset(registry: list[AssetRecord], channel: str) -> AssetRecord:
    for asset in registry:
        if asset.approved and channel in asset.allowed_channels:
            return asset
    raise ValueError("No approved asset is available for this channel.")


def hydrate_asset(
    choice: AssetChoice,
    registry: list[AssetRecord],
    channel: str = "email",
) -> SelectedAsset:
    by_id = {asset.asset_id: asset for asset in registry}
    record = by_id.get(choice.asset_id)
    reason = choice.reason
    if (
        record is None
        or not record.approved
        or channel not in record.allowed_channels
    ):
        record = _fallback_asset(registry, channel)
        reason = f"{choice.reason} (fell back to an approved registry asset)"
    return SelectedAsset(
        asset_id=record.asset_id,
        reason=reason,
        name=record.name,
        path=record.path,
        approved=record.approved,
        source="local asset registry",
    )


def select_asset(
    brief: CampaignBrief,
    strategy: CampaignStrategy,
    registry: list[AssetRecord],
    revision_feedback: str | None = None,
) -> SelectedAsset:
    payload = {
        "brief": brief.model_dump(),
        "strategy": strategy.model_dump(),
        "assets": [asset.model_dump() for asset in registry],
    }
    if revision_feedback:
        payload["revision_feedback"] = revision_feedback
    choice = generate_structured(
        SYSTEM_PROMPT,
        f"Select one asset_id from the registry.\n{payload}",
        AssetChoice,
        agent_name="asset_agent",
    )
    return hydrate_asset(choice, registry, channel=brief.channel)
