"""
Carrousel de photos sur l'écran d'accueil.
Chargement en arrière-plan (non bloquant), deux modes d'affichage.
"""
import logging
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pygame
    _PYGAME_OK = True
except ImportError:
    _PYGAME_OK = False

try:
    from PIL import Image as PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

BORDER = 5          # bordure blanche "effet photo imprimée"
SHADOW  = 4         # décalage de l'ombre portée

# Disposition "table" selon le nombre de photos visibles
# (cx_ratio, cy_ratio, angle_deg, scale_factor)
# cx/cy = position du centre de la photo dans la zone (0-1)
_TABLE = {
    1: [(0.50, 0.50,  0.0, 1.00)],
    2: [(0.28, 0.50, -8.0, 0.96), (0.72, 0.50,  7.0, 0.96)],
    3: [(0.20, 0.52,-10.0, 0.90), (0.50, 0.48,  0.0, 1.00), (0.80, 0.52,  9.0, 0.90)],
    4: [(0.18, 0.52,-11.0, 0.88), (0.40, 0.48, -4.0, 0.95),
        (0.62, 0.52,  5.0, 0.95), (0.84, 0.48,  9.0, 0.88)],
    5: [(0.13, 0.52,-13.0, 0.85), (0.31, 0.48, -6.0, 0.92),
        (0.52, 0.52,  0.0, 1.00), (0.71, 0.48,  5.0, 0.92),
        (0.89, 0.52, 11.0, 0.85)],
}


