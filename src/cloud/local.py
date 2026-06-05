import logging
import shutil
from pathlib import Path
from typing import Optional

from .base import CloudProvider

logger = logging.getLogger(__name__)


class LocalProvider(CloudProvider):
    """Copie locale des photos finales (provider par défaut)."""

    def __init__(self, config):
        self._output_dir = Path(config.get("cloud.local.output_dir", "Photo/exported"))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = config.get("qr.base_url", "http://photobooth.local/photos")

    def upload(self, local_path: str, filename: str) -> Optional[str]:
        try:
            dest = self._output_dir / filename
            shutil.copy2(local_path, dest)
            url = f"{self._base_url.rstrip('/')}/{filename}"
            logger.info(f"Copie locale : {dest}")
            return url
        except Exception as e:
            logger.error(f"Erreur copie locale: {e}")
            return None

    def is_available(self) -> bool:
        return self._output_dir.exists()
