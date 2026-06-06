import json
import logging
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class Template:

    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.width: int = data["width"]
        self.height: int = data["height"]
        # Support background section (new) ou background_color (legacy)
        bg = data.get("background", {})
        self.bg_type: str = bg.get("type", "color")
        self.bg_image_path: Optional[str] = bg.get("path")
        self.bg_fallback: tuple = tuple(bg.get("fallback_color",
                                        data.get("background_color", [248, 248, 248])))
        self.slots: list = data["slots"]
        self.overlay_path: Optional[str] = data.get("overlay_path")
        self.text_elements: list = data.get("text_elements", [])
        self.title_zone: Optional[dict] = data.get("title_zone")
        self.description_zone: Optional[dict] = data.get("description_zone")
        self.decorations: list = data.get("decorations", [])

    @classmethod
    def from_file(cls, path: str) -> "Template":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def slot(self, index: int) -> Optional[dict]:
        return self.slots[index] if index < len(self.slots) else None


class Composer:

    def __init__(self, config):
        self._config = config
        self._templates_dir = Path(config.get("templates.templates_dir", "templates"))
        self._templates: dict = {}
        self._load_all()

    def _load_all(self):
        if not self._templates_dir.exists():
            logger.warning(f"Dossier templates introuvable : {self._templates_dir.resolve()}")
            return
        for path in sorted(self._templates_dir.glob("*.json")):
            try:
                t = Template.from_file(str(path))
                self._templates[path.stem] = t
                logger.info(f"Template charge : {path.stem} ({path.resolve()})")
            except Exception as e:
                logger.error(f"Erreur chargement template {path}: {e}")
        logger.info(f"Templates disponibles : {list(self._templates.keys())}")

    def available(self) -> List[str]:
        return list(self._templates.keys())

    def compose(
        self,
        photo_paths: List[str],
        template_name: str,
        output_path: str,
        font_path: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        logger.info(f"Composition : template='{template_name}' photos={len(photo_paths)}")

        template = self._templates.get(template_name)
        if not template:
            logger.warning(
                f"Template '{template_name}' introuvable dans {list(self._templates.keys())}. "
                f"Fallback vers premier template disponible."
            )
            if self._templates:
                template = next(iter(self._templates.values()))
                logger.info(f"Fallback template : {template.name}")
            else:
                logger.error("Aucun template disponible — composition automatique")
                return self._compose_auto(photo_paths, output_path)

        # Fond
        canvas = self._make_background(template)

        # Photos
        for i, photo_path in enumerate(photo_paths):
            slot = template.slot(i)
            if not slot:
                continue
            try:
                photo = Image.open(photo_path).convert("RGB")
                photo = self._fit_crop(photo, slot["width"], slot["height"])
                canvas.paste(photo, (slot["x"], slot["y"]))
            except Exception as e:
                logger.error(f"Erreur placement photo {photo_path}: {e}")

        if template.overlay_path:
            self._apply_overlay(canvas, template.overlay_path, template.width, template.height)

        for dec in template.decorations:
            self._draw_decoration(canvas, dec)

        if template.title_zone and title:
            self._draw_zone_text(canvas, template.title_zone, title, font_path)

        if template.description_zone and description:
            self._draw_zone_text(canvas, template.description_zone, description, font_path)

        for elem in template.text_elements:
            try:
                self._draw_text(canvas, elem, font_path)
            except Exception as e:
                logger.error(f"Erreur texte template: {e}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        quality = self._config.get("processing.jpeg_quality", 92)
        canvas.save(output_path, quality=quality)
        logger.info(f"Image finale -> {output_path}")
        return output_path

    # ------------------------------------------------------------------

    def _make_background(self, template: Template) -> Image.Image:
        """Crée le canvas de fond selon la configuration du template."""
        if template.bg_type == "image" and template.bg_image_path:
            p = Path(template.bg_image_path)
            if p.exists():
                try:
                    bg = Image.open(p).convert("RGB")
                    bg = self._fit_crop(bg, template.width, template.height)
                    logger.debug(f"Fond image : {p}")
                    return bg
                except Exception as e:
                    logger.warning(f"Fond image erreur ({p}): {e} — fallback couleur")
            else:
                logger.warning(f"Fond image introuvable : {p.resolve()} — fallback couleur")

        # Couleur de fond (fallback ou explicite)
        return Image.new("RGB", (template.width, template.height), template.bg_fallback)

    def _fit_crop(self, img: Image.Image, tw: int, th: int) -> Image.Image:
        src_r = img.width / img.height
        dst_r = tw / th
        if src_r > dst_r:
            new_h, new_w = th, int(th * src_r)
        else:
            new_w, new_h = tw, int(tw / src_r)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - tw) // 2
        top = (new_h - th) // 2
        return img.crop((left, top, left + tw, top + th))

    def _apply_overlay(self, canvas, path, w, h):
        p = Path(path)
        if not p.exists():
            return
        try:
            ov = Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS)
            base = canvas.convert("RGBA")
            base.alpha_composite(ov)
            canvas.paste(base.convert("RGB"))
        except Exception as e:
            logger.error(f"Overlay erreur: {e}")

    def _draw_decoration(self, canvas, dec: dict):
        draw = ImageDraw.Draw(canvas)
        color = tuple(dec.get("color", [0, 0, 0]))
        width = dec.get("width", 2)
        if dec.get("type") == "line":
            draw.line([(dec["x1"], dec["y1"]), (dec["x2"], dec["y2"])], fill=color, width=width)
        elif dec.get("type") == "rect":
            draw.rectangle([(dec["x"], dec["y"]), (dec["x"] + dec["w"], dec["y"] + dec["h"])], fill=color)

    def _draw_zone_text(self, canvas, zone: dict, text: str, font_path: Optional[str]):
        draw = ImageDraw.Draw(canvas)
        zx, zy, zw, zh = zone["x"], zone["y"], zone["width"], zone["height"]
        size = zone.get("size", 32)
        color = tuple(zone.get("color", [0, 0, 0]))
        font = self._load_font(font_path, size)

        # Tronquer si trop long
        display = text
        while font.getlength(display) > zw - 20 and len(display) > 3:
            display = display[:-1]

        tw = int(font.getlength(display))
        bbox = font.getbbox(display)
        th = bbox[3] - bbox[1]
        align = zone.get("align", "center")
        tx = zx + (zw - tw) // 2 if align == "center" else (zx + zw - tw - 10 if align == "right" else zx + 10)
        ty = zy + (zh - th) // 2
        draw.text((tx, ty), display, fill=color, font=font)

    def _draw_text(self, canvas, elem: dict, font_path: Optional[str]):
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(font_path, elem.get("size", 24))
        draw.text((elem.get("x", 0), elem.get("y", 0)),
                  elem.get("text", ""),
                  fill=tuple(elem.get("color", [0, 0, 0])),
                  font=font)

    def _load_font(self, font_path: Optional[str], size: int):
        if font_path and Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        for name in ("DejaVuSans.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
            for base in ("/usr/share/fonts/truetype/dejavu/",
                         "/usr/share/fonts/truetype/liberation/",
                         "C:/Windows/Fonts/"):
                p = Path(base) / name
                if p.exists():
                    try:
                        return ImageFont.truetype(str(p), size)
                    except Exception:
                        pass
        return ImageFont.load_default()

    def _compose_auto(self, photo_paths, output_path):
        n = len(photo_paths)
        if n == 0:
            raise ValueError("Aucune photo")
        w = self._config.get("processing.final_width", 1800)
        h = self._config.get("processing.final_height", 1200)
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        cell_w, cell_h, pad = w // cols, h // rows, 15
        canvas = Image.new("RGB", (w, h), (30, 30, 30))
        for i, path in enumerate(photo_paths):
            col, row = i % cols, i // cols
            try:
                photo = Image.open(path).convert("RGB")
                photo = self._fit_crop(photo, cell_w - pad * 2, cell_h - pad * 2)
                canvas.paste(photo, (col * cell_w + pad, row * cell_h + pad))
            except Exception as e:
                logger.error(f"Auto-compose {path}: {e}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, quality=self._config.get("processing.jpeg_quality", 92))
        return output_path
