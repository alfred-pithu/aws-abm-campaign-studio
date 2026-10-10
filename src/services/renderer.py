"""Deterministic HTML rendering. The LLM never generates HTML."""

import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import PROJECT_ROOT, get_settings
from src.models.assets import SelectedAsset
from src.models.content import EmailContent


def _data_uri(path: Path) -> str:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64,{payload}"


def render_email(content: EmailContent, asset: SelectedAsset) -> str:
    settings = get_settings()
    env = Environment(
        loader=FileSystemLoader(str(settings.templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("email.html")
    image_path = PROJECT_ROOT / asset.path
    hero_src = _data_uri(image_path) if image_path.is_file() else ""
    return template.render(
        subject=content.subject,
        preheader=content.preheader,
        headline=content.headline,
        body_paragraphs=content.body_paragraphs,
        cta_text=content.cta_text,
        hero_src=hero_src,
        asset_alt=asset.name or "Campaign image",
    )
