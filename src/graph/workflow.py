"""LangGraph orchestration and the approval/publish state machine.

Publishing is a Python function. No agent can call it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from src.agents.asset_agent import select_asset
from src.agents.brief_agent import normalize_brief, parse_marketer_request
from src.agents.content_agent import write_content
from src.agents.review_agent import review_content
from src.agents.revision_router import route_revision
from src.agents.strategy_agent import build_strategy
from src.config import get_settings
from src.graph.state import WorkflowState, append_audit
from src.models.campaign import CampaignBrief, WorkflowStatus
from src.models.validation import CheckStatus, ValidationResult
from src.services.claims import (
    approved_claims_for_product,
    find_approved_product,
    load_assets,
    load_brand_rules,
    load_claims,
)
from src.services.llm import LLMError
from src.services.renderer import render_email
from src.services.validation_repair import (
    apply_deterministic_content_fixes,
    asset_only_failures,
    content_failure_names,
    failed_checks,
    format_repair_feedback,
)
from src.services.validators import validate_campaign

ALLOWED_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: {WorkflowStatus.GENERATING},
    WorkflowStatus.GENERATING: {WorkflowStatus.VALIDATING, WorkflowStatus.DRAFT},
    WorkflowStatus.VALIDATING: {WorkflowStatus.PREVIEW},
    WorkflowStatus.PREVIEW: {WorkflowStatus.HUMAN_REVIEW},
    WorkflowStatus.HUMAN_REVIEW: {WorkflowStatus.REVISION, WorkflowStatus.APPROVED},
    WorkflowStatus.REVISION: {WorkflowStatus.VALIDATING},
    WorkflowStatus.APPROVED: {WorkflowStatus.PUBLISHED},
    WorkflowStatus.PUBLISHED: set(),
}


class IllegalTransition(Exception):
    """Raised when the workflow tries to skip a required state."""


class ApprovalError(Exception):
    """Raised when approval is blocked by validation or status."""


def transition(state: WorkflowState, new_status: WorkflowStatus) -> WorkflowState:
    current = state.workflow_status
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise IllegalTransition(
            f"Cannot transition from {current.value} to {new_status.value}"
        )
    updated = state.model_copy(deep=True)
    updated.workflow_status = new_status
    return updated


def _as_state(state: WorkflowState | dict) -> WorkflowState:
    if isinstance(state, WorkflowState):
        return state
    return WorkflowState.model_validate(state)


def _dump(state: WorkflowState) -> dict:
    return state.model_dump()


def _brand_and_approved_claims(brief: CampaignBrief):
    return load_brand_rules(), approved_claims_for_product(brief.product)


def _apply_strategy(state: WorkflowState, feedback: str | None = None) -> WorkflowState:
    brand_rules, claims = _brand_and_approved_claims(state.campaign_brief)
    strategy = build_strategy(
        state.campaign_brief, brand_rules, claims, revision_feedback=feedback
    )
    state = state.model_copy(update={"strategy": strategy})
    return append_audit(state, "STRATEGY_GENERATED", agent="strategy_agent")


def _apply_content(
    state: WorkflowState,
    feedback: str | None = None,
    regenerated: bool = False,
) -> WorkflowState:
    brand_rules, claims = _brand_and_approved_claims(state.campaign_brief)
    content = write_content(
        state.campaign_brief,
        state.strategy,
        brand_rules,
        claims,
        revision_feedback=feedback,
    )
    state = state.model_copy(update={"content": content})
    event = "CONTENT_REGENERATED" if regenerated else "CONTENT_GENERATED"
    return append_audit(state, event, agent="content_agent")


def _apply_asset(state: WorkflowState, feedback: str | None = None) -> WorkflowState:
    selected = select_asset(
        state.campaign_brief,
        state.strategy,
        load_assets(),
        revision_feedback=feedback,
    )
    state = state.model_copy(update={"selected_asset": selected})
    return append_audit(state, "ASSET_SELECTED", agent="asset_agent")


def _validate_campaign(state: WorkflowState) -> ValidationResult:
    return validate_campaign(
        content=state.content,
        selected_asset=state.selected_asset,
        claims=load_claims(),
        assets=load_assets(),
        brand_rules=load_brand_rules(),
        channel=state.campaign_brief.channel,
    )


def _audit_repair(state: WorkflowState, attempt: int, failed_names: str, action: str) -> WorkflowState:
    return append_audit(
        state,
        "VALIDATION_AUTO_REPAIR",
        agent="validators",
        details=f"attempt {attempt}; failed: {failed_names}; action: {action}",
    )


def _validate_review_render(state: WorkflowState, include_review: bool) -> WorkflowState:
    state = transition(state, WorkflowStatus.VALIDATING)
    max_attempts = get_settings().validation_repair_max_attempts
    brand_rules = load_brand_rules()
    llm_attempts = 0
    asset_retried = False
    result = _validate_campaign(state)

    while not result.passed:
        failed = failed_checks(result)
        names = ",".join(check.check for check in failed)

        if (
            state.content is not None
            and state.strategy is not None
            and content_failure_names(failed)
        ):
            claims = approved_claims_for_product(state.campaign_brief.product)
            original = state.content.model_dump()
            fixed = apply_deterministic_content_fixes(
                state.content, claims, state.strategy, brand_rules
            )
            if fixed.model_dump() != original:
                state = state.model_copy(update={"content": fixed})
                state = _audit_repair(state, llm_attempts, names, "deterministic")
                result = _validate_campaign(state)
                if result.passed:
                    break
                failed = failed_checks(result)
                names = ",".join(check.check for check in failed)

        if asset_only_failures(failed) and not asset_retried:
            state = _apply_asset(
                state, feedback=format_repair_feedback(failed, brand_rules)
            )
            state = _audit_repair(state, llm_attempts, names, "asset_reselect")
            asset_retried = True
            result = _validate_campaign(state)
            continue

        if content_failure_names(failed) and llm_attempts < max_attempts:
            state = _apply_content(
                state,
                feedback=format_repair_feedback(failed, brand_rules),
                regenerated=True,
            )
            llm_attempts += 1
            state = _audit_repair(state, llm_attempts, names, "content_regen")
            result = _validate_campaign(state)
            continue

        break

    state = state.model_copy(update={"validation_results": result})
    state = append_audit(state, "VALIDATION_COMPLETED", agent="validators")
    if include_review:
        brand_rules, claims = _brand_and_approved_claims(state.campaign_brief)
        review = review_content(
            state.campaign_brief,
            state.strategy,
            state.content,
            result,
            brand_rules,
            claims,
        )
        state = state.model_copy(update={"review_result": review})
        state = append_audit(state, "REVIEW_COMPLETED", agent="review_agent")
    html = render_email(state.content, state.selected_asset)
    state = state.model_copy(update={"rendered_html": html})
    state = transition(state, WorkflowStatus.PREVIEW)
    state = transition(state, WorkflowStatus.HUMAN_REVIEW)
    return state


def normalize_brief_node(state: WorkflowState | dict) -> dict:
    state = _as_state(state)
    brief = normalize_brief(state.campaign_brief)
    state = state.model_copy(update={"campaign_brief": brief})
    state = append_audit(state, "BRIEF_NORMALIZED", agent="brief_agent")
    return _dump(state)


def build_strategy_node(state: WorkflowState | dict) -> dict:
    return _dump(_apply_strategy(_as_state(state)))


def write_content_node(state: WorkflowState | dict) -> dict:
    return _dump(_apply_content(_as_state(state)))


def select_asset_node(state: WorkflowState | dict) -> dict:
    return _dump(_apply_asset(_as_state(state)))


def validate_review_render_node(state: WorkflowState | dict) -> dict:
    return _dump(_validate_review_render(_as_state(state), include_review=True))


def content_revision_node(state: WorkflowState | dict) -> dict:
    state = _as_state(state)
    state = _apply_content(state, feedback=state.revision_request, regenerated=True)
    state = _validate_review_render(state, include_review=True)
    state = state.model_copy(
        update={
            "agents_rerun": ["content", "validation", "review"],
            "agents_skipped": ["brief", "strategy", "asset"],
        }
    )
    return _dump(state)


def asset_revision_node(state: WorkflowState | dict) -> dict:
    state = _as_state(state)
    state = _apply_asset(state, feedback=state.revision_request)
    state = _validate_review_render(state, include_review=False)
    state = state.model_copy(
        update={
            "agents_rerun": ["asset", "validation"],
            "agents_skipped": ["brief", "strategy", "content", "review"],
        }
    )
    return _dump(state)


def strategy_revision_node(state: WorkflowState | dict) -> dict:
    state = _as_state(state)
    state = _apply_strategy(state, feedback=state.revision_request)
    state = _apply_content(state, feedback=state.revision_request, regenerated=True)
    state = _validate_review_render(state, include_review=True)
    state = state.model_copy(
        update={
            "agents_rerun": ["strategy", "content", "validation", "review"],
            "agents_skipped": ["brief", "asset"],
        }
    )
    return _dump(state)


def full_revision_node(state: WorkflowState | dict) -> dict:
    state = _as_state(state)
    brief = normalize_brief(state.campaign_brief)
    state = state.model_copy(update={"campaign_brief": brief})
    state = append_audit(state, "BRIEF_NORMALIZED", agent="brief_agent")
    state = _apply_strategy(state, feedback=state.revision_request)
    state = _apply_content(state, feedback=state.revision_request, regenerated=True)
    state = _apply_asset(state, feedback=state.revision_request)
    state = _validate_review_render(state, include_review=True)
    state = state.model_copy(
        update={
            "agents_rerun": ["brief", "strategy", "content", "asset", "validation", "review"],
            "agents_skipped": [],
        }
    )
    return _dump(state)


def _select_revision_branch(state: WorkflowState | dict) -> str:
    state = _as_state(state)
    return state.revision_target or "content"


def _build_generate_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("normalize_brief", normalize_brief_node)
    graph.add_node("build_strategy", build_strategy_node)
    graph.add_node("write_content", write_content_node)
    graph.add_node("select_asset", select_asset_node)
    graph.add_node("validate_review_render", validate_review_render_node)
    graph.add_edge(START, "normalize_brief")
    graph.add_edge("normalize_brief", "build_strategy")
    graph.add_edge("build_strategy", "write_content")
    graph.add_edge("write_content", "select_asset")
    graph.add_edge("select_asset", "validate_review_render")
    graph.add_edge("validate_review_render", END)
    return graph.compile()


def _build_revision_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("content", content_revision_node)
    graph.add_node("asset", asset_revision_node)
    graph.add_node("strategy", strategy_revision_node)
    graph.add_node("full_campaign", full_revision_node)
    graph.add_conditional_edges(
        START,
        _select_revision_branch,
        {
            "content": "content",
            "asset": "asset",
            "strategy": "strategy",
            "full_campaign": "full_campaign",
        },
    )
    graph.add_edge("content", END)
    graph.add_edge("asset", END)
    graph.add_edge("strategy", END)
    graph.add_edge("full_campaign", END)
    return graph.compile()


_GENERATE_GRAPH = None
_REVISION_GRAPH = None


def _generate_graph():
    global _GENERATE_GRAPH
    if _GENERATE_GRAPH is None:
        _GENERATE_GRAPH = _build_generate_graph()
    return _GENERATE_GRAPH


def _revision_graph():
    global _REVISION_GRAPH
    if _REVISION_GRAPH is None:
        _REVISION_GRAPH = _build_revision_graph()
    return _REVISION_GRAPH


def run_generate(brief: CampaignBrief) -> WorkflowState:
    product = find_approved_product(brief.product)
    if product is None:
        label = brief.product.strip() or "this product"
        return WorkflowState(
            campaign_brief=brief,
            workflow_status=WorkflowStatus.DRAFT,
            error_message=(
                f"I don't have an approved profile for {label}. "
                "Add it under Products first."
            ),
        )
    brief = brief.model_copy(update={"product": product.name})
    state = WorkflowState(campaign_brief=brief, workflow_status=WorkflowStatus.DRAFT)
    state = append_audit(state, "CAMPAIGN_CREATED")
    state = transition(state, WorkflowStatus.GENERATING)
    try:
        result = _generate_graph().invoke(state)
        return _as_state(result)
    except (LLMError, Exception) as exc:
        if isinstance(exc, IllegalTransition):
            raise
        failed = transition(state, WorkflowStatus.DRAFT)
        failed.error_message = "Unable to generate content. Please retry."
        return failed


def run_generate_from_message(text: str) -> WorkflowState:
    """Parse a Slack-style request, then run the generate graph once."""
    placeholder = CampaignBrief(
        campaign_id="",
        product="",
        audience="",
        goal="",
        tone="",
        key_message="",
        additional_context=text.strip(),
    )
    try:
        brief = parse_marketer_request(text)
    except Exception as exc:
        if isinstance(exc, IllegalTransition):
            raise
        failed = WorkflowState(
            campaign_brief=placeholder,
            workflow_status=WorkflowStatus.DRAFT,
            error_message="Unable to generate content. Please retry.",
        )
        return failed
    return run_generate(brief)


def run_revision(state: WorkflowState, feedback: str) -> WorkflowState:
    if state.workflow_status != WorkflowStatus.HUMAN_REVIEW:
        raise IllegalTransition(
            f"Cannot request a revision from {state.workflow_status.value}"
        )
    snapshot = state.model_copy(deep=True)
    working = transition(state, WorkflowStatus.REVISION)
    working.revision_request = feedback.strip()
    working = append_audit(
        working, "REVISION_REQUESTED", details=working.revision_request
    )
    target = route_revision(working.revision_request)
    working.revision_target = target
    working.version += 1
    working = append_audit(working, "REVISION_ROUTED", details=target)
    try:
        result = _revision_graph().invoke(working)
        return _as_state(result)
    except (LLMError, Exception) as exc:
        if isinstance(exc, IllegalTransition):
            raise
        snapshot.error_message = "Unable to generate content. Please retry."
        return snapshot


def approve(state: WorkflowState, approved_by: str = "Demo Marketer") -> WorkflowState:
    if state.workflow_status != WorkflowStatus.HUMAN_REVIEW:
        raise IllegalTransition(
            f"Cannot transition from {state.workflow_status.value} to APPROVED"
        )
    failed_checks = []
    if state.validation_results is not None:
        failed_checks = [
            check
            for check in state.validation_results.checks
            if check.status == CheckStatus.FAIL
        ]
    if state.validation_results is None or not state.validation_results.passed:
        names = [check.check.replace("_", " ") for check in failed_checks]
        if names:
            bullets = "\n- ".join(names)
            raise ApprovalError(
                f"Cannot approve campaign.\n\n{len(names)} validation checks failed:\n- {bullets}"
            )
        raise ApprovalError("Cannot approve campaign.\n\nValidation has not passed.")
    state = transition(state, WorkflowStatus.APPROVED)
    state = state.model_copy(update={"approved_by": approved_by, "error_message": None})
    return append_audit(state, "HUMAN_APPROVED", details=f"Approved by {approved_by}")


def publish(state: WorkflowState) -> WorkflowState:
    if state.workflow_status != WorkflowStatus.APPROVED:
        raise IllegalTransition(
            f"Cannot transition from {state.workflow_status.value} to PUBLISHED"
        )
    settings = get_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        settings.output_dir
        / f"{state.campaign_brief.campaign_id}_v{state.version}.html"
    )
    output_path.write_text(state.rendered_html or "", encoding="utf-8")
    state = transition(state, WorkflowStatus.PUBLISHED)
    state = state.model_copy(update={"published_at": datetime.now(timezone.utc)})
    return append_audit(state, "PUBLISHED", details=str(output_path))
