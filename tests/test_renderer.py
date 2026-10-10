from src.services.renderer import render_email
from tests.conftest import sample_asset, sample_content


def test_content_json_renders_to_html():
    content = sample_content()
    html = render_email(content, sample_asset())
    assert "<img" in html
    assert content.headline in html
    assert content.cta_text in html
    assert "{{" not in html
    assert "This is a POC preview" in html
