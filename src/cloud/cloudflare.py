import logging
from typing import Optional

from .base import CloudProvider

logger = logging.getLogger(__name__)


class CloudflareProvider(CloudProvider):
    """Upload vers Cloudflare R2."""

    def __init__(self, config):
        self._account_id = config.get("cloud.cloudflare.account_id", "")
        self._api_token = config.get("cloud.cloudflare.api_token", "")
        self._bucket = config.get("cloud.cloudflare.bucket_name", "")
        self._public_url = config.get("cloud.cloudflare.public_url_base", "")

    def upload(self, local_path: str, filename: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            url = (
                f"https://api.cloudflare.com/client/v4/accounts"
                f"/{self._account_id}/r2/buckets/{self._bucket}/objects/{filename}"
            )
            with open(local_path, "rb") as f:
                resp = requests.put(
                    url,
                    headers={"Authorization": f"Bearer {self._api_token}"},
                    data=f,
                    timeout=60,
                )
            if resp.status_code in (200, 201):
                public_url = f"{self._public_url.rstrip('/')}/{filename}"
                logger.info(f"Cloudflare R2: {public_url}")
                return public_url
            logger.error(f"Cloudflare upload: {resp.status_code} {resp.text}")
            return None
        except Exception as e:
            logger.error(f"Cloudflare erreur: {e}")
            return None

    def is_available(self) -> bool:
        return bool(self._account_id and self._api_token and self._bucket)
