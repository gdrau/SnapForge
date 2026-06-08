import logging
from pathlib import Path
from typing import Optional

from .base import CloudProvider

logger = logging.getLogger(__name__)

# Content-Type par extension pour que le navigateur affiche directement les images
_CONTENT_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


class CloudflareProvider(CloudProvider):
    """Upload vers Cloudflare R2 via l'API REST Cloudflare v4."""

    def __init__(self, config):
        self._account_id = config.get("cloud.cloudflare.account_id", "")
        self._api_token  = config.get("cloud.cloudflare.api_token", "")
        self._bucket     = config.get("cloud.cloudflare.bucket_name", "")
        self._public_url = config.get("cloud.cloudflare.public_url_base", "").rstrip("/")

    def upload(self, local_path: str, filename: str) -> Optional[str]:
        if not self.is_available():
            logger.error("Cloudflare R2 non configuré (account_id, api_token ou bucket_name manquant)")
            return None
        try:
            import requests

            endpoint = (
                f"https://api.cloudflare.com/client/v4/accounts"
                f"/{self._account_id}/r2/buckets/{self._bucket}/objects/{filename}"
            )
            # Content-Type correct → le navigateur affiche la photo directement
            ext = Path(filename).suffix.lower()
            content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

            with open(local_path, "rb") as f:
                resp = requests.put(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Content-Type":  content_type,
                    },
                    data=f,
                    timeout=60,
                )

            if resp.status_code in (200, 201):
                public_url = f"{self._public_url}/{filename}"
                logger.info(f"Cloudflare R2 upload OK : {public_url}")
                return public_url

            logger.error(
                f"Cloudflare R2 erreur {resp.status_code} : {resp.text[:300]}\n"
                f"Vérifier : account_id, api_token (permission R2 Edit), bucket_name"
            )
            return None

        except Exception as e:
            logger.error(f"Cloudflare R2 exception : {e}")
            return None

    def is_available(self) -> bool:
        return bool(self._account_id and self._api_token and self._bucket and self._public_url)
