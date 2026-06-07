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


class QRGenerator:

    def __init__(self, config):
        self._enabled: bool = config.get("qr.enabled", True)
        self._base_url: str = config.get("qr.base_url", "http://photobooth.local/photos")
        self._size: int = config.get("qr.size", 300)
        self._display_duration: int = config.get("qr.display_duration", 15)

    @property
    def display_duration(self) -> int:
        return self._display_duration

    def generate(self, filename: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
        """
        Génère un QR code pointant vers base_url/filename.
        Sauvegarde dans output_path si fourni.
        Retourne une PIL Image, ou None si désactivé/erreur.
        """
        if not self._enabled:
            logger.warning("QR Code desactive (qr.enabled=false dans config.yaml) — "
                           "verifier Admin > Plugins > QR Code sur resultat")
            return None
        if not _QR_AVAILABLE:
            logger.error("qrcode non installe : pip install qrcode[pil]")
            return None

        url = f"{self._base_url.rstrip('/')}/{Path(filename).name}"

        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img: Image.Image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            img = img.resize((self._size, self._size), Image.LANCZOS)

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                img.save(output_path)
                logger.info(f"QR code -> {output_path} (url={url})")

            return img
        except Exception as e:
            logger.error(f"Erreur génération QR: {e}")
            return None
