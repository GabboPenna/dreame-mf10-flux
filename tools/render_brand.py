"""Compose the MF10 Flux brand assets. Copyright 2026 Gabriele Pennacchia."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_mf10_flux/brand"
BRAND.mkdir(exist_ok=True)
FAN = Image.open(ROOT / "docs/images/mf10.png").convert("RGBA")
WORDMARK = Image.open(ROOT / "docs/images/dreame-wordmark.png").convert("RGBA")
METADATA = PngImagePlugin.PngInfo()
METADATA.add_text("Author", "Gabriele Pennacchia")
METADATA.add_text("Title", "Dreame MF10 Flux")


def font(size):
    """Use an installed sans-serif, with a portable Pillow fallback."""
    for path in ("C:/Windows/Fonts/seguisb.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def save_pair(image, name):
    image.save(BRAND / f"{name}@2x.png", pnginfo=METADATA)
    image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS).save(
        BRAND / f"{name}.png", pnginfo=METADATA
    )


for dark in (False, True):
    foreground = "#f5f6f8" if dark else "#151922"
    accent = "#77ede8" if dark else "#117e83"
    icon = Image.new("RGBA", (512, 512))
    icon.alpha_composite(FAN.resize((470, 470), Image.Resampling.LANCZOS), (21, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((155, 423, 357, 491), radius=24, fill="#101d27")
    draw.text((256, 453), "FLUX", anchor="mm", font=font(46), fill="#77ede8")
    save_pair(icon, "dark_icon" if dark else "icon")

    logo = Image.new("RGBA", (1280, 360))
    logo.alpha_composite(FAN.resize((344, 344), Image.Resampling.LANCZOS), (0, 8))
    mark = WORDMARK.copy()
    if dark:
        mark = Image.new("RGBA", mark.size, foreground)
        mark.putalpha(WORDMARK.getchannel("A"))
    mark.thumbnail((760, 110), Image.Resampling.LANCZOS)
    logo.alpha_composite(mark, (382, 48))
    draw = ImageDraw.Draw(logo)
    draw.text((373, 164), "MF10", font=font(113), fill=foreground)
    draw.text((723, 164), "FLUX", font=font(113), fill=accent)
    save_pair(logo, "dark_logo" if dark else "logo")
    if not dark:
        panel = Image.new("RGBA", logo.size, "white")
        panel.alpha_composite(logo)
        panel.resize((640, 180), Image.Resampling.LANCZOS).save(
            ROOT / "docs/images/brand.png", pnginfo=METADATA
        )
