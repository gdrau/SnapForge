import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import qrcode
    _QR_AVAILABLE = True
except ImportError:
    _QR_AVAILABLE = False
    logger.warning("qrcode non installé — pip install qrcode[pil]")

# Compatibilité Pillow 9.x, 10.x, 11.x
try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    _RESAMPLE = Image.LANCZOS   # type: ignore[attr-defined]


def _to_pil_rgb(qr_img) -> Optional[Image.Image]:
    """Convertit le résultat de qrcode.make_image() en PIL Image RGB."""
    if hasattr(qr_img, 'convert'):
        try:
            return qr_img.convert("RGB")
        except Exception as e:
            logger.debug(f"convert() échoué : {e}")
    if hasattr(qr_img, 'get_image'):
        try:
            return qr_img.get_image().convert("RGB")
        except Exception as e:
            logger.debug(f"get_image() échoué : {e}")
    try:
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    except Exception as e:
        logger.debug(f"save/PNG échoué : {e}")
    return None


class QRGenerator:

    def __init__(self, config):
        self._enabled          = config.get("qr.enabled", True)
        self._base_url: str    = config.get("qr.base_url", "http://photobooth.local/photos")
        self._size: int        = config.get("qr.size", 300)
        self._display_duration = config.get("qr.display_duration", 15)

    @property
    def display_duration(self) -> int:
        return self._display_duration

    def generate(self, filename: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """Génère un QR code → URL = base_url + nom_fichier (serveur local)."""
        url = f"{self._base_url.rstrip('/')}/{Path(filename).name}"
        return self._build(url, output_path)

    def generate_from_url(self, url: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """
        Génère un QR code depuis une URL directe.
        À utiliser quand on dispose de l'URL réelle retournée par le cloud
        (Google Photos, Cloudflare R2, etc.).
        """
        return self._build(url, output_path)

    def _build(self, url: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """Logique commune de génération QR."""
        if not self._enabled:
            logger.warning("QR désactivé (qr.enabled=false)")
            return None
        if not _QR_AVAILABLE:
            logger.error("qrcode non installé : pip install qrcode[pil]")
            return None

        logger.info(f"Génération QR : {url}")
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            raw = qr.make_image(fill_color="black", back_color="white")
        except Exception as exc:
            logger.error(f"Erreur make_image ({type(exc).__name__}): {exc}")
            return None

        pil_img = _to_pil_rgb(raw)
        if pil_img is None:
            logger.error(f"Impossible de convertir le QR en image PIL (type={type(raw)})")
            return None

        try:
            pil_img = pil_img.resize((self._size, self._size), _RESAMPLE)
        except Exception as exc:
            logger.error(f"Erreur resize : {exc}")
            return None

        if output_path:
            try:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                pil_img.save(output_path)
                logger.info(f"QR sauvegardé : {output_path}")
            except Exception as exc:
                logger.warning(f"Impossible de sauvegarder QR : {exc}")

        logger.info(f"QR généré ({self._size}×{self._size}px) → {url}")
        return pil_img
