"""
thumbnail.py

Generates a YouTube thumbnail for a duelingbook replay.

Layout (1280x720):
  - Black background
  - Left half: card artwork for deck1
  - Right half: card artwork for deck2
  - VS badge in the center
  - Deck names at the bottom of each half
  - Label left / label right below deck names (green, Impact)
  - Yu-Gi-Oh! logo at the top center

Usage:
    from postprocess.thumbnail import ThumbnailGenerator
    gen = ThumbnailGenerator()
    path = gen.generate(
        deck1="Snake-Eyes", card1="Snake-Eye Ash",
        deck2="Branded",    card2="Albaz the Branded",
        label_left="DUELINGBOOK", label_right="HIGH RATED",
        output_path="output/thumbnails/replay_123.jpg",
    )
"""

import io
import logging
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# Thumbnail dimensions (YouTube standard)
W, H = 1280, 720

FONT_IMPACT      = "/System/Library/Fonts/Supplemental/Impact.ttf"
FONT_ARIAL_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
FONT_ARIAL_BOLD  = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

YUGIOH_LOGO  = "assets/Yugioh logo.webp"
VS_IMAGE     = "assets/VS Image.png"
LIGHTNING    = "assets/lightning.png"

YGOAPI_BASE = "https://db.ygoprodeck.com/api/v7/cardinfo.php"