class CarouselManager:
    """
    Gère le carrousel de photos de l'écran d'accueil.

    Thread-safe : chargement en background, rendu depuis le thread principal.
    Les miniatures sont préchargées avec bordure blanche (effet tirage photo).
    """

    _THUMB_MAX = 280  # taille max d'une miniature en cache (px)

    def __init__(self, config):
        self._config = config
        self._source_dir = Path(config.get("photos.final_dir", "Photo/final"))

        self._thumbs: List["pygame.Surface"] = []
        self._lock = threading.Lock()
        self._offset = 0                  # index de départ dans la liste
        self._last_advance = time.monotonic()
        self._cache_items: list = []      # items pré-calculés pour le rendu
        self._cache_key = None            # clé de cache (offset, mode, n, zw, zh)
        self._loading = False

        if self.enabled:
            self._start_load()

    # ------------------------------------------------------------------
    # Propriétés lues directement depuis config (toujours à jour)
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("home_carousel.enabled", True))

    @property
    def mode(self) -> str:
        return str(self._config.get("home_carousel.mode", "table"))

    @property
    def interval(self) -> float:
        return float(self._config.get("home_carousel.interval_seconds", 4))

    @property
    def max_n(self) -> int:
        return int(self._config.get("home_carousel.max_photos_displayed", 5))

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def has_photos(self) -> bool:
        with self._lock:
            return len(self._thumbs) > 0

    def refresh(self):
        """Appelé après chaque session ou activation du carrousel."""
        if self.enabled:
            self._start_load()

    def update(self):
        """Avance le carrousel si l'intervalle est écoulé (appeler chaque frame)."""
        if not self.enabled:
            return
        now = time.monotonic()
        if now - self._last_advance >= self.interval:
            self._last_advance = now
            with self._lock:
                if len(self._thumbs) > 1:
                    self._offset = (self._offset + 1) % len(self._thumbs)
                    self._cache_items = []
                    self._cache_key   = None

    def get_render_items(self, zx: int, zy: int, zw: int, zh: int) -> list:
        """
        Retourne [(surface, abs_x, abs_y)] prêts à blitter.
        Utilise un cache : recalcul uniquement si offset/taille change.
        """
        with self._lock:
            if not self._thumbs:
                return []

            n   = min(self.max_n, len(self._thumbs))
            key = (self._offset, self.mode, n, zw, zh)

            if self._cache_key == key and self._cache_items:
                return [(s, x + zx, y + zy) for s, x, y in self._cache_items]

            photos = [self._thumbs[(self._offset + i) % len(self._thumbs)]
                      for i in range(n)]

            if self.mode == "simple":
                items = self._layout_simple(photos, zw, zh)
            else:
                items = self._layout_table(photos, zw, zh)

            self._cache_items = items
            self._cache_key   = key
            return [(s, x + zx, y + zy) for s, x, y in items]

    # ------------------------------------------------------------------
    # Chargement en arrière-plan
    # ------------------------------------------------------------------

    def _start_load(self):
        if self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        if not (_PIL_OK and _PYGAME_OK):
            self._loading = False
            return
        if not self._source_dir.exists():
            self._loading = False
            return

        try:
            files = sorted(
                [p for p in self._source_dir.glob("*.jpg") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception as e:
            logger.error(f"Carousel scan: {e}")
            self._loading = False
            return

        new_thumbs = []
        for path in files[:15]:    # max 15 photos en mémoire
            try:
                img = PILImage.open(path).convert("RGB")
                img.thumbnail((self._THUMB_MAX, self._THUMB_MAX), PILImage.LANCZOS)
                # Bordure blanche — effet tirage photo
                bordered = PILImage.new(
                    "RGB",
                    (img.width + BORDER * 2, img.height + BORDER * 2),
                    (252, 252, 252),
                )
                bordered.paste(img, (BORDER, BORDER))
                surf = pygame.image.fromstring(bordered.tobytes(), bordered.size, "RGB")
                new_thumbs.append(surf)
            except Exception as e:
                logger.debug(f"Carousel: ignore {path.name}: {e}")

        with self._lock:
            self._thumbs      = new_thumbs
            self._cache_items = []
            self._cache_key   = None

        logger.info(f"Carousel: {len(new_thumbs)} miniatures chargees depuis {self._source_dir}")
        self._loading = False

    # ------------------------------------------------------------------
    # Layouts
    # ------------------------------------------------------------------

    def _layout_simple(self, photos: list, zw: int, zh: int) -> list:
        """Une photo centrée dans la zone."""
        if not photos:
            return []
        surf = photos[0]
        iw, ih = surf.get_size()
        scale = min((zw - 10) / iw, (zh - 10) / ih, 1.0)
        if scale < 0.99:
            nw, nh = int(iw * scale), int(ih * scale)
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        else:
            nw, nh = iw, ih
        return [(surf, (zw - nw) // 2, (zh - nh) // 2)]

    def _layout_table(self, photos: list, zw: int, zh: int) -> list:
        """Photos dispersées comme sur une table, avec légères rotations."""
        n = len(photos)
        if n == 0:
            return []

        # Taille de base adaptée à la zone
        if zw > zh:          # zone paysage
            base = int(zh * 0.68)
        else:                # zone portrait
            base = int(min(zw, zh) * 0.44)

        layout = _TABLE.get(n, _TABLE[min(n, 5)])
        items  = []

        for surf, (cx_r, cy_r, angle, sf) in zip(photos, layout):
            iw, ih = surf.get_size()
            tw = int(base * sf)
            th = int(tw * ih / iw)

            # Clamp pour ne pas dépasser les bords
            if tw > zw * 0.72:
                tw = int(zw * 0.72); th = int(tw * ih / iw)
            if th > zh * 0.92:
                th = int(zh * 0.92); tw = int(th * iw / ih)
            if tw < 20 or th < 20:
                continue

            scaled  = pygame.transform.smoothscale(surf, (tw, th))
            rotated = pygame.transform.rotate(scaled, angle)
            rw, rh  = rotated.get_size()

            # Centre cible dans la zone
            cx = int(cx_r * zw)
            cy = int(cy_r * zh)
            x  = max(0, min(cx - rw // 2, zw - rw))
            y  = max(0, min(cy - rh // 2, zh - rh))

            items.append((rotated, x, y))

        return items
