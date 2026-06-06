"""
Carrousel de photos sur l'écran d'accueil.
Chargement en arrière-plan (non bloquant), deux modes d'affichage.

Workflow photo :
  1. Charger miniature brute (sans bordure)
  2. Réduire à la taille d'affichage
  3. Ajouter la bordure blanche APRÈS redimensionnement (toujours visible)
  4. Tourner le tout (photo + bordure + ombre) d'un seul bloc
"""
import logging
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

# Disposition "table" : (cx_ratio, cy_ratio, angle_deg, scale_factor)
# Angles bornés à ±10° pour un effet naturel non caricatural
_TABLE = {
    1: [(0.50, 0.50,  0.0, 1.00)],
    2: [(0.28, 0.50, -8.0, 0.96), (0.72, 0.50,  7.0, 0.96)],
    3: [(0.20, 0.52, -9.0, 0.90), (0.50, 0.48,  0.0, 1.00), (0.80, 0.52,  8.0, 0.90)],
    4: [(0.18, 0.52,-10.0, 0.88), (0.40, 0.48, -4.0, 0.95),
        (0.62, 0.52,  4.0, 0.95), (0.84, 0.48,  9.0, 0.88)],
    5: [(0.13, 0.52,-10.0, 0.85), (0.31, 0.48, -5.0, 0.92),
        (0.52, 0.52,  0.0, 1.00), (0.71, 0.48,  5.0, 0.92),
        (0.89, 0.52, 10.0, 0.85)],
}

_THUMB_MAX = 300     # taille max de la miniature brute en cache


