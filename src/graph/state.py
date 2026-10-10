"""Central campaign workflow state.

Agents receive sliced fields from this object. No agent is given the entire
state as a generic blob of context.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from src.models.assets import SelectedAsset
from src.models.campaign import AuditEvent, CampaignBrief, CampaignStrategy, WorkflowStatus
from src.models.content import EmailContent
from src.models.validation import ReviewResult, ValidationResult

RevisionTarget = Literal["content", "asset", "strategy", "full_campaign"]


class WorkflowState(BaseModel):
    campaign_brief: CampaignBrief
    strategy: CampaignStrategy | None = None
    content: EmailContent | None = None
    selected_asset: SelectedAsset | None = None
    validation_results: ValidationResult | None = None
    review_result: ReviewResult | None = None
    revision_request: str | None = None
    revision_target: RevisionTarget | None = None
    workflow_status: WorkflowStatus = WorkflowStatus.DRAFT
    version: int = 1
    audit_events: list[AuditEvent] = Field(default_factory=list)
    rendered_html: str | None = None
    error_message: str | None = None
    agents_rerun: list[str] = Field(default_factory=list)
    agents_skipped: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    published_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def append_audit(
    state: WorkflowState,
    event: str,
    agent: str | None = None,
    details: str | None = None,
) -> WorkflowState:
    updated = state.model_copy(deep=True)
    updated.audit_events.append(
        AuditEvent(
            timestamp=datetime.now(timezone.utc),
            event=event,
            agent=agent,
            version=updated.version,
            details=details,
        )
    )
    return updated