class ThumbnailGenerator:

    def generate(
        self,
        deck1: str,
        card1: str,
        deck2: str,
        card2: str,
        label_left: str,
        label_right: str,
        output_path: str,
    ) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Fetching artwork for: {card1} | {card2}")
        img1 = self._fetch_card_art(card1)  # raises ValueError if not found
        img2 = self._fetch_card_art(card2)  # raises ValueError if not found

        canvas = self._compose(img1, img2, deck1, deck2, label_left, label_right)
        canvas.save(str(output_path), "JPEG", quality=95)
        logger.info(f"Thumbnail saved: {output_path}")
        return str(output_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_card_art(self, card_name: str) -> Image.Image:
        """Downloads the card artwork from YGOPRODeck API.

        Raises ValueError if the card is not found, so the caller can report it.
        """
        r = requests.get(YGOAPI_BASE, params={"name": card_name}, timeout=10)
        if r.status_code == 404 or "data" not in r.json():
            raise ValueError(f"Carta no encontrada en YGOPRODeck: '{card_name}'")
        r.raise_for_status()
        card_data = r.json()["data"][0]
        image_url = card_data["card_images"][0]["image_url_cropped"]
        img_r = requests.get(image_url, timeout=15)
        img_r.raise_for_status()
        return Image.open(io.BytesIO(img_r.content)).convert("RGBA")

    def _placeholder(self, name: str) -> Image.Image:
        img = Image.new("RGBA", (421, 614), (40, 40, 60, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 280), name, fill=(200, 200, 200, 255))
        return img

    def _compose(
        self,
        img1: Image.Image,
        img2: Image.Image,
        deck1: str,
        deck2: str,
        label_left: str,
        label_right: str,
    ) -> Image.Image:
        canvas = Image.new("RGB", (W, H), (0, 0, 0))

        half = W // 2  # 640 — each card occupies exactly one half

        # --- Left card (0 to 640) ---
        left_art = self._fit_card(img1, half, H)
        canvas.paste(left_art.convert("RGB"), (0, 0))

        # Narrow gradient only near the center seam (last 120px of each half)
        grad_left = self._gradient_overlay(120, H, direction="right")
        canvas.paste(grad_left, (half - 120, 0), grad_left)

        # --- Right card (640 to 1280) ---
        right_art = self._fit_card(img2, half, H)
        canvas.paste(right_art.convert("RGB"), (half, 0))

        grad_right = self._gradient_overlay(120, H, direction="left")
        canvas.paste(grad_right, (half, 0), grad_right)

        # --- Lightning divider ---
        self._paste_lightning(canvas)

        # --- VS badge (center) ---
        self._draw_vs(canvas)

        # --- Yu-Gi-Oh logo ---
        self._draw_logo(canvas)

        # Text centers: 25% and 75% of width
        cx_left  = half // 2        # 320
        cx_right = half + half // 2  # 960

        # 45% of total width = 576px max per side
        max_text_w = int(W * 0.45)
        draw = ImageDraw.Draw(canvas)

        # --- Deck names (white, Impact) ---
        self._draw_text_outlined(draw, deck1, (cx_left,  565), size=120, anchor="mm", font=FONT_IMPACT,
                                  max_width=max_text_w)
        self._draw_text_outlined(draw, deck2, (cx_right, 565), size=120, anchor="mm", font=FONT_IMPACT,
                                  max_width=max_text_w)

        # --- Labels (green, Impact) ---
        green = (80, 200, 60)
        self._draw_text_outlined(draw, label_left,  (cx_left,  660), size=90, anchor="mm",
                                  font=FONT_IMPACT, fill=green, max_width=max_text_w)
        self._draw_text_outlined(draw, label_right, (cx_right, 660), size=90, anchor="mm",
                                  font=FONT_IMPACT, fill=green, max_width=max_text_w)

        return canvas

    def _fit_card(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Scales card art to fill the target area (crop to fit)."""
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))

    def _gradient_overlay(self, w: int, h: int, direction: str) -> Image.Image:
        """Creates a dark-to-transparent gradient for blending the two halves."""
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(grad)
        steps = w
        for i in range(steps):
            if direction == "right":
                alpha = int(255 * (i / steps) ** 1.5)
                x = i
            else:
                alpha = int(255 * ((steps - i) / steps) ** 1.5)
                x = i
            draw.line([(x, 0), (x, h)], fill=(0, 0, 0, alpha))
        return grad

    def _paste_lightning(self, canvas: Image.Image) -> None:
        """Places the lightning PNG as the center divider, scaled to full height."""
        path = Path(LIGHTNING)
        if not path.exists():
            return
        try:
            img = Image.open(str(path)).convert("RGBA")
            # Scale to full canvas height keeping aspect ratio
            ratio = H / img.height
            new_w = int(img.width * ratio)
            img = img.resize((new_w, H), Image.LANCZOS)
            cx = W // 2
            canvas.paste(img, (cx - new_w // 2, 0), img)
        except Exception as e:
            logger.warning(f"Could not place lightning: {e}")

    def _draw_lightning(self, canvas: Image.Image) -> None:
        """Draws a zigzag lightning bolt as the center divider."""
        draw = ImageDraw.Draw(canvas)
        cx = W // 2
        # Lightning bolt points (zigzag from top to bottom)
        bolt = [
            (cx + 18,  0),
            (cx - 10, 280),
            (cx + 10, 280),
            (cx - 18, H),
            (cx + 10, 400),
            (cx - 10, 400),
            (cx + 18,  0),
        ]
        # White glow
        draw.polygon(bolt, fill=(255, 255, 220, 0))
        for offset in range(8, 0, -2):
            expanded = [(x + (1 if x > cx else -1) * offset, y) for x, y in bolt]
            alpha = int(120 * (offset / 8))
            glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            gd.polygon(expanded, fill=(255, 220, 50, alpha))
            canvas.paste(Image.new("RGB", (W, H), 0), (0, 0), glow_layer)

        draw.polygon(bolt, fill=(255, 240, 80))
        # White core
        core = [(x + (1 if x > cx else -1) * -3, y) for x, y in bolt]
        draw.polygon(core, fill=(255, 255, 255))

    def _draw_vs(self, canvas: Image.Image) -> None:
        """Places the VS image in the center."""
        vs_path = Path(VS_IMAGE)
        if not vs_path.exists():
            return
        try:
            vs = Image.open(str(vs_path)).convert("RGBA")
            vs.thumbnail((280, 280), Image.LANCZOS)
            vw, vh = vs.size
            cx, cy = W // 2, H // 2
            canvas.paste(vs, (cx - vw // 2, cy - vh // 2), vs)
        except Exception as e:
            logger.warning(f"Could not place VS image: {e}")

    def _draw_logo(self, canvas: Image.Image) -> None:
        """Places the Yu-Gi-Oh! logo at the top center."""
        logo_path = Path(YUGIOH_LOGO)
        if not logo_path.exists():
            return
        try:
            logo = Image.open(str(logo_path)).convert("RGBA")
            # Scale to fit within 320x100 keeping aspect ratio
            logo.thumbnail((320, 100), Image.LANCZOS)
            lw, lh = logo.size
            x = (W - lw) // 2
            canvas.paste(logo, (x, 10), logo)
        except Exception as e:
            logger.warning(f"Could not place logo: {e}")

    def _draw_text_outlined(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        pos: tuple,
        size: int,
        anchor: str = "mm",
        font: str = FONT_IMPACT,
        fill: tuple = (255, 255, 255),
        outline_color: tuple = (0, 0, 0),
        outline_width: int = 3,
        max_width: int = None,
    ) -> None:
        try:
            fnt = ImageFont.truetype(font, size)
        except Exception:
            fnt = ImageFont.load_default()

        # Shrink font until text fits within max_width
        if max_width:
            while size > 10:
                fnt = ImageFont.truetype(font, size)
                bbox = draw.textbbox((0, 0), text, font=fnt, anchor="lt")
                if (bbox[2] - bbox[0]) <= max_width:
                    break
                size -= 2

        x, y = pos
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=fnt,
                              fill=outline_color, anchor=anchor)
        draw.text(pos, text, font=fnt, fill=fill, anchor=anchor)