class CarouselManager:
    """
    Gère le carrousel de photos sur l'écran d'accueil.
    Toutes les opérations lourdes (IO, PIL) se font en background thread.
    Le rendu se fait depuis le thread principal Pygame.
    """

    def __init__(self, config):
        self._config  = config
        self._source  = Path(config.get("photos.final_dir", "Photo/final"))

        # Miniatures brutes (sans bordure) – PIL.Image convertis en pygame.Surface
        self._thumbs: List["pygame.Surface"] = []
        self._lock    = threading.Lock()
        self._offset  = 0
        self._t_last  = time.monotonic()

        # Cache de layout pour éviter de recalculer à chaque frame
        self._cache_items: list = []
        self._cache_key = None
        self._loading   = False

        if self.enabled:
            self._start_load()

    # ------------------------------------------------------------------ #
    # Propriétés lues directement depuis config (toujours à jour)          #
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # API publique                                                          #
    # ------------------------------------------------------------------ #

    def has_photos(self) -> bool:
        with self._lock:
            return len(self._thumbs) > 0

    def refresh(self):
        """Déclencher après chaque session ou changement de config."""
        if self.enabled:
            self._start_load()

    def update(self):
        """Avancer le carrousel si l'intervalle est écoulé (appeler chaque frame)."""
        if not self.enabled:
            return
        if time.monotonic() - self._t_last >= self.interval:
            self._t_last = time.monotonic()
            with self._lock:
                if len(self._thumbs) > 1:
                    self._offset = (self._offset + 1) % len(self._thumbs)
                    self._cache_items = []
                    self._cache_key   = None

    def get_render_items(self, zx: int, zy: int, zw: int, zh: int) -> list:
        """
        Retourne [(photo_surf, shadow_surf, abs_x, abs_y), …]
        photo_surf et shadow_surf sont déjà tournés et prêts à blitter.
        """
        with self._lock:
            if not self._thumbs:
                return []

            n   = min(self.max_n, len(self._thumbs))
            key = (self._offset, self.mode, n, zw, zh)

            if self._cache_key == key and self._cache_items:
                return [(p, s, x + zx, y + zy) for p, s, x, y in self._cache_items]

            photos = [self._thumbs[(self._offset + i) % len(self._thumbs)]
                      for i in range(n)]

            if self.mode == "simple":
                items = self._layout_simple(photos, zw, zh)
            else:
                items = self._layout_table(photos, zw, zh)

            self._cache_items = items
            self._cache_key   = key
            return [(p, s, x + zx, y + zy) for p, s, x, y in items]

    # ------------------------------------------------------------------ #
    # Chargement en arrière-plan                                            #
    # ------------------------------------------------------------------ #

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
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception as e:
            logger.error(f"Carousel scan: {e}")
            self._loading = False
            return

        new_thumbs = []
        for path in files[:15]:
            try:
                img = PILImage.open(path).convert("RGB")
                # Miniature brute SANS bordure (ajoutée à l'affichage pour rester visible)
                img.thumbnail((_THUMB_MAX, _THUMB_MAX), PILImage.LANCZOS)
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

    # ------------------------------------------------------------------ #
    # Layouts                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_photo_with_border(scaled: "pygame.Surface") -> "pygame.Surface":
        """
        Crée une surface SRCALPHA : photo + cadre blanc.
        Le cadre est calculé APRÈS le redimensionnement pour toujours être visible.
        """
        pw, ph = scaled.get_size()
        bw = max(7, int(min(pw, ph) * 0.07))   # 7% de la petite dimension, min 7px
        fw, fh = pw + bw * 2, ph + bw * 2

        surf = pygame.Surface((fw, fh), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        # Cadre blanc opaque
        pygame.draw.rect(surf, (252, 252, 252, 255), (0, 0, fw, fh))
        # Photo au centre
        surf.blit(scaled, (bw, bw))
        return surf

    @staticmethod
    def _make_shadow(fw: int, fh: int, alpha: int = 90) -> "pygame.Surface":
        """Ombre portée de la même taille que la photo (SRCALPHA)."""
        s = pygame.Surface((fw, fh), pygame.SRCALPHA)
        s.fill((0, 0, 0, 0))
        pygame.draw.rect(s, (0, 0, 0, alpha), (0, 0, fw, fh))
        return s

    def _layout_simple(self, photos: list, zw: int, zh: int) -> list:
        """Une photo centrée, avec bordure et ombre."""
        if not photos:
            return []
        surf = photos[0]
        iw, ih = surf.get_size()
        scale = min((zw - 20) / iw, (zh - 20) / ih, 1.0)
        if scale < 0.99:
            surf = pygame.transform.smoothscale(surf, (int(iw * scale), int(ih * scale)))
        iw, ih = surf.get_size()

        photo  = self._make_photo_with_border(surf)
        shadow = self._make_shadow(*photo.get_size())
        fw, fh = photo.get_size()
        return [(photo, shadow, (zw - fw) // 2, (zh - fh) // 2)]

    def _layout_table(self, photos: list, zw: int, zh: int) -> list:
        """
        Photos étalées comme sur une table.
        Workflow : scale → cadre blanc → rotation de l'ensemble (photo+cadre+ombre).
        """
        n = len(photos)
        if n == 0:
            return []

        # Taille de base adaptée à la zone
        base = int(zh * 0.68) if zw > zh else int(min(zw, zh) * 0.44)

        layout = _TABLE.get(n, _TABLE[min(n, 5)])
        items  = []

        for surf, (cx_r, cy_r, angle, sf) in zip(photos, layout):
            iw, ih = surf.get_size()
            tw = int(base * sf)
            th = int(tw * ih / iw)

            # Clamp pour ne pas dépasser la zone
            if tw > zw * 0.72:
                tw = int(zw * 0.72); th = int(tw * ih / iw)
            if th > zh * 0.92:
                th = int(zh * 0.92); tw = int(th * iw / ih)
            if tw < 20 or th < 20:
                continue

            # 1. Redimensionner la photo brute
            scaled = pygame.transform.smoothscale(surf, (tw, th))

            # 2. Ajouter le cadre blanc APRÈS redimensionnement
            photo_full = self._make_photo_with_border(scaled)
            fw, fh     = photo_full.get_size()

            # 3. Ombre (même taille que la photo avec cadre)
            shadow_full = self._make_shadow(fw, fh, alpha=85)

            # 4. Rotation de l'intégralité (photo+cadre et ombre tournent ensemble)
            rot_photo  = pygame.transform.rotate(photo_full,  angle)
            rot_shadow = pygame.transform.rotate(shadow_full, angle)
            rw, rh     = rot_photo.get_size()

            # 5. Positionnement dans la zone
            cx = int(cx_r * zw)
            cy = int(cy_r * zh)
            x  = max(0, min(cx - rw // 2, zw - rw))
            y  = max(0, min(cy - rh // 2, zh - rh))

            items.append((rot_photo, rot_shadow, x, y))

        return items
