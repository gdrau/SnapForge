import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class CupsPrinter:
    """Impression via CUPS (commande lp)."""

    def __init__(self, config):
        self._config_enabled: bool = config.get("printing.enabled", False)
        self._printer_name: str = config.get("printing.printer_name", "")
        self._copies: int = config.get("printing.copies", 1)
        self._dpi: int = config.get("printing.dpi", 300)

    @property
    def enabled(self) -> bool:
        return self._config_enabled and shutil.which("lp") is not None

    def get_printers(self) -> List[str]:
        try:
            result = subprocess.run(
                ["lpstat", "-a"], capture_output=True, text=True, timeout=5
            )
            return [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
        except Exception as e:
            logger.error(f"Erreur liste imprimantes: {e}")
            return []

    def print_photo(self, photo_path: str) -> bool:
        if not self.enabled:
            logger.warning("Impression désactivée ou commande 'lp' introuvable")
            return False

        if not Path(photo_path).exists():
            logger.error(f"Photo introuvable : {photo_path}")
            return False

        cmd = ["lp", "-n", str(self._copies)]
        if self._printer_name:
            cmd.extend(["-d", self._printer_name])
        cmd.extend(
            ["-o", "media=photo", "-o", f"Resolution={self._dpi}dpi", "-o", "fit-to-page", photo_path]
        )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"Impression lancée : {photo_path}")
                return True
            logger.error(f"Erreur impression : {result.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout impression")
            return False
        except Exception as e:
            logger.error(f"Erreur impression: {e}")
            return False
