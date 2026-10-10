"""Create simple local campaign images. Run once during setup."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
NAVY = (35, 47, 62)
ORANGE = (255, 153, 0)
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _card(filename: str, title: str, subtitle: str) -> None:
    image = Image.new("RGB", (600, 280), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 252, 600, 280], fill=ORANGE)
    draw.text((32, 88), title, fill=WHITE, font=_font(32))
    draw.text((32, 136), subtitle, fill=(209, 213, 219), font=_font(18))
    ASSETS.mkdir(parents=True, exist_ok=True)
    image.save(ASSETS / filename, "PNG")


def main() -> None:
    _card("bedrock-hero.png", "Amazon Bedrock", "Foundation models as a managed service")
    _card("aws-ai.png", "AWS AI", "Build and scale generative AI")
    _card("aws-logo.png", "AWS", "ISV campaign studio")


if __name__ == "__main__":
    main()
