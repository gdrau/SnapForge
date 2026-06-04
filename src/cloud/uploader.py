import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from .base import CloudProvider

logger = logging.getLogger(__name__)


def _create_provider(config) -> Optional[CloudProvider]:
    if not config.get("cloud.enabled", False):
        return None
    name = config.get("cloud.provider", "local")
    if name == "local":
        from .local import LocalProvider
        return LocalProvider(config)
    if name == "google_photos":
        from .google_photos import GooglePhotosProvider
        return GooglePhotosProvider(config)
    if name == "cloudflare":
        from .cloudflare import CloudflareProvider
        return CloudflareProvider(config)
    if name == "s3":
        from .s3 import S3Provider
        return S3Provider(config)
    logger.warning(f"Provider cloud inconnu '{name}', fallback local")
    from .local import LocalProvider
    return LocalProvider(config)


class UploadManager:
    """
    Gère les uploads avec file d'attente persistante.
    En cas d'échec réseau, la photo est mise en queue et réessayée toutes les 60s.
    """

    def __init__(self, config):
        self._enabled = config.get("cloud.enabled", False)
        self._retry = config.get("cloud.retry_on_failure", True)
        self._queue_file = Path(config.get("cloud.retry_queue_file", "photos/upload_queue.json"))
        self._provider = _create_provider(config)
        self._queue: list[dict] = []
        self._lock = threading.Lock()

        if self._retry and self._enabled:
            self._load_queue()
            threading.Thread(target=self._retry_loop, daemon=True).start()

    def _load_queue(self):
        if not self._queue_file.exists():
            return
        try:
            with open(self._queue_file) as f:
                self._queue = json.load(f)
            if self._queue:
                logger.info(f"File d'attente upload : {len(self._queue)} photos en attente")
        except Exception as e:
            logger.error(f"Erreur lecture queue: {e}")

    def _save_queue(self):
        try:
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._queue_file, "w") as f:
                json.dump(self._queue, f)
        except Exception as e:
            logger.error(f"Erreur sauvegarde queue: {e}")

    def upload(self, local_path: str, filename: str) -> Optional[str]:
        """Upload synchrone. Met en queue si échec."""
        if not self._enabled or not self._provider:
            return None

        url = self._provider.upload(local_path, filename)
        if url is None and self._retry:
            with self._lock:
                self._queue.append({"path": local_path, "filename": filename})
                self._save_queue()
            logger.info(f"Upload en attente : {filename}")
        return url

    def _retry_loop(self):
        while True:
            time.sleep(60)
            with self._lock:
                if not self._queue or not self._provider:
                    continue
                if not self._provider.is_available():
                    continue
                remaining = []
                for item in self._queue:
                    url = self._provider.upload(item["path"], item["filename"])
                    if url is None:
                        remaining.append(item)
                    else:
                        logger.info(f"Retry upload réussi : {item['filename']}")
                self._queue = remaining
                self._save_queue()

    @property
    def enabled(self) -> bool:
        return self._enabled
