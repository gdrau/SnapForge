import os
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "config.yaml"
EXAMPLE_CONFIG = "config.example.yaml"


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = DEFAULT_CONFIG

    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config {config_path} introuvable, utilisation du fichier exemple")
        path = Path(EXAMPLE_CONFIG)

    if not path.exists():
        raise FileNotFoundError(
            f"Aucun fichier de configuration trouvé ({config_path} ou {EXAMPLE_CONFIG})"
        )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    logger.info(f"Configuration chargée depuis {path}")
    return data or {}


class Config:
    """Accès à la configuration via notation pointée (ex: config.get('camera.fps'))."""

    def __init__(self, data: dict):
        self._data = data
        self._ensure_dirs()

    def _ensure_dirs(self):
        dirs = [
            self.get("photos.raw_dir", "Photo/raw"),
            self.get("photos.final_dir", "Photo/final"),
            "logs",
            "credentials",
        ]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)

        log_file = self.get("logging.file", "logs/photobooth.log")
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    def get(self, key_path: str, default=None):
        keys = key_path.split(".")
        val = self._data
        for key in keys:
            if isinstance(val, dict) and key in val:
                val = val[key]
            else:
                return default
        return val

    def set(self, key_path: str, value):
        """Modifie une valeur via notation pointée."""
        keys = key_path.split(".")
        d = self._data
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value

    def save(self, path: str = DEFAULT_CONFIG):
        """Sauvegarde la configuration courante en YAML."""
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f"Configuration sauvegardée : {path}")

    def __getitem__(self, key):
        return self._data[key]

    def raw(self) -> dict:
        return self._data
