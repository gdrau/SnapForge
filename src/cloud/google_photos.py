import logging
import os
import pickle
from typing import Optional

from .base import CloudProvider

logger = logging.getLogger(__name__)


class GooglePhotosProvider(CloudProvider):
    """Upload vers Google Photos via OAuth2."""

    _SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]

    def __init__(self, config):
        self._credentials_file = config.get("cloud.google_photos.credentials_file", "")
        self._album_name = config.get("cloud.google_photos.album_name", "PhotoBooth")
        self._token_file = "credentials/google_token.pkl"
        self._creds = None
        self._album_id: Optional[str] = None

        if self._credentials_file and os.path.exists(self._credentials_file):
            self._auth()

    def _auth(self):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow

            if os.path.exists(self._token_file):
                with open(self._token_file, "rb") as f:
                    self._creds = pickle.load(f)

            if not self._creds or not self._creds.valid:
                if self._creds and self._creds.expired and self._creds.refresh_token:
                    self._creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self._credentials_file, self._SCOPES
                    )
                    self._creds = flow.run_local_server(port=0)
                os.makedirs(os.path.dirname(self._token_file), exist_ok=True)
                with open(self._token_file, "wb") as f:
                    pickle.dump(self._creds, f)

            logger.info("Google Photos: authentification OK")
        except ImportError:
            logger.error("google-auth non installé — pip install google-auth google-auth-oauthlib")
            self._creds = None
        except Exception as e:
            logger.error(f"Google Photos auth: {e}")
            self._creds = None

    def upload(self, local_path: str, filename: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            headers_upload = {
                "Authorization": f"Bearer {self._creds.token}",
                "Content-type": "application/octet-stream",
                "X-Goog-Upload-Protocol": "raw",
                "X-Goog-Upload-File-Name": filename,
            }
            with open(local_path, "rb") as f:
                upload_token = requests.post(
                    "https://photoslibrary.googleapis.com/v1/uploads",
                    headers=headers_upload,
                    data=f,
                    timeout=120,
                ).text

            body: dict = {
                "newMediaItems": [{"simpleMediaItem": {"uploadToken": upload_token, "fileName": filename}}]
            }
            if self._album_id:
                body["albumId"] = self._album_id

            result = requests.post(
                "https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate",
                headers={"Authorization": f"Bearer {self._creds.token}"},
                json=body,
                timeout=30,
            ).json()

            item = result.get("newMediaItemResults", [{}])[0]
            url = item.get("mediaItem", {}).get("productUrl")
            logger.info(f"Google Photos: {url}")
            return url
        except Exception as e:
            logger.error(f"Google Photos upload: {e}")
            return None

    def is_available(self) -> bool:
        return self._creds is not None
