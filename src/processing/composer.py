import json
import logging
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


class Template:

    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.width: int = data["width"]
        self.height: int = data["height"]
        # Support section imbriquée "background" OU clés plates (background_type, etc.)
        bg = data.get("background", {})
        bg_type_flat = data.get("background_type", "")
        self.bg_type: str = bg.get("type") or bg_type_flat or "color"
        self.bg_image_path: Optional[str] = bg.get("path")
        self.bg_image_b64: Optional[str] = bg.get("image_b64") or (
            data.get("background_image") if self.bg_type == "image" else None
        )
        grad_flat = data.get("background_gradient", {})
        self.bg_gradient: dict = bg.get("gradient", {}) or grad_flat
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

    def first_slot(self, template_name: str) -> Optional[dict]:
        """Retourne le premier slot {'x','y','width','height'} du template, ou None."""
        t = self._templates.get(template_name)
        return t.slot(0) if t else None

    def template_ar(self, template_name: str) -> Optional[float]:
        """Retourne le ratio largeur/hauteur du canvas du template, ou None."""
        t = self._templates.get(template_name)
        return (t.width / t.height) if t else None

    def compose(
        self,
        photo_paths: List[str],
        template_name: str,
        output_path: str,
        font_path: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        title_size: Optional[int] = None,
        description_size: Optional[int] = None,
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

        scale = float(self._config.get("processing.output_scale", 1.0))
        out_w = int(template.width  * scale)
        out_h = int(template.height * scale)

        # Fond
        canvas = self._make_background(template, out_w, out_h)

        # Unsharp Mask après resize (radius, percent, threshold)
        usm_radius    = float(self._config.get("processing.usm_radius",    1.0))
        usm_percent   = int(self._config.get("processing.usm_percent",   150))
        usm_threshold = int(self._config.get("processing.usm_threshold",   3))
        usm_enabled   = bool(self._config.get("processing.usm_enabled",  True))

        # Point noir : libcamera laisse des noirs délavés (voile gris ~8/255).
        # black_point remappe [bp,255]->[0,255] pour écraser les noirs = image "punchy"
        # comme le stack legacy. 0 = désactivé.
        black_point = int(self._config.get("processing.black_point", 0))
        # Correction couleur douce : compense la dominante (ex: vert/froid de libcamera)
        wb_gains = self._config.get("processing.wb_gains", None)  # [r, g, b] multiplicateurs

        # Photos — slots agrandis par scale : utilise plus de pixels sources
        for i, photo_path in enumerate(photo_paths):
            slot = template.slot(i)
            if not slot:
                continue
            try:
                sw = int(slot["width"]  * scale)
                sh = int(slot["height"] * scale)
                sx = int(slot["x"]      * scale)
                sy = int(slot["y"]      * scale)
                photo = Image.open(photo_path).convert("RGB")
                photo = self._fit_crop(photo, sw, sh)
                if usm_enabled:
                    photo = photo.filter(ImageFilter.UnsharpMask(
                        radius=usm_radius, percent=usm_percent, threshold=usm_threshold
                    ))
                photo = self._apply_tone(photo, black_point, wb_gains)
                canvas.paste(photo, (sx, sy))
            except Exception as e:
                logger.error(f"Erreur placement photo {photo_path}: {e}")

        if template.overlay_path:
            self._apply_overlay(canvas, template.overlay_path, out_w, out_h)

        for dec in template.decorations:
            self._draw_decoration(canvas, self._scale_dict(dec, scale))

        if template.title_zone and title:
            zone = dict(template.title_zone)
            if title_size is not None:
                zone["size"] = max(20, min(200, int(title_size)))
            self._draw_zone_text(canvas, self._scale_dict(zone, scale), title, font_path)

        if template.description_zone and description:
            zone = dict(template.description_zone)
            if description_size is not None:
                zone["size"] = max(12, min(150, int(description_size)))
            self._draw_zone_text(canvas, self._scale_dict(zone, scale), description, font_path)

        for elem in template.text_elements:
            try:
                self._draw_text(canvas, self._scale_dict(elem, scale), font_path)
            except Exception as e:
                logger.error(f"Erreur texte template: {e}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        quality = self._config.get("processing.jpeg_quality", 97)
        output_dpi = int(self._config.get("processing.output_dpi", 0))
        save_kwargs: dict = {"quality": quality}
        if output_dpi > 0:
            save_kwargs["dpi"] = (output_dpi, output_dpi)
        canvas.save(output_path, **save_kwargs)
        logger.info(f"Image finale -> {output_path}  ({out_w}×{out_h}px, scale={scale})")
        return output_path

    # ------------------------------------------------------------------

    # clés numériques à multiplier par le facteur d'échelle
    _SCALE_KEYS = frozenset({"x", "y", "width", "height", "size",
                              "x1", "y1", "x2", "y2", "w", "h"})

    def _scale_dict(self, d: dict, scale: float) -> dict:
        """Retourne une copie du dict avec toutes les clés de coordonnées scalées."""
        if scale == 1.0:
            return d
        result = dict(d)
        for k in self._SCALE_KEYS:
            if k in result and isinstance(result[k], (int, float)):
                result[k] = int(result[k] * scale)
        return result

    def _make_background(self, template: Template, w: int, h: int) -> Image.Image:
        """Crée le canvas de fond aux dimensions demandées."""
        if template.bg_type == "image":
            if template.bg_image_path:
                p = Path(template.bg_image_path)
                if p.exists():
                    try:
                        bg = Image.open(p).convert("RGB")
                        bg = self._fit_crop(bg, w, h)
                        logger.debug(f"Fond image fichier : {p}")
                        return bg
                    except Exception as e:
                        logger.warning(f"Fond image erreur ({p}): {e} — fallback")
                else:
                    logger.warning(f"Fond image introuvable : {p.resolve()} — fallback")
            if template.bg_image_b64:
                try:
                    import base64
                    import io as _io
                    b64_data = template.bg_image_b64
                    if b64_data.startswith("data:"):
                        b64_data = b64_data.split(",", 1)[1]
                    raw = base64.b64decode(b64_data)
                    bg = Image.open(_io.BytesIO(raw)).convert("RGB")
                    bg = self._fit_crop(bg, w, h)
                    logger.debug("Fond image base64 chargé")
                    return bg
                except Exception as e:
                    logger.warning(f"Fond image base64 erreur : {e} — fallback couleur")

        elif template.bg_type == "gradient" and template.bg_gradient:
            return self._make_gradient(template.bg_gradient, w, h, template.bg_fallback)

        return Image.new("RGB", (w, h), template.bg_fallback)

    def _make_gradient(self, gradient: dict, w: int, h: int, fallback: tuple) -> Image.Image:
        try:
            start = tuple(int(v) for v in gradient.get("start_color", list(fallback)))
            end   = tuple(int(v) for v in gradient.get("end_color",   list(fallback)))
            direction = gradient.get("direction", "vertical")
            img = Image.new("RGB", (w, h))
            if direction == "horizontal":
                # Bande de 1px de haut, étendue verticalement par resize
                strip = Image.new("RGB", (w, 1))
                for x in range(w):
                    t = x / max(w - 1, 1)
                    strip.putpixel((x, 0), tuple(int(s + (e - s) * t) for s, e in zip(start, end)))
                return strip.resize((w, h), Image.NEAREST)
            else:
                strip = Image.new("RGB", (1, h))
                for y in range(h):
                    t = y / max(h - 1, 1)
                    strip.putpixel((0, y), tuple(int(s + (e - s) * t) for s, e in zip(start, end)))
                return strip.resize((w, h), Image.NEAREST)
        except Exception as e:
            logger.warning(f"Gradient erreur : {e} — fallback couleur")
            return Image.new("RGB", (w, h), fallback)

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

    def _apply_tone(self, img: Image.Image, black_point: int, wb_gains) -> Image.Image:
        """Écrase les noirs délavés (black_point) et corrige une dominante (wb_gains).

        black_point : remappe linéairement [bp,255] -> [0,255] (bp=0 -> désactivé).
        wb_gains    : liste [r, g, b] de multiplicateurs par canal (None -> aucun).
        Déterministe : même correction pour toutes les photos (pas de surprise couleur).
        """
        if black_point and black_point > 0:
            bp = min(black_point, 64)
            scale = 255.0 / (255 - bp)
            lut = [max(0, min(255, int((v - bp) * scale))) for v in range(256)]
            img = img.point(lut * 3)
        if wb_gains and len(wb_gains) == 3:
            gr, gg, gb = (float(x) for x in wb_gains)
            lut_r = [max(0, min(255, int(v * gr))) for v in range(256)]
            lut_g = [max(0, min(255, int(v * gg))) for v in range(256)]
            lut_b = [max(0, min(255, int(v * gb))) for v in range(256)]
            img = img.point(lut_r + lut_g + lut_b)
        return img

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
        zx, zy, zw, zh = zone["x"], zone["y"], zone["width"], zone["height"]
        size = zone.get("size", 32)
        color = tuple(zone.get("color", [0, 0, 0]))
        font = self._load_font(font_path, size)
        direction = zone.get("text_direction", "horizontal")

        if direction in ("vertical-up", "vertical-down"):
            # Rendu horizontal sur surface temporaire (zh × zw), puis rotation
            display = text
            while font.getlength(display) > zh - 20 and len(display) > 3:
                display = display[:-1]
            tw = int(font.getlength(display))
            bbox = font.getbbox(display)
            th = bbox[3] - bbox[1]
            tmp = Image.new("RGBA", (zh, zw), (0, 0, 0, 0))
            ImageDraw.Draw(tmp).text(
                ((zh - tw) // 2, (zw - th) // 2),
                display, fill=color, font=font,
            )
            angle = 90 if direction == "vertical-up" else 270
            rotated = tmp.rotate(angle, expand=True)
            canvas.paste(rotated.convert("RGB"), (zx, zy), rotated.split()[3])
        else:
            draw = ImageDraw.Draw(canvas)
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
