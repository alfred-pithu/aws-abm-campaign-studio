from src.models.assets import SelectedAsset
from src.models.campaign import CampaignBrief, CampaignStrategy
from src.models.content import EmailContent
from src.services.claims import load_assets, load_brand_rules, load_claims


def sample_brief() -> CampaignBrief:
    return CampaignBrief(
        campaign_id="campaign_001",
        product="Amazon Bedrock",
        audience="CTOs at AI startups",
        goal="Drive awareness",
        channel="email",
        tone="technical, confident, practical",
        key_message="Build generative AI applications using managed foundation models.",
    )


def sample_strategy() -> CampaignStrategy:
    return CampaignStrategy(
        audience="CTOs at AI startups",
        content_angle="Give engineering leaders a practical path to generative AI without managing model infrastructure.",
        key_points=[
            "Managed access to foundation models",
            "Build generative AI applications faster",
            "Enterprise security and privacy controls",
        ],
        recommended_cta="Explore Amazon Bedrock",
        required_claims=["bedrock_001", "bedrock_002"],
        tone_guidance="Technical, practical, low-hype",
        content_constraints=["Avoid unsupported performance claims"],
    )


def sample_content(**overrides) -> EmailContent:
    data = dict(
        subject="Build generative AI on Amazon Bedrock",
        preheader="Managed foundation models for engineering teams",
        headline="Build generative AI applications without managing model hosts",
        body_paragraphs=[
            "Amazon Bedrock provides access to foundation models through a managed service.",
            "Teams can build generative AI applications with enterprise-ready controls.",
        ],
        cta_text="Explore Amazon Bedrock",
        claim_ids=["bedrock_001", "bedrock_002"],
    )
    data.update(overrides)
    return EmailContent.model_validate(data)


def sample_asset() -> SelectedAsset:
    record = next(asset for asset in load_assets() if asset.asset_id == "asset_bedrock_hero")
    return SelectedAsset(
        asset_id=record.asset_id,
        reason="Matches the Bedrock product and email campaign context.",
        name=record.name,
        path=record.path,
        approved=record.approved,
        source="local asset registry",
    )


def knowledge():
    return load_brand_rules(), load_claims(), load_assets()
