import pytest

from src.graph.state import WorkflowState
from src.graph.workflow import ApprovalError, IllegalTransition, approve, publish, transition
from src.models.campaign import WorkflowStatus
from src.services.renderer import render_email
from src.services.validators import validate_campaign
from tests.conftest import knowledge, sample_asset, sample_brief, sample_content, sample_strategy


def _human_review_state(*, passed: bool = True) -> WorkflowState:
    brand_rules, claims, assets = knowledge()
    content = sample_content() if passed else sample_content(cta_text=" ")
    asset = sample_asset()
    validation = validate_campaign(content, asset, claims, assets, brand_rules)
    return WorkflowState(
        campaign_brief=sample_brief(),
        strategy=sample_strategy(),
        content=content,
        selected_asset=asset,
        validation_results=validation,
        rendered_html=render_email(content, asset) if passed else "<html></html>",
        workflow_status=WorkflowStatus.HUMAN_REVIEW,
        version=1,
    )


def test_preview_cannot_publish():
    state = _human_review_state()
    state.workflow_status = WorkflowStatus.PREVIEW
    with pytest.raises(IllegalTransition, match="PREVIEW to PUBLISHED"):
        transition(state, WorkflowStatus.PUBLISHED)


def test_generating_cannot_publish():
    state = _human_review_state()
    state.workflow_status = WorkflowStatus.GENERATING
    with pytest.raises(IllegalTransition, match="GENERATING to PUBLISHED"):
        transition(state, WorkflowStatus.PUBLISHED)


def test_human_review_cannot_skip_to_published():
    state = _human_review_state()
    with pytest.raises(IllegalTransition, match="HUMAN_REVIEW to PUBLISHED"):
        transition(state, WorkflowStatus.PUBLISHED)


def test_approve_blocked_when_validation_fails():
    state = _human_review_state(passed=False)
    with pytest.raises(ApprovalError, match="Cannot approve campaign"):
        approve(state)


def test_approve_then_publish_reaches_published(tmp_path, monkeypatch):
    class _Settings:
        output_dir = tmp_path

    monkeypatch.setattr("src.graph.workflow.get_settings", lambda: _Settings())
    state = _human_review_state(passed=True)
    approved = approve(state, approved_by="Demo Marketer")
    assert approved.workflow_status == WorkflowStatus.APPROVED
    published = publish(approved)
    assert published.workflow_status == WorkflowStatus.PUBLISHED
    assert (tmp_path / "campaign_001_v1.html").is_file()
