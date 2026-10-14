"""Products page: generate a draft profile, then human-approve it to JSON."""

from __future__ import annotations

import streamlit as st

from src.agents.onboarding_agent import generate_product_profile
from src.models.campaign import ProductClaim
from src.models.product import ProductProfile, ProductProfileDraft
from src.services.claims import (
    DuplicateProductError,
    approve_product,
    load_claims,
    load_products,
)
from src.services.llm import LLMError


def _approved_products() -> list[ProductProfile]:
    return [product for product in load_products() if product.status == "approved"]


def _list_claims(product_name: str) -> list[ProductClaim]:
    return [
        claim
        for claim in load_claims()
        if claim.approved and claim.product == product_name
    ]


def _draft_from_form(profile: ProductProfile, claims_rows: list[dict], warning: str) -> ProductProfileDraft:
    claims = []
    for row in claims_rows:
        text = str(row.get("claim", "")).strip()
        if not text:
            continue
        claims.append(
            ProductClaim(
                claim_id="",
                product=profile.name,
                claim=text,
                source=str(row.get("source", "")).strip(),
                approved=False,
            )
        )
    return ProductProfileDraft(profile=profile, claims=claims, warning=warning)


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def render_products_page() -> None:
    if "product_draft" not in st.session_state:
        st.session_state.product_draft = None

    products = _approved_products()
    st.subheader("Approved products")
    if not products:
        st.caption("No approved products yet.")
    for product in products:
        claims = _list_claims(product.name)
        with st.expander(product.name, expanded=product.name == "Amazon Bedrock"):
            st.write(product.short_description)
            st.caption(product.category or "Uncategorized")
            if product.capabilities:
                st.markdown("**Capabilities**")
                for item in product.capabilities:
                    st.markdown(f"- {item}")
            if claims:
                st.markdown("**Approved claims**")
                for claim in claims:
                    st.markdown(f"- `{claim.claim_id}` — {claim.claim}")

    draft: ProductProfileDraft | None = st.session_state.product_draft
    if draft is not None:
        _render_draft(draft)
        return

    st.subheader("Add product")
    with st.form("add_product"):
        name = st.text_input("Product name")
        url = st.text_input("Product URL")
        description = st.text_area("Description")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Generate product profile", type="primary")
    if not submitted:
        return
    if not name.strip() or not (url.strip() or description.strip()):
        st.error("Name and a URL or description are required.")
        return
    with st.spinner("Generating product profile…"):
        try:
            st.session_state.product_draft = generate_product_profile(
                name=name,
                url=url,
                description=description,
                notes=notes,
            )
        except LLMError:
            st.error("Unable to generate a product profile. Please retry.")
            return
    st.rerun()


def _render_draft(draft: ProductProfileDraft) -> None:
    st.subheader("Review draft")
    st.caption("Claims stay unapproved until you click Approve product.")
    if draft.insufficient_source:
        st.warning(draft.warning or "Not enough source material to generate a profile.")
    elif draft.warning:
        st.info(draft.warning)

    profile = draft.profile
    with st.form("review_product_draft"):
        name = st.text_input("Name", value=profile.name)
        short_description = st.text_area(
            "Short description", value=profile.short_description
        )
        category = st.text_input("Category", value=profile.category)
        source_url = st.text_input("Source URL", value=profile.source_url)
        capabilities = st.text_area(
            "Capabilities (one per line)",
            value="\n".join(profile.capabilities),
        )
        audiences = st.text_area(
            "Target audiences (one per line)",
            value="\n".join(profile.target_audiences),
        )
        use_cases = st.text_area(
            "Use cases (one per line)",
            value="\n".join(profile.use_cases),
        )
        differentiators = st.text_area(
            "Differentiators (one per line)",
            value="\n".join(profile.differentiators),
        )
        claims_rows = [
            {"claim": claim.claim, "source": claim.source} for claim in draft.claims
        ]
        edited_claims = st.data_editor(
            claims_rows or [{"claim": "", "source": ""}],
            num_rows="dynamic",
            width="stretch",
            key="draft_claims_editor",
        )
        approve_clicked = st.form_submit_button("Approve product", type="primary")
        cancel_clicked = st.form_submit_button("Cancel")

    if cancel_clicked:
        st.session_state.product_draft = None
        st.rerun()

    if not approve_clicked:
        return

    updated_profile = ProductProfile(
        product_id=profile.product_id,
        name=name.strip(),
        short_description=short_description.strip(),
        category=category.strip(),
        capabilities=_split_lines(capabilities),
        target_audiences=_split_lines(audiences),
        use_cases=_split_lines(use_cases),
        differentiators=_split_lines(differentiators),
        source_url=source_url.strip(),
        status="draft",
    )
    updated = _draft_from_form(updated_profile, list(edited_claims), draft.warning)
    if not updated.profile.name:
        st.error("Product name is required.")
        return
    try:
        saved = approve_product(updated)
    except DuplicateProductError as exc:
        st.error(str(exc))
        return
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state.product_draft = None
    st.success(
        f"{saved.name} is approved. In Campaign, type Promote {saved.name} to CTOs."
    )
    st.rerun()
