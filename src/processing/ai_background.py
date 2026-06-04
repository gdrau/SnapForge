import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


class AIBackgroundProcessor:
    """
    Remplacement de fond optionnel après capture.

    Providers supportés :
    - rembg       : local, U2Net, meilleure qualité, ~3-8s sur Pi 4 CPU
    - mediapipe   : local, TFLite, très rapide (<1s), précision moindre
    - removebg_api: cloud, qualité maximale, nécessite clé API
    """

    def __init__(self, config):
        self._config = config
        self._enabled: bool = config.get("ai.enabled", False)
        self._provider: str = config.get("ai.provider", "rembg")
        self._bg_path: Optional[str] = config.get("ai.background_path")
        self._apply_on: str = config.get("ai.apply_on", "raw_photo")
        self._session = None
        self._mp_seg = None

        if self._enabled:
            self._init_provider()

    def _init_provider(self):
        if self._provider == "rembg":
            try:
                from rembg import new_session
                self._session = new_session("u2net")
                logger.info("rembg initialisé (u2net)")
            except ImportError:
                logger.error("rembg non installé — pip install rembg onnxruntime")
                self._enabled = False
            except Exception as e:
                logger.error(f"Erreur init rembg: {e}")
                self._enabled = False

        elif self._provider == "mediapipe":
            try:
                import mediapipe as mp
                self._mp_seg = mp.solutions.selfie_segmentation
                logger.info("MediaPipe selfie segmentation initialisé")
            except ImportError:
                logger.error("mediapipe non installé — pip install mediapipe")
                self._enabled = False

        elif self._provider == "removebg_api":
            if not self._config.get("ai.removebg_api_key", ""):
                logger.error("removebg_api sélectionné mais ai.removebg_api_key est vide")
                self._enabled = False

        else:
            logger.error(f"Provider IA inconnu : {self._provider}")
            self._enabled = False

    # ------------------------------------------------------------------

    @property
    def should_apply(self) -> bool:
        return self._enabled

    @property
    def apply_on(self) -> str:
        return self._apply_on

    def process(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Détourage + remplacement de fond.
        Retourne output_path si succès, input_path inchangé si erreur.
        """
        if not self._enabled:
            return input_path

        if output_path is None:
            p = Path(input_path)
            output_path = str(p.parent / f"{p.stem}_ai{p.suffix}")

        try:
            logger.info(f"Traitement IA ({self._provider}) : {input_path}")
            if self._provider == "rembg":
                foreground = self._rembg(input_path)
            elif self._provider == "mediapipe":
                foreground = self._mediapipe(input_path)
            elif self._provider == "removebg_api":
                foreground = self._removebg_api(input_path)
            else:
                return input_path

            if self._bg_path and Path(self._bg_path).exists():
                result = self._replace_background(foreground, self._bg_path)
            else:
                # Fond blanc si aucun fichier de fond configuré
                bg = Image.new("RGBA", foreground.size, (255, 255, 255, 255))
                result = Image.alpha_composite(bg, foreground).convert("RGB")

            result.save(output_path)
            logger.info(f"IA terminée -> {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Échec traitement IA pour {input_path}: {e}")
            return input_path

    def _rembg(self, path: str) -> Image.Image:
        from rembg import remove
        with open(path, "rb") as f:
            data = f.read()
        result = remove(data, session=self._session)
        return Image.open(io.BytesIO(result)).convert("RGBA")

    def _mediapipe(self, path: str) -> Image.Image:
        import numpy as np
        import mediapipe as mp
        img = Image.open(path).convert("RGB")
        arr = np.array(img)
        with self._mp_seg.SelfieSegmentation(model_selection=1) as seg:
            mask = seg.process(arr).segmentation_mask > 0.5
        rgba = np.zeros((*arr.shape[:2], 4), dtype=np.uint8)
        rgba[:, :, :3] = arr
        rgba[:, :, 3] = (mask * 255).astype(np.uint8)
        return Image.fromarray(rgba, "RGBA")

    def _removebg_api(self, path: str) -> Image.Image:
        import requests
        api_key = self._config.get("ai.removebg_api_key", "")
        with open(path, "rb") as f:
            resp = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                files={"image_file": f},
                data={"size": "auto"},
                headers={"X-Api-Key": api_key},
                timeout=30,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"remove.bg API: {resp.status_code} - {resp.text}")
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")

    def _replace_background(self, fg: Image.Image, bg_path: str) -> Image.Image:
        bg = Image.open(bg_path).convert("RGBA").resize(fg.size, Image.LANCZOS)
        return Image.alpha_composite(bg, fg).convert("RGB")
