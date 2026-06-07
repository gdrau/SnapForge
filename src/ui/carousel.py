"""
Carrousel de photos sur l'écran d'accueil.
Deux modes selon l'orientation de l'écran, chargement non bloquant.

Principe de dimensionnement :
  1. Charger miniature brute
  2. La faire rentrer dans une boîte (box_w × box_h) QUELLE QUE SOIT son orientation
  3. Ajouter cadre blanc APRÈS redimensionnement
  4. Tourner l'ensemble (photo + cadre + ombre) d'un seul bloc
"""
import logging
import math
import threading
import time
from pathlib import Path
from typing import List

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

_THUMB_MAX = 280   # taille max de la miniature brute en cache

# ---------------------------------------------------------------------------
# Dispositions selon l'orientation de la ZONE
# (cx_ratio, cy_ratio, angle_deg, scale_factor)
# Angles bornés portrait ≤5°, paysage ≤8° — effet naturel non caricatural
# ---------------------------------------------------------------------------

# Paysage : ligne aérée de photos
_TABLE_L = {
    1: [(0.50, 0.50,  0.0, 1.00)],
    2: [(0.30, 0.50, -6.0, 1.00), (0.70, 0.50,  5.0, 1.00)],
    3: [(0.20, 0.50, -6.0, 0.95), (0.50, 0.50,  0.0, 1.00), (0.80, 0.50,  5.0, 0.95)],
    4: [(0.14, 0.50, -7.0, 0.93), (0.37, 0.50, -3.0, 0.97),
        (0.63, 0.50,  3.0, 0.97), (0.86, 0.50,  7.0, 0.93)],
    5: [(0.10, 0.50, -8.0, 0.90), (0.28, 0.50, -4.0, 0.96),
        (0.50, 0.50,  0.0, 1.00), (0.72, 0.50,  4.0, 0.96),
        (0.90, 0.50,  8.0, 0.90)],
    6: [(0.08, 0.50, -8.0, 0.87), (0.24, 0.50, -4.0, 0.93),
        (0.40, 0.50, -1.0, 0.98), (0.60, 0.50,  1.0, 0.98),
        (0.76, 0.50,  4.0, 0.93), (0.92, 0.50,  8.0, 0.87)],
}

# Portrait : 2 côte à côte, ou 2×2, ou 2×2+1
_TABLE_P = {
    1: [(0.50, 0.50,  0.0, 1.00)],
    2: [(0.27, 0.50, -4.0, 1.00), (0.73, 0.50,  3.0, 1.00)],
    3: [(0.24, 0.36, -4.0, 0.96), (0.76, 0.36,  3.0, 0.96),
        (0.50, 0.72, -1.0, 0.92)],
    4: [(0.24, 0.28, -4.0, 0.93), (0.76, 0.28,  3.0, 0.93),
        (0.24, 0.72, -3.0, 0.93), (0.76, 0.72,  4.0, 0.93)],
    5: [(0.24, 0.25, -4.0, 0.90), (0.76, 0.25,  3.0, 0.90),
        (0.24, 0.68, -3.0, 0.90), (0.76, 0.68,  4.0, 0.90),
        (0.50, 0.47,  0.0, 0.86)],
}


