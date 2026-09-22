"""Compose the MF10 Flux brand assets. Copyright 2026 Gabriele Pennacchia."""

from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components/dreame_mf10_flux/brand"
BRAND.mkdir(exist_ok=True)
FAN = Image.open(ROOT / "docs/images/mf10.png").convert("RGBA")
WORDMARK = Image.open(ROOT / "docs/images/dreame-wordmark.png").convert("RGBA")
METADATA = PngImagePlugin.PngInfo()
METADATA.add_text("Author", "Gabriele Pennacchia")
METADATA.add_text("Title", "Dreame MF10 Flux")


def glyphs():
    """Build the needed lettering from the supplied wordmark, without system fonts.

    M is taken directly from the artwork. F and L retain the E's bars and stem;
    U and zero use the D's curves. The remaining two characters follow the same
    stroke width. This is matching artwork, not an official Dreame font file.
    """
    alpha = WORDMARK.getchannel("A")
    letter_d = alpha.crop((0, 0, 511, 512))
    letter_e = alpha.crop((1488, 0, 1924, 512))
    letter_m = alpha.crop((2834, 0, 3371, 512))
    stroke = 99

    letter_f = letter_e.copy()
    ImageDraw.Draw(letter_f).rectangle((stroke, 390, 436, 512), fill=0)
    letter_l = letter_e.copy()
    ImageDraw.Draw(letter_l).rectangle((stroke, 0, 436, 405), fill=0)

    letter_u = letter_d.transpose(Image.Transpose.ROTATE_270)
    ImageDraw.Draw(letter_u).rectangle((stroke, 0, 511 - stroke, stroke), fill=0)
    curve = letter_d.crop((255, 0, 511, 512))
    zero = Image.new("L", (512, 512))
    zero.paste(curve.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (0, 0))
    zero.paste(curve, (256, 0))

    one = Image.new("L", (232, 512))
    ImageDraw.Draw(one).polygon(
        [(0, 141), (128, 0), (232, 0), (232, 511), (128, 511), (128, 151), (69, 216)],
        fill=255,
    )
    letter_x = Image.new("L", (512, 512))
    draw = ImageDraw.Draw(letter_x)
    draw.polygon([(0, 0), (128, 0), (512, 511), (384, 511)], fill=255)
    draw.polygon([(384, 0), (512, 0), (128, 511), (0, 511)], fill=255)
    return {
        "M": letter_m,
        "F": letter_f,
        "1": one,
        "0": zero,
        "L": letter_l,
        "U": letter_u,
        "X": letter_x,
    }


GLYPHS = glyphs()


def lettering(text, width, foreground, accent):
    """Render consistent MF10/Flux lettering with fixed, reproducible spacing."""
    tracking = 114
    natural_width = sum(GLYPHS[c].width if c != " " else 150 for c in text)
    natural_width += tracking * (len(text) - 1)
    result = Image.new("RGBA", (natural_width, 512))
    x = 0
    flux = text.startswith("FLUX")
    for character in text:
        if character == " ":
            x += 150 + tracking
            flux = True
            continue
        mask = GLYPHS[character]
        color = accent if flux else foreground
        ink = Image.new("RGBA", mask.size, color)
        ink.putalpha(mask)
        result.alpha_composite(ink, (x, 0))
        x += mask.width + tracking
    height = round(512 * width / natural_width)
    return result.resize((width, height), Image.Resampling.LANCZOS)


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
    badge = lettering("FLUX", 166, "#77ede8", "#77ede8")
    icon.alpha_composite(badge, ((512 - badge.width) // 2, 457 - badge.height // 2))
    save_pair(icon, "dark_icon" if dark else "icon")

    logo = Image.new("RGBA", (1280, 360))
    logo.alpha_composite(FAN.resize((344, 344), Image.Resampling.LANCZOS), (0, 8))
    mark = WORDMARK.copy()
    if dark:
        mark = Image.new("RGBA", mark.size, foreground)
        mark.putalpha(WORDMARK.getchannel("A"))
    mark.thumbnail((760, 110), Image.Resampling.LANCZOS)
    logo.alpha_composite(mark, (382, 48))
    subtitle = lettering("MF10 FLUX", mark.width, foreground, accent)
    logo.alpha_composite(subtitle, (382, 195))
    save_pair(logo, "dark_logo" if dark else "logo")
    if not dark:
        panel = Image.new("RGBA", logo.size, "white")
        panel.alpha_composite(logo)
        panel.resize((640, 180), Image.Resampling.LANCZOS).save(
            ROOT / "docs/images/brand.png", pnginfo=METADATA
        )
