import json
import logging
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class Template:
    """Définit la mise en page d'une composition finale."""

    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.width: int = data["width"]
        self.height: int = data["height"]
        self.background_color: tuple = tuple(data.get("background_color", [255, 255, 255]))
        self.slots: list = data["slots"]
        self.overlay_path: Optional[str] = data.get("overlay_path")
        self.text_elements: list = data.get("text_elements", [])

    @classmethod
    def from_file(cls, path: str) -> "Template":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def slot(self, index: int) -> Optional[dict]:
        return self.slots[index] if index < len(self.slots) else None


class Composer:
    """Assemble des photos brutes en une image finale via un template."""

    def __init__(self, config):
        self._config = config
        self._templates_dir = Path(config.get("templates.templates_dir", "templates"))
        self._templates: dict[str, Template] = {}
        self._load_all()

    def _load_all(self):
        if not self._templates_dir.exists():
            logger.warning(f"Dossier templates introuvable : {self._templates_dir}")
            return
        for path in sorted(self._templates_dir.glob("*.json")):
            try:
                t = Template.from_file(str(path))
                self._templates[path.stem] = t
                logger.info(f"Template chargé : {path.stem}")
            except Exception as e:
                logger.error(f"Erreur chargement template {path}: {e}")

    def available(self) -> List[str]:
        return list(self._templates.keys())

    def compose(
        self,
        photo_paths: List[str],
        template_name: str,
        output_path: str,
        font_path: Optional[str] = None,
    ) -> str:
        template = self._templates.get(template_name)
        if not template:
            logger.warning(f"Template '{template_name}' introuvable, composition automatique")
            return self._compose_auto(photo_paths, output_path)

        canvas = Image.new("RGB", (template.width, template.height), template.background_color)

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

    def _fit_crop(self, img: Image.Image, tw: int, th: int) -> Image.Image:
        """Redimensionne et recadre au centre pour remplir exactement tw×th."""
        src_r = img.width / img.height
        dst_r = tw / th
        if src_r > dst_r:
            new_h = th
            new_w = int(new_h * src_r)
        else:
            new_w = tw
            new_h = int(new_w / src_r)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - tw) // 2
        top = (new_h - th) // 2
        return img.crop((left, top, left + tw, top + th))

    def _apply_overlay(self, canvas: Image.Image, overlay_path: str, w: int, h: int):
        p = Path(overlay_path)
        if not p.exists():
            return
        try:
            overlay = Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS)
            base = canvas.convert("RGBA")
            base.alpha_composite(overlay)
            canvas.paste(base.convert("RGB"))
        except Exception as e:
            logger.error(f"Erreur overlay: {e}")

    def _draw_text(self, canvas: Image.Image, elem: dict, font_path: Optional[str]):
        draw = ImageDraw.Draw(canvas)
        text = elem.get("text", "")
        x, y = elem.get("x", 0), elem.get("y", 0)
        size = elem.get("size", 24)
        color = tuple(elem.get("color", [0, 0, 0]))
        font = None
        if font_path and Path(font_path).exists():
            try:
                font = ImageFont.truetype(font_path, size)
            except Exception:
                pass
        draw.text((x, y), text, fill=color, font=font or ImageFont.load_default())

    def _compose_auto(self, photo_paths: List[str], output_path: str) -> str:
        """Mise en page automatique si aucun template ne correspond."""
        n = len(photo_paths)
        if n == 0:
            raise ValueError("Aucune photo à composer")
        w = self._config.get("processing.final_width", 1800)
        h = self._config.get("processing.final_height", 1200)
        cols = 2 if n > 1 else 1
        rows = (n + cols - 1) // cols
        cell_w, cell_h = w // cols, h // rows
        pad = 15
        canvas = Image.new("RGB", (w, h), (30, 30, 30))
        for i, path in enumerate(photo_paths):
            col, row = i % cols, i // cols
            try:
                photo = Image.open(path).convert("RGB")
                photo = self._fit_crop(photo, cell_w - pad * 2, cell_h - pad * 2)
                canvas.paste(photo, (col * cell_w + pad, row * cell_h + pad))
            except Exception as e:
                logger.error(f"Auto-compose erreur {path}: {e}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, quality=self._config.get("processing.jpeg_quality", 92))
        return output_path