class CarouselManager:

    def __init__(self, config):
        self._config  = config
        self._source  = Path(config.get("photos.final_dir", "Photo/final"))
        self._thumbs: List["pygame.Surface"] = []
        self._lock     = threading.Lock()
        self._offset   = 0
        self._t_last   = time.monotonic()
        self._cache_items: list = []
        self._cache_key = None
        self._loading   = False

        if self.enabled:
            self._start_load()

    # --- Propriétés lues depuis config ----------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("home_carousel.enabled", True))

    @property
    def mode(self) -> str:
        return str(self._config.get("home_carousel.mode", "table"))

    @property
    def interval(self) -> float:
        return float(self._config.get("home_carousel.interval_seconds", 4))

    # --- API publique ----------------------------------------------------

    def has_photos(self) -> bool:
        with self._lock:
            return len(self._thumbs) > 0

    def refresh(self):
        if self.enabled:
            self._start_load()

    def update(self):
        if not self.enabled:
            return
        if time.monotonic() - self._t_last >= self.interval:
            self._t_last = time.monotonic()
            with self._lock:
                if len(self._thumbs) > 1:
                    self._offset = (self._offset + 1) % len(self._thumbs)
                    self._cache_items = []
                    self._cache_key   = None

    def get_render_items(self, zx: int, zy: int, zw: int, zh: int,
                         is_portrait: bool = False) -> list:
        """
        Retourne [(photo_surf, shadow_surf, abs_x, abs_y), …]
        Les surfaces sont déjà redimensionnées, bordurées et tournées.
        """
        with self._lock:
            if not self._thumbs:
                return []

            # Nombre max : portrait ≤5, paysage ≤6 (configurable via admin)
            cfg_max = int(self._config.get("home_carousel.max_photos_displayed", 6))
            max_n   = min(5 if is_portrait else 6, cfg_max)
            n       = min(max_n, len(self._thumbs))
            key = (self._offset, self.mode, n, zw, zh, is_portrait)

            if self._cache_key == key and self._cache_items:
                return [(p, s, x + zx, y + zy) for p, s, x, y in self._cache_items]

            photos = [self._thumbs[(self._offset + i) % len(self._thumbs)]
                      for i in range(n)]

            if self.mode == "simple":
                items = self._layout_simple(photos, zw, zh, is_portrait)
            else:
                items = self._layout_table(photos, zw, zh, is_portrait)

            self._cache_items = items
            self._cache_key   = key
            return [(p, s, x + zx, y + zy) for p, s, x, y in items]

    # --- Chargement background ------------------------------------------

    def _start_load(self):
        if self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        if not (_PIL_OK and _PYGAME_OK):
            self._loading = False
            return
        if not self._source.exists():
            self._loading = False
            return

        try:
            files = sorted(
                [p for p in self._source.glob("*.jpg") if p.is_file()],
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
        except Exception as e:
            logger.error(f"Carousel scan: {e}")
            self._loading = False
            return

        new_thumbs = []
        for path in files[:15]:
            try:
                img = PILImage.open(path).convert("RGB")
                img.thumbnail((_THUMB_MAX, _THUMB_MAX), PILImage.LANCZOS)
                # Miniature BRUTE sans bordure (la bordure est ajoutée à l'affichage)
                surf = pygame.image.fromstring(img.tobytes(), img.size, "RGB")
                new_thumbs.append(surf)
            except Exception as e:
                logger.debug(f"Carousel: ignore {path.name}: {e}")

        with self._lock:
            self._thumbs      = new_thumbs
            self._cache_items = []
            self._cache_key   = None

        logger.info(f"Carousel: {len(new_thumbs)} miniatures chargees")
        self._loading = False

    # --- Helpers de construction des surfaces ---------------------------

    @staticmethod
    def _fit_in_box(surf: "pygame.Surface", bw: int, bh: int,
                    scale_factor: float = 1.0) -> "pygame.Surface":
        """
        Redimensionne la photo pour tenir dans la boîte (bw × bh).
        Le ratio est conservé. Aucune déformation possible.
        """
        iw, ih = surf.get_size()
        scale  = min(bw / iw, bh / ih) * scale_factor
        tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
        return pygame.transform.smoothscale(surf, (tw, th))

    @staticmethod
    def _add_border_and_shadow(scaled: "pygame.Surface"):
        """
        Crée :
          - photo_surf : scaled + cadre blanc (SRCALPHA)
          - shadow_surf: ombre de même taille (SRCALPHA)
        La bordure est calculée APRÈS redimensionnement → toujours visible.
        """
        pw, ph  = scaled.get_size()
        border  = max(6, int(min(pw, ph) * 0.068))
        fw, fh  = pw + border * 2, ph + border * 2

        photo = pygame.Surface((fw, fh), pygame.SRCALPHA)
        photo.fill((0, 0, 0, 0))
        pygame.draw.rect(photo, (252, 252, 252, 255), (0, 0, fw, fh))
        photo.blit(scaled, (border, border))

        shadow = pygame.Surface((fw, fh), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 0))
        pygame.draw.rect(shadow, (0, 0, 0, 88), (0, 0, fw, fh))

        return photo, shadow

    # --- Layouts --------------------------------------------------------

    def _layout_simple(self, photos, zw, zh, is_portrait):
        if not photos:
            return []
        bw = (105 if is_portrait else 130)
        bh = (140 if is_portrait else 100)
        scaled = self._fit_in_box(photos[0], bw, bh)
        photo, shadow = self._add_border_and_shadow(scaled)
        fw, fh = photo.get_size()
        return [(photo, shadow, (zw - fw) // 2, (zh - fh) // 2)]

    def _layout_table(self, photos, zw, zh, is_portrait):
        """
        Boîte normalisée : photo redimensionnée pour tenir dans (box_w × box_h)
        QUELLE QUE SOIT son orientation (portrait ou paysage).
        """
        n = len(photos)
        if n == 0:
            return []

        if is_portrait:
            # BOÎTE CARRÉE : même côté S pour portrait ET paysage
            # → les photos ont la même dimension apparente quelle que soit leur orientation
            S_ratio = 0.42 if n <= 2 else (0.33 if n <= 4 else 0.26)
            S = max(75, min(int(zw * S_ratio), int(zh * 0.82)))
            box_w, box_h = S, S
            max_rot = 5.0
            table   = _TABLE_P.get(n, _TABLE_P[min(n, 3)])
        else:
            # Boîte carrée pour la zone paysage
            S_ratio = 0.22 if n <= 3 else (0.17 if n <= 5 else 0.14)
            S = max(60, min(int(zw * S_ratio), int(zh * 0.78)))
            box_w, box_h = S, S
            max_rot = 8.0
            table   = _TABLE_L.get(n, _TABLE_L[min(n, 5)])

        items = []

        for surf, (cx_r, cy_r, raw_angle, sf) in zip(photos, table):
            angle = max(-max_rot, min(max_rot, raw_angle))

            # 1. Redimensionner dans la boîte CARRÉE
            #    _fit_in_box(surf, S, S) → longue dimension = S, ratio conservé
            #    Résultat : même taille visuelle pour portrait et paysage
            scaled = self._fit_in_box(surf, box_w, box_h, sf)
            pw, ph = scaled.get_size()
            if pw < 10 or ph < 10:
                continue

            # 2. Cadre blanc + ombre
            photo_full, shadow_full = self._add_border_and_shadow(scaled)
            fw, fh = photo_full.get_size()

            # 3. Rotation LISSÉE (rotozoom = interpolation bilinéaire → pas de crénelage)
            if abs(angle) > 0.3:
                rot_photo  = pygame.transform.rotozoom(photo_full,  angle, 1.0)
                rot_shadow = pygame.transform.rotozoom(shadow_full, angle, 1.0)
            else:
                rot_photo, rot_shadow = photo_full, shadow_full
            rw, rh = rot_photo.get_size()

            # 4. Réduire si la bbox après rotation dépasse la zone
            if rw > zw or rh > zh:
                s = min(zw / rw, zh / rh) * 0.95
                rot_photo  = pygame.transform.smoothscale(rot_photo,  (int(rw*s), int(rh*s)))
                rot_shadow = pygame.transform.smoothscale(rot_shadow, (int(rw*s), int(rh*s)))
                rw, rh = rot_photo.get_size()

            # 4. Position dans la zone (centrage sur cx_r, cy_r)
            cx = int(cx_r * zw)
            cy = int(cy_r * zh)
            x  = max(0, min(cx - rw // 2, zw - rw))
            y  = max(0, min(cy - rh // 2, zh - rh))

            items.append((rot_photo, rot_shadow, x, y))

        return items
