"""
Génération de GIF animés depuis une liste de frames capturées.
Optimisé pour Raspberry Pi (conversion palette, resize, optimize).
"""
import logging
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False
    logger.error("Pillow non installé — gif_maker indisponible")

try:
    from PIL import Image as _PilImage
    _RESAMPLE = _PilImage.Resampling.LANCZOS
except AttributeError:
    try:
        from PIL import Image as _PilImage
        _RESAMPLE = _PilImage.LANCZOS  # type: ignore
    except Exception:
        _RESAMPLE = None


class GifMaker:
    """Génère un GIF animé depuis des frames JPEG et une miniature JPEG."""

    def __init__(self, config):
        self._config       = config
        self._frame_dur    = config.get("gif.frame_duration_ms", 180)
        self._loop         = config.get("gif.loop", 0)
        self._resize_w     = config.get("gif.resize_width", 720)
        self._output_dir   = Path(config.get("gif.output_dir",      "Photo/gifs"))
        self._thumb_dir    = Path(config.get("gif.thumbnails_dir",  "Photo/thumbnails"))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._thumb_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("gif.enabled", True) and _PIL_OK)

    def make_gif(self, frame_paths: List[str], output_path: str) -> Optional[str]:
        """
        Génère le GIF depuis les frames capturées.
        Retourne le chemin du GIF ou None en cas d'erreur.
        """
        if not _PIL_OK:
            logger.error("Pillow manquant — impossible de générer le GIF")
            return None
        if not frame_paths:
            logger.error("Aucune frame pour le GIF")
            return None

        t0 = time.monotonic()
        try:
            frames_pil = []
            for path in frame_paths:
                img = Image.open(path).convert("RGB")
                # Redimensionner en conservant le ratio
                if self._resize_w and img.width > self._resize_w:
                    ratio = self._resize_w / img.width
                    new_h = int(img.height * ratio)
                    img = img.resize((self._resize_w, new_h), _RESAMPLE)
                # Convertir en palette 256 couleurs pour réduire le poids
                img_p = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                frames_pil.append(img_p)

            if not frames_pil:
                return None

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            frames_pil[0].save(
                output_path,
                format="GIF",
                save_all=True,
                append_images=frames_pil[1:],
                duration=self._frame_dur,
                loop=self._loop,
                optimize=True,
            )

            size_kb = Path(output_path).stat().st_size // 1024
            elapsed = round(time.monotonic() - t0, 1)
            logger.info(f"GIF généré : {output_path} ({size_kb} Ko, {elapsed}s)")
            return output_path

        except Exception as e:
            logger.error(f"Erreur génération GIF ({type(e).__name__}): {e}")
            return None

    def make_thumbnail(self, gif_path: str, thumb_path: str, size: int = 300) -> Optional[str]:
        """
        Crée une miniature JPEG depuis la première frame du GIF.
        Utilisée par le carrousel de l'écran d'accueil.
        """
        if not _PIL_OK:
            return None
        try:
            img = Image.open(gif_path)
            img.seek(0)                   # première frame
            img = img.convert("RGB")
            img.thumbnail((size, size), _RESAMPLE)
            Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)
            img.save(thumb_path, "JPEG", quality=85)
            logger.info(f"Miniature GIF : {thumb_path}")
            return thumb_path
        except Exception as e:
            logger.error(f"Erreur miniature GIF : {e}")
            return None

    def gif_path_for(self, timestamp: str, number: int) -> str:
        return str(self._output_dir / f"gif_{number:04d}_{timestamp}.gif")

    def thumb_path_for(self, timestamp: str, number: int) -> str:
        return str(self._thumb_dir / f"gif_{number:04d}_{timestamp}.jpg")
