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

# Compatibilité Pillow 9.x et 10.x+
try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    _RESAMPLE = Image.LANCZOS   # type: ignore[attr-defined]


class QRGenerator:

    def __init__(self, config):
        self._enabled           = config.get("qr.enabled", True)
        self._base_url: str     = config.get("qr.base_url", "http://photobooth.local/photos")
        self._size: int         = config.get("qr.size", 300)
        self._display_duration  = config.get("qr.display_duration", 15)

    @property
    def display_duration(self) -> int:
        return self._display_duration

    def generate(self, filename: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """
        Génère le QR code et le sauvegarde dans output_path.
        Retourne l'image PIL, ou None avec un log d'erreur précis.
        """
        if not self._enabled:
            logger.warning("QR desactive : qr.enabled=false dans config.yaml — "
                           "allez dans Admin > Plugins > QR Code sur resultat > ACTIVE")
            return None

        if not _QR_AVAILABLE:
            logger.error("qrcode non installe : pip install qrcode[pil]")
            return None

        url = f"{self._base_url.rstrip('/')}/{Path(filename).name}"
        logger.info(f"Generation QR pour : {url}")

        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)

            # make_image retourne un objet propriétaire, convert() le ramène en PIL Image
            pil_img = qr.make_image(fill_color="black", back_color="white")
            pil_img = pil_img.convert("RGB")
            pil_img = pil_img.resize((self._size, self._size), _RESAMPLE)

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                pil_img.save(output_path)
                logger.info(f"QR sauvegarde : {output_path}")

            logger.info(f"QR genere avec succes ({self._size}x{self._size}px)")
            return pil_img

        except Exception as exc:
            logger.error(f"ERREUR generation QR ({type(exc).__name__}): {exc}")
            return None
