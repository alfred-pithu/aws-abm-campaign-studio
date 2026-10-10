# AWS ISV Campaign Studio (POC)

A vertical slice of the AWS ISV ABM content workflow. This is **not** a production marketing platform.

It demonstrates that an ambiguous enterprise workflow can be split into the right AI and deterministic pieces, with least-privilege agent context, validation, a mandatory human approval gate, targeted revisions, and an audit trail.

## What this is

```
Marketer
   ↓
Brief
   ↓
Strategy
   ↓
Content
   ↓
Asset
   ↓
Validation
   ↓
Review
   ↓
Human Approval
   ↓
Publish
```

One product (Amazon Bedrock), one audience (CTOs at AI startups), one channel (email). Runnable locally with Streamlit.

## Architecture

AI writes the words. Code builds the page. Humans approve before anything is marked published.

```
Marketer message (Streamlit chat)
        ↓
LangGraph generate
  Brief Agent → Strategy Agent → Content Agent → Asset Agent
        ↓
Deterministic validators (no LLM)
        ↓
Review Agent (judgment signals)
        ↓
Jinja2 HTML renderer
        ↓
HUMAN_REVIEW
   ↙            ↘
Revision      Approve
   ↓              ↓
Targeted      APPROVED
rerun             ↓
               PUBLISHED
               (HTML file + audit)
```

## Design principles

1. AI handles judgment and generation.
2. Deterministic code handles hard constraints.
3. Human approval is mandatory. `GENERATING → PUBLISHED` is impossible.
4. Agents have least-privilege context. No agent receives the entire application state.
5. Generated content is structured JSON (`EmailContent`). The LLM never emits HTML.
6. HTML is deterministically rendered with Jinja2.
7. Revisions are targeted rather than full workflow reruns.

## Context isolation

| Component | Sees | Does not see |
| --- | --- | --- |
| Brief Agent | Campaign input | Claims, assets, HTML, publish |
| Strategy Agent | Brief, brand rules, approved claims | Assets, HTML, publish |
| Content Agent | Brief, strategy, brand rules, claims | Assets, HTML, publish |
| Asset Agent | Brief, strategy, asset registry | Claims to rewrite, HTML, publish |
| Review Agent | Brief, strategy, content, validation, brand rules, claims | Publish API |
| Validators / renderer / publish | Structured objects | LLM calls |

Publishing is a Python function. Agents cannot call it.

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add your OpenRouter (or OpenAI) key to .env
streamlit run app.py
```

This POC talks to an OpenAI-compatible API. OpenRouter works out of the box with:

```
OPENAI_API_KEY=sk-or-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
```

LangSmith is optional. If `LANGCHAIN_TRACING_V2=true` and LangSmith credentials are set, traces are recorded. The app still runs if they are not.

## Share a URL (Streamlit Community Cloud)

This is the fastest way to send an interviewer a link.

1. Put the repo on GitHub (public is easiest).
2. Go to [https://share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **Create app** → pick this repo → main file `app.py`.
4. In **Advanced settings → Secrets**, paste:

```toml
OPENAI_API_KEY = "sk-or-..."
OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_MODEL = "openai/gpt-4o-mini"
```

5. Deploy. The URL looks like `https://<app-name>-<you>.streamlit.app`.

Do not commit `.env`. The interviewer will burn your OpenRouter credits when they click generate.

## Demo flow

1. Open the application.
2. Click **Send demo request**, or type the Amazon Bedrock / CTOs request in the composer.
3. Read the thread: brief, strategy, draft copy, selected image, validation, AI review, then the email preview.
4. Confirm status is **HUMAN_REVIEW**.
5. Click **Request changes** (or type in the composer): `Make the tone less salesy and more technical.`
6. Confirm the bot says the revision target is **CONTENT**, reran content/validation/review, and skipped the rest.
7. Confirm the preview updates in a new bubble.
8. Click **Approve and publish** in the header.
9. Confirm the thread shows campaign id, version, and Demo Marketer, and the composer is frozen.
10. Open **Audit trail** at the bottom of the thread and walk the lifecycle.
11. Optional: click **Start new conversation**, then `pytest tests/ -v`

## Not in this POC

Slack, landing pages, four-audience matrix, DAM/CRM APIs, Brand Code YAML, product onboarding from URLs, vision QA, Docker/Kubernetes, authentication, real email send, vector search, FastAPI.
