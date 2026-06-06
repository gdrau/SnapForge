"""
Génération du fond graphique par défaut pour les templates photo.
Fond élégant blanc cassé avec formes géométriques discrètes.
"""
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# Palette pastel événement (mariage, anniversaire, soirée)
_PASTEL_COLORS = [
    (255, 220, 180),  # abricot
    (200, 220, 255),  # bleu ciel
    (200, 240, 210),  # vert menthe
    (255, 200, 220),  # rose pâle
    (240, 220, 255),  # lavande
    (255, 240, 190),  # jaune crème
    (210, 235, 255),  # bleu glacier
    (255, 215, 200),  # pêche
]

# Formes fixes (seed stable, ne pas utiliser random)
_SHAPES = [
    # (type, x_pct, y_pct, size_pct, color_idx, opacity)
    ("rect",  0.08, 0.06, 0.025, 0, 60),
    ("rect",  0.92, 0.04, 0.018, 1, 50),
    ("rect",  0.05, 0.94, 0.022, 2, 55),
    ("rect",  0.95, 0.92, 0.020, 3, 50),
    ("rect",  0.50, 0.02, 0.015, 4, 45),
    ("rect",  0.12, 0.50, 0.012, 5, 40),
    ("rect",  0.88, 0.50, 0.014, 6, 45),
    ("rect",  0.30, 0.97, 0.018, 7, 50),
    ("rect",  0.70, 0.97, 0.016, 0, 45),
    ("rect",  0.25, 0.03, 0.013, 1, 40),
    ("rect",  0.75, 0.03, 0.015, 2, 40),
    ("rect",  0.02, 0.25, 0.012, 3, 35),
    ("rect",  0.98, 0.75, 0.013, 4, 35),
    # Petits carrés décoratifs
    ("dot",  0.15, 0.15, 0.008, 0, 70),
    ("dot",  0.85, 0.85, 0.008, 1, 70),
    ("dot",  0.85, 0.15, 0.006, 2, 65),
    ("dot",  0.15, 0.85, 0.006, 3, 65),
    ("dot",  0.50, 0.50, 0.005, 4, 30),
    ("dot",  0.35, 0.08, 0.005, 5, 55),
    ("dot",  0.65, 0.92, 0.005, 6, 55),
]


def generate_default_background(width: int, height: int, output_path: str) -> bool:
    """Génère le fond graphique par défaut pour les templates."""
    if not _PIL_OK:
        return False

    try:
        # Base blanc cassé chaud
        bg = Image.new("RGBA", (width, height), (250, 250, 248, 255))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for shape_type, xp, yp, sp, cidx, alpha in _SHAPES:
            cx = int(xp * width)
            cy = int(yp * height)
            s = int(sp * min(width, height))
            r, g, b = _PASTEL_COLORS[cidx % len(_PASTEL_COLORS)]
            color = (r, g, b, alpha)

            if shape_type == "rect":
                draw.rectangle([cx - s, cy - s, cx + s, cy + s], fill=color)
            elif shape_type == "dot":
                draw.ellipse([cx - s, cy - s, cx + s, cy + s], fill=color)

        # Fusionner
        result = Image.alpha_composite(bg, overlay).convert("RGB")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path, quality=95)
        logger.info(f"Fond par defaut genere : {output_path}")
        return True

    except Exception as e:
        logger.error(f"Erreur generation fond : {e}")
        return False


def ensure_default_background(path: str = "assets/backgrounds/default_bg.jpg",
                               width: int = 1181, height: int = 1772) -> bool:
    """Génère le fond s'il n'existe pas encore."""
    p = Path(path)
    if p.exists():
        return True
    return generate_default_background(width, height, path)
