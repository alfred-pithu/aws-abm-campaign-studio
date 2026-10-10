"""Chat transcript helpers. Streamlit UI only — no LLM calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import streamlit as st
import streamlit.components.v1 as components

from src.config import PROJECT_ROOT
from src.graph.state import WorkflowState
from src.models.assets import SelectedAsset
from src.models.campaign import CampaignBrief, CampaignStrategy
from src.models.content import EmailContent
from src.models.validation import CheckStatus, ReviewResult, ValidationResult
from src.services.claims import get_claim

Role = Literal["user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    kind: str
    text: str = ""
    brief: CampaignBrief | None = None
    strategy: CampaignStrategy | None = None
    content: EmailContent | None = None
    asset: SelectedAsset | None = None
    validation: ValidationResult | None = None
    review: ReviewResult | None = None
    rendered_html: str | None = None
    revision_target: str | None = None
    agents_rerun: list[str] = field(default_factory=list)
    agents_skipped: list[str] = field(default_factory=list)
    campaign_id: str | None = None
    version: int | None = None
    approved_by: str | None = None


def _label_list(names: list[str]) -> str:
    if not names:
        return "—"
    return ", ".join(name.replace("_", " ") for name in names)


def _claims_lines(claim_ids: list[str]) -> str:
    lines: list[str] = []
    for claim_id in claim_ids:
        claim = get_claim(claim_id)
        if claim:
            lines.append(f"- `{claim.claim_id}` — {claim.claim}  \n  Source: {claim.source}")
        else:
            lines.append(f"- `{claim_id}`")
    return "\n".join(lines) if lines else "- None"


def append_generate_messages(messages: list[ChatMessage], state: WorkflowState) -> None:
    messages.append(
        ChatMessage(role="assistant", kind="brief", brief=state.campaign_brief)
    )
    if state.strategy:
        messages.append(
            ChatMessage(role="assistant", kind="strategy", strategy=state.strategy)
        )
    if state.content:
        messages.append(
            ChatMessage(role="assistant", kind="content", content=state.content)
        )
    if state.selected_asset:
        messages.append(
            ChatMessage(role="assistant", kind="asset", asset=state.selected_asset)
        )
    if state.validation_results:
        messages.append(
            ChatMessage(
                role="assistant",
                kind="validation",
                validation=state.validation_results,
            )
        )
    if state.review_result:
        messages.append(
            ChatMessage(role="assistant", kind="review", review=state.review_result)
        )
    if state.rendered_html:
        messages.append(
            ChatMessage(
                role="assistant",
                kind="preview",
                rendered_html=state.rendered_html,
            )
        )
    messages.append(
        ChatMessage(
            role="assistant",
            kind="status",
            text=(
                f"Status: `{state.workflow_status.value}`. "
                "Approve above, request changes, or tell me what to change here."
            ),
        )
    )


def append_revision_messages(
    messages: list[ChatMessage],
    state: WorkflowState,
    feedback: str | None = None,
) -> None:
    _ = feedback
    messages.append(
        ChatMessage(
            role="assistant",
            kind="revision",
            revision_target=state.revision_target,
            agents_rerun=list(state.agents_rerun),
            agents_skipped=list(state.agents_skipped),
        )
    )
    if state.content:
        messages.append(
            ChatMessage(role="assistant", kind="content", content=state.content)
        )
    if state.validation_results:
        messages.append(
            ChatMessage(
                role="assistant",
                kind="validation",
                validation=state.validation_results,
            )
        )
    if state.review_result:
        messages.append(
            ChatMessage(role="assistant", kind="review", review=state.review_result)
        )
    if state.rendered_html:
        messages.append(
            ChatMessage(
                role="assistant",
                kind="preview",
                rendered_html=state.rendered_html,
            )
        )
    messages.append(
        ChatMessage(
            role="assistant",
            kind="status",
            text=(
                f"Status: `{state.workflow_status.value}`. "
                "Approve above, request changes, or tell me what to change here."
            ),
        )
    )


def append_publish_message(messages: list[ChatMessage], state: WorkflowState) -> None:
    messages.append(
        ChatMessage(
            role="assistant",
            kind="published",
            campaign_id=state.campaign_brief.campaign_id,
            version=state.version,
            approved_by=state.approved_by or "Demo Marketer",
        )
    )


def _render_brief(message: ChatMessage) -> None:
    brief = message.brief
    if brief is None:
        return
    st.markdown("**Here's the brief I understood**")
    st.markdown(f"- **Product:** {brief.product}")
    st.markdown(f"- **Audience:** {brief.audience}")
    st.markdown(f"- **Goal:** {brief.goal}")
    st.markdown(f"- **Channel:** {brief.channel}")
    st.markdown(f"- **Tone:** {brief.tone}")
    st.markdown(f"- **Key message:** {brief.key_message}")


def _render_strategy(message: ChatMessage) -> None:
    strategy = message.strategy
    if strategy is None:
        return
    st.markdown("**Strategy**")
    st.markdown(f"**Audience:** {strategy.audience}")
    st.markdown(f"**Content angle:** {strategy.content_angle}")
    st.markdown("**Key points**")
    for point in strategy.key_points:
        st.markdown(f"- {point}")
    st.markdown(f"**Recommended CTA:** {strategy.recommended_cta}")
    st.markdown(f"**Tone guidance:** {strategy.tone_guidance}")
    st.markdown("**Required claims**")
    st.markdown(_claims_lines(strategy.required_claims))


def _render_content(message: ChatMessage) -> None:
    content = message.content
    if content is None:
        return
    st.markdown("**Draft email copy**")
    st.markdown(f"**Subject:** {content.subject}")
    st.markdown(f"**Preheader:** {content.preheader}")
    st.markdown(f"**Headline:** {content.headline}")
    st.markdown("**Body**")
    for paragraph in content.body_paragraphs:
        st.write(paragraph)
    st.markdown(f"**CTA:** {content.cta_text}")
    st.markdown("**Claims used**")
    st.markdown(_claims_lines(content.claim_ids))


def _render_asset(message: ChatMessage) -> None:
    asset = message.asset
    if asset is None:
        return
    st.markdown("**Selected approved asset**")
    image_path = PROJECT_ROOT / asset.path
    if image_path.is_file():
        st.image(str(image_path), caption=asset.name)
    st.markdown(f"**Asset ID:** `{asset.asset_id}`")
    st.markdown(f"**Reason:** {asset.reason}")
    st.markdown(f"**Approved:** {'yes' if asset.approved else 'no'}")
    st.markdown(f"**Source:** {asset.source}")


def _render_validation(message: ChatMessage) -> None:
    validation = message.validation
    if validation is None:
        return
    st.markdown("**Validation**")
    if validation.passed:
        st.success("All validation checks passed.")
    else:
        st.error("Validation failed. Approval is blocked until these checks pass.")
    for check in validation.checks:
        icon = "PASS" if check.status == CheckStatus.PASS else "FAIL"
        st.markdown(f"- **{icon}** `{check.check}` — {check.details}")


def _render_review(message: ChatMessage) -> None:
    review = message.review
    if review is None:
        return
    st.markdown("**AI review**")
    st.caption("These scores are evaluation signals, not objective truth.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Audience fit", f"{review.audience_fit}/10")
    m2.metric("Brand alignment", f"{review.brand_alignment}/10")
    m3.metric("Clarity", f"{review.clarity}/10")
    m4.metric("Technical quality", f"{review.technical_quality}/10")
    st.markdown("**Overall assessment**")
    st.write(review.overall_assessment)
    st.markdown(f"**Recommendation:** {review.recommendation}")
    if review.issues:
        st.markdown("**Issues**")
        for issue in review.issues:
            st.markdown(f"- {issue}")


def _render_preview(message: ChatMessage) -> None:
    st.markdown("**Email preview**")
    if message.rendered_html:
        components.html(message.rendered_html, height=640, scrolling=True)
    else:
        st.info("No preview yet.")


def _render_revision(message: ChatMessage) -> None:
    target = (message.revision_target or "content").upper()
    st.markdown(f"**Revision target:** `{target}`")
    st.markdown(f"**Reran:** {_label_list(message.agents_rerun)}")
    st.markdown(f"**Skipped:** {_label_list(message.agents_skipped)}")


def _render_published(message: ChatMessage) -> None:
    st.success("Campaign published successfully.")
    st.markdown(f"**Campaign ID:** `{message.campaign_id}`")
    st.markdown(f"**Version:** `{message.version}`")
    st.markdown(f"**Approved by:** `{message.approved_by}`")
    st.caption("This is a POC publish. No real email was sent.")


def render_messages(messages: list[ChatMessage]) -> None:
    renderers = {
        "brief": _render_brief,
        "strategy": _render_strategy,
        "content": _render_content,
        "asset": _render_asset,
        "validation": _render_validation,
        "review": _render_review,
        "preview": _render_preview,
        "revision": _render_revision,
        "published": _render_published,
    }
    for message in messages:
        with st.chat_message(message.role):
            renderer = renderers.get(message.kind)
            if renderer:
                renderer(message)
            elif message.text:
                st.markdown(message.text)
