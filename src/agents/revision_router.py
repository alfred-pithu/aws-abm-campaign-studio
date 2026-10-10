"""Revision router: classify marketer feedback onto one workflow target.

This is a classifier, not an autonomous agent. Keyword rules run first.
LLM classify() is the fallback when no keyword matches.
"""

from typing import Literal

from src.services.llm import classify

RevisionTarget = Literal["content", "asset", "strategy", "full_campaign"]

SYSTEM_PROMPT = """
You are the revision router in an enterprise marketing workflow.

Role: Classify marketer feedback into exactly one revision target.

Allowed context: the feedback string only.

Objective: Return one label:
- content (tone, copy, CTA, subject, salesiness)
- asset (image, visual, hero, photo)
- strategy (audience angle, positioning)
- full_campaign (start over)

What you must NOT do:
- Rewrite copy
- Select assets
- Publish
""".strip()

_FULL_KEYWORDS = (
    "start over",
    "whole campaign",
    "entire campaign",
    "from scratch",
    "full campaign",
)
_ASSET_KEYWORDS = ("image", "visual", "hero", "photo", "picture", "graphic", "asset")
_STRATEGY_KEYWORDS = ("angle", "audience", "strategy", "positioning", "persona")
_CONTENT_KEYWORDS = (
    "tone",
    "copy",
    "salesy",
    "cta",
    "subject",
    "preheader",
    "headline",
    "wording",
    "body",
    "less salesy",
    "more technical",
)


def route_revision(feedback: str) -> RevisionTarget:
    text = feedback.lower()
    if any(keyword in text for keyword in _FULL_KEYWORDS):
        return "full_campaign"
    if any(keyword in text for keyword in _ASSET_KEYWORDS):
        return "asset"
    if any(keyword in text for keyword in _STRATEGY_KEYWORDS):
        return "strategy"
    if any(keyword in text for keyword in _CONTENT_KEYWORDS):
        return "content"
    label = classify(
        SYSTEM_PROMPT,
        f"Classify this marketer feedback:\n{feedback}",
        labels=["content", "asset", "strategy", "full_campaign"],
        agent_name="revision_router",
    )
    if label not in {"content", "asset", "strategy", "full_campaign"}:
        return "content"
    return label  # type: ignore[return-value]
