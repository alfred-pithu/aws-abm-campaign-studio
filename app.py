"""AWS ISV Campaign Studio — conversational Streamlit UI.

This module is a chat shell. It does not call the OpenAI SDK.
LLM access is isolated to `src.services.llm`.
"""

import streamlit as st

from src.config import DEMO_REQUEST
from src.graph.workflow import (
    ApprovalError,
    IllegalTransition,
    approve,
    publish,
    run_generate_from_message,
    run_revision,
)
from src.models.campaign import WorkflowStatus
from src.services.persistence import save_campaign
from src.ui.products import render_products_page
from src.ui.transcript import (
    ChatMessage,
    append_generate_messages,
    append_publish_message,
    append_revision_messages,
    render_messages,
)

ERROR_TEXT = "Unable to generate content. Please retry."

st.set_page_config(
    page_title="AWS ISV Campaign Studio",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp { background: #f7f8fa; color: #16191f; }
      h1, h2, h3, p, label, .stMarkdown { color: #16191f; }
      div[data-testid="stMetricValue"] { font-size: 1.4rem; }
      .status-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.02em;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_COLORS = {
    WorkflowStatus.DRAFT: ("#e5e7eb", "#111827"),
    WorkflowStatus.GENERATING: ("#fde68a", "#92400e"),
    WorkflowStatus.VALIDATING: ("#fde68a", "#92400e"),
    WorkflowStatus.PREVIEW: ("#dbeafe", "#1e40af"),
    WorkflowStatus.HUMAN_REVIEW: ("#ffedd5", "#9a3412"),
    WorkflowStatus.REVISION: ("#fde68a", "#92400e"),
    WorkflowStatus.APPROVED: ("#d1fae5", "#065f46"),
    WorkflowStatus.PUBLISHED: ("#d1fae5", "#065f46"),
}


def _init_state() -> None:
    defaults = {
        "messages": [],
        "campaign": None,
        "awaiting_revision": False,
        "pending_action": None,
        "pending_text": "",
        "busy": False,
        "product_draft": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _status_badge(status: WorkflowStatus) -> str:
    bg, fg = STATUS_COLORS.get(status, ("#e5e7eb", "#111827"))
    return (
        f'<span class="status-pill" style="background:{bg};color:{fg};">'
        f"{status.value}</span>"
    )


def _reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.campaign = None
    st.session_state.awaiting_revision = False
    st.session_state.pending_action = None
    st.session_state.pending_text = ""
    st.session_state.busy = False


def _queue_user_message(text: str) -> None:
    """Paint the user bubble first, then generate on the next run."""
    if st.session_state.busy:
        return
    campaign = st.session_state.campaign
    status = campaign.workflow_status if campaign is not None else None
    if status == WorkflowStatus.PUBLISHED:
        return
    if campaign is None or status == WorkflowStatus.DRAFT:
        action = "generate"
    elif status == WorkflowStatus.HUMAN_REVIEW:
        action = "revision"
    else:
        return
    st.session_state.messages.append(ChatMessage(role="user", kind="user", text=text))
    st.session_state.pending_action = action
    st.session_state.pending_text = text
    st.session_state.busy = True
    st.session_state.awaiting_revision = False
    st.rerun()


def _finish_error(result) -> None:
    text = ERROR_TEXT
    if result is not None and result.error_message:
        text = result.error_message
    st.session_state.messages.append(
        ChatMessage(role="assistant", kind="error", text=text)
    )
    if result is not None:
        st.session_state.campaign = result
    st.session_state.busy = False
    st.rerun()


def _process_pending() -> None:
    action = st.session_state.pending_action
    text = st.session_state.pending_text
    if action not in {"generate", "revision"}:
        return
    st.session_state.pending_action = None
    st.session_state.pending_text = ""
    label = (
        "Generating campaign…" if action == "generate" else "Applying targeted revision…"
    )
    with st.chat_message("assistant"):
        with st.spinner(label):
            try:
                if action == "generate":
                    result = run_generate_from_message(text)
                else:
                    result = run_revision(st.session_state.campaign, text)
            except Exception:
                result = None
    if result is None or result.error_message:
        _finish_error(result)
        return
    save_campaign(result)
    st.session_state.campaign = result
    if action == "generate":
        append_generate_messages(st.session_state.messages, result)
    else:
        append_revision_messages(st.session_state.messages, result, text)
    st.session_state.busy = False
    st.rerun()


def _approve_and_publish() -> None:
    campaign = st.session_state.campaign
    try:
        updated = approve(campaign, approved_by="Demo Marketer")
        updated = publish(updated)
        save_campaign(updated)
        st.session_state.campaign = updated
        st.session_state.awaiting_revision = False
        append_publish_message(st.session_state.messages, updated)
        st.rerun()
    except (ApprovalError, IllegalTransition) as exc:
        st.error(str(exc))


def _start_revision() -> None:
    st.session_state.awaiting_revision = True


def _render_revision_form(form_key: str) -> None:
    with st.form(form_key):
        st.markdown("**What should I change?**")
        feedback = st.text_area(
            "Revision feedback",
            placeholder="Make the tone less salesy and more technical.",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Send revision", type="primary")
    if submitted:
        if not feedback.strip():
            st.error("Tell me what to change first.")
        else:
            _queue_user_message(feedback.strip())


def _render_review_actions(key_prefix: str) -> None:
    campaign = st.session_state.campaign
    validation_ok = bool(
        campaign.validation_results and campaign.validation_results.passed
    )
    disabled = st.session_state.busy or not validation_ok
    if not validation_ok:
        st.warning("Cannot approve campaign until validation passes.")
    approve_col, revise_col = st.columns(2)
    with approve_col:
        if st.button(
            "Approve and publish",
            type="primary",
            disabled=disabled,
            key=f"{key_prefix}_approve",
            width="stretch",
        ):
            _approve_and_publish()
    with revise_col:
        st.button(
            "Request changes",
            disabled=st.session_state.busy,
            key=f"{key_prefix}_revise",
            width="stretch",
            on_click=_start_revision,
        )
    if st.session_state.awaiting_revision:
        _render_revision_form(f"revision_form_{key_prefix}")


_init_state()
page = st.radio("Section", ["Campaign", "Products"], horizontal=True)
if page == "Products":
    st.title("Product knowledge")
    st.caption("Generate a draft, approve it, then promote that product in Campaign.")
    render_products_page()
    st.stop()

campaign = st.session_state.campaign
busy = bool(st.session_state.busy)
published = (
    campaign is not None and campaign.workflow_status == WorkflowStatus.PUBLISHED
)
in_review = (
    campaign is not None
    and campaign.workflow_status == WorkflowStatus.HUMAN_REVIEW
    and not busy
)
can_start = (not st.session_state.messages) and campaign is None and not busy

header_left, header_right = st.columns([3, 2])
with header_left:
    st.title("AWS ISV Campaign Studio")
    st.caption("AI-powered ABM content workflow")
with header_right:
    if campaign is not None:
        st.markdown(_status_badge(campaign.workflow_status), unsafe_allow_html=True)
        st.caption(f"Version {campaign.version}")
    elif busy:
        st.markdown(_status_badge(WorkflowStatus.GENERATING), unsafe_allow_html=True)
    if can_start:
        if st.button("Send demo request", key="send_demo"):
            _queue_user_message(DEMO_REQUEST)
    if published:
        if st.button("Start new conversation", key="reset_conversation"):
            _reset_conversation()
            st.rerun()

def _render_message_review_actions() -> None:
    _render_review_actions("message")


render_messages(
    st.session_state.messages,
    after_status=_render_message_review_actions if in_review else None,
)

if st.session_state.pending_action in {"generate", "revision"}:
    _process_pending()

if campaign is not None and campaign.audit_events:
    with st.expander("Audit trail"):
        rows = [
            {
                "timestamp": event.timestamp.isoformat(),
                "event": event.event,
                "agent": event.agent or "",
                "version": event.version,
                "details": event.details or "",
            }
            for event in campaign.audit_events
        ]
        st.dataframe(rows, hide_index=True, width="stretch")

if published:
    composer_placeholder = "Conversation closed. Start a new conversation to continue."
elif in_review:
    composer_placeholder = "Make the tone less salesy…"
elif busy:
    composer_placeholder = "Working…"
else:
    composer_placeholder = "Message Campaign Studio…"

prompt = st.chat_input(
    composer_placeholder, disabled=published or busy, key="composer"
)
if prompt and prompt.strip() and not published and not busy:
    _queue_user_message(prompt.strip())
