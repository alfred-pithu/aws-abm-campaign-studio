from src.graph.state import WorkflowState
from src.graph.workflow import _validate_review_render
from src.models.campaign import WorkflowStatus
from src.models.validation import ReviewResult
from tests.conftest import sample_asset, sample_brief, sample_content, sample_strategy


def _review_stub(*_args, **_kwargs) -> ReviewResult:
    return ReviewResult(
        audience_fit=8,
        brand_alignment=8,
        clarity=8,
        technical_quality=8,
        overall_assessment="Ready for human review.",
        issues=[],
        recommendation="APPROVE",
    )


def _generating_state(content) -> WorkflowState:
    return WorkflowState(
        campaign_brief=sample_brief(),
        strategy=sample_strategy(),
        content=content,
        selected_asset=sample_asset(),
        workflow_status=WorkflowStatus.GENERATING,
        version=1,
    )


def _repair_actions(state: WorkflowState) -> list[str]:
    events = [event for event in state.audit_events if event.event == "VALIDATION_AUTO_REPAIR"]
    actions = []
    for event in events:
        details = event.details or ""
        if "action: " in details:
            actions.append(details.split("action: ", 1)[1])
    return actions


def test_deterministic_repair_passes_without_llm(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("write_content should not run when deterministic repair passes")

    monkeypatch.setattr("src.graph.workflow.write_content", fail_if_called)
    monkeypatch.setattr("src.graph.workflow.review_content", _review_stub)
    state = _generating_state(
        sample_content(
            body_paragraphs=[
                "Amazon Bedrock provides effortless access to foundation models through a managed service.",
                "Teams can build generative AI applications with enterprise-ready controls.",
            ]
        )
    )
    result = _validate_review_render(state, include_review=True)
    assert result.workflow_status == WorkflowStatus.HUMAN_REVIEW
    assert result.validation_results is not None
    assert result.validation_results.passed is True
    assert "deterministic" in _repair_actions(result)
    assert result.version == 1


def test_content_regen_repair_passes_after_failed_validation(monkeypatch):
    calls = {"count": 0}

    def fake_write_content(*_args, **_kwargs):
        calls["count"] += 1
        return sample_content()

    monkeypatch.setattr("src.graph.workflow.write_content", fake_write_content)
    monkeypatch.setattr("src.graph.workflow.review_content", _review_stub)
    state = _generating_state(sample_content(body_paragraphs=["   "]))
    result = _validate_review_render(state, include_review=True)
    assert result.workflow_status == WorkflowStatus.HUMAN_REVIEW
    assert result.validation_results is not None
    assert result.validation_results.passed is True
    assert "content_regen" in _repair_actions(result)
    assert calls["count"] == 1
    assert result.version == 1


def test_content_regen_stops_at_cap_and_still_blocks_approve(monkeypatch):
    calls = {"count": 0}

    def fake_write_content(*_args, **_kwargs):
        calls["count"] += 1
        return sample_content(body_paragraphs=["   "])

    monkeypatch.setattr("src.graph.workflow.write_content", fake_write_content)
    monkeypatch.setattr("src.graph.workflow.review_content", _review_stub)
    monkeypatch.setattr(
        "src.graph.workflow.get_settings",
        lambda: type("Settings", (), {"validation_repair_max_attempts": 3})(),
    )
    state = _generating_state(sample_content(body_paragraphs=["   "]))
    result = _validate_review_render(state, include_review=True)
    assert result.workflow_status == WorkflowStatus.HUMAN_REVIEW
    assert result.validation_results is not None
    assert result.validation_results.passed is False
    assert _repair_actions(result).count("content_regen") == 3
    assert calls["count"] == 3
    assert result.version == 1
