"""
Carrousel de photos et GIFs sur l'écran d'accueil.
- Photos : images fixes avec bordure et ombre
- GIFs   : animation en boucle, frames chargées en arrière-plan
Chargement non bloquant, timing global sans état par item.
"""
import logging
import math
import threading
import time
from pathlib import Path
from typing import List, Optional

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

_THUMB_MAX = 600   # miniature brute (qualité mode simple)
_GIF_FRAME_MAX = 240   # frames GIF pour le carrousel (plus petites)

# ---------------------------------------------------------------------------
# Dispositions table
# ---------------------------------------------------------------------------

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
    7: [(0.07, 0.50, -8.0, 0.85), (0.21, 0.50, -5.0, 0.91),
        (0.35, 0.50, -2.0, 0.96), (0.50, 0.50,  0.0, 1.00),
        (0.65, 0.50,  2.0, 0.96), (0.79, 0.50,  5.0, 0.91),
        (0.93, 0.50,  8.0, 0.85)],
    8: [(0.06, 0.50, -8.0, 0.83), (0.19, 0.50, -5.0, 0.89),
        (0.31, 0.50, -3.0, 0.94), (0.44, 0.50, -1.0, 0.98),
        (0.56, 0.50,  1.0, 0.98), (0.69, 0.50,  3.0, 0.94),
        (0.81, 0.50,  5.0, 0.89), (0.94, 0.50,  8.0, 0.83)],
    9: [(0.05, 0.50, -8.0, 0.81), (0.16, 0.50, -6.0, 0.87),
        (0.27, 0.50, -3.0, 0.92), (0.38, 0.50, -1.0, 0.96),
        (0.50, 0.50,  0.0, 1.00), (0.62, 0.50,  1.0, 0.96),
        (0.73, 0.50,  3.0, 0.92), (0.84, 0.50,  6.0, 0.87),
        (0.95, 0.50,  8.0, 0.81)],
}

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
    6: [(0.22, 0.22, -4.0, 0.88), (0.50, 0.18,  0.0, 0.88), (0.78, 0.22,  3.0, 0.88),
        (0.22, 0.74, -3.0, 0.88), (0.50, 0.78,  1.0, 0.88), (0.78, 0.74,  4.0, 0.88)],
    7: [(0.18, 0.22, -4.0, 0.84), (0.50, 0.18,  0.0, 0.84), (0.82, 0.22,  3.0, 0.84),
        (0.18, 0.74, -3.0, 0.84), (0.82, 0.74,  4.0, 0.84),
        (0.35, 0.50, -2.0, 0.80), (0.65, 0.50,  2.0, 0.80)],
    8: [(0.22, 0.18, -4.0, 0.82), (0.50, 0.15,  0.0, 0.82), (0.78, 0.18,  3.0, 0.82),
        (0.22, 0.50, -2.0, 0.82), (0.78, 0.50,  2.0, 0.82),
        (0.22, 0.80, -3.0, 0.82), (0.50, 0.82,  1.0, 0.82), (0.78, 0.80,  4.0, 0.82)],
    9: [(0.18, 0.18, -3.0, 0.78), (0.50, 0.16,  0.0, 0.78), (0.82, 0.18,  3.0, 0.78),
        (0.18, 0.50, -2.0, 0.78), (0.50, 0.50,  0.0, 0.78), (0.82, 0.50,  2.0, 0.78),
        (0.18, 0.82, -3.0, 0.78), (0.50, 0.82,  1.0, 0.78), (0.82, 0.82,  3.0, 0.78)],
}


class CarouselManager:
    """
    Carrousel photos + GIFs animés.
    Structure par item : {"frames": [Surface], "durations": [float], "is_gif": bool}
    Timing GIF : horloge globale + modulo total durée (pas d'état par item).
    """

    def __init__(self, config):
        self._config       = config
        self._source       = Path(config.get("photos.final_dir",    "Photo/final"))
        self._thumb_source = Path(config.get("gif.thumbnails_dir",  "Photo/thumbnails"))
        self._gif_dir      = Path(config.get("gif.output_dir",      "Photo/gifs"))
        self._items: List[dict] = []     # {"frames", "durations", "is_gif"}
        self._lock     = threading.Lock()
        self._offset   = 0
        self._t_last   = time.monotonic()
        self._cache_items: list = []
        self._cache_key = None
        self._loading   = False

        if self.enabled:
            self._start_load()

    # --- Propriétés ---

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
        return min(9, int(self._config.get("home_carousel.max_photos_displayed", 9)))

    @property
    def animate_gifs(self) -> bool:
        return bool(self._config.get("home_carousel.animate_gifs", True))

    @property
    def max_animated_gifs(self) -> int:
        return int(self._config.get("home_carousel.max_animated_gifs", 2))

    # --- API publique ---

    def has_photos(self) -> bool:
        with self._lock:
            return len(self._items) > 0

    def refresh(self):
        if self.enabled:
            self._start_load()

    def clear(self):
        """Vide immédiatement le cache mémoire — appeler avant refresh() après un reset."""
        with self._lock:
            self._items       = []
            self._cache_items = []
            self._cache_key   = None

    def update(self):
        if not self.enabled:
            return
        if time.monotonic() - self._t_last >= self.interval:
            self._t_last = time.monotonic()
            with self._lock:
                if len(self._items) > 1:
                    self._offset = (self._offset + 1) % len(self._items)
                    self._cache_items = []
                    self._cache_key   = None

    def get_render_items(self, zx: int, zy: int, zw: int, zh: int,
                         is_portrait: bool = False) -> list:
        with self._lock:
            if not self._items:
                return []

            n        = min(self.max_n, len(self._items))
            total    = len(self._items)
            now      = time.monotonic()
            animate  = self.animate_gifs
            max_anim = self.max_animated_gifs
            anim_cnt = 0

            # Calculer la frame courante pour chaque item
            current_surfs = []
            gif_flags     = []

            for i in range(n):
                item      = self._items[(self._offset + i) % total]
                frames    = item.get("frames", [])
                durs      = item.get("durations", [1.0])
                is_gif    = item.get("is_gif", False)
                is_anim   = is_gif and len(frames) > 1 and animate and anim_cnt < max_anim

                if not frames:
                    continue

                if is_anim:
                    # Timing global : décalage de 0.7s par GIF pour ne pas être synchrones
                    total_dur = max(0.001, sum(durs))
                    phase     = (now + i * 0.7) % total_dur
                    acc, fidx = 0.0, 0
                    for j, d in enumerate(durs):
                        if phase < acc + d:
                            fidx = j
                            break
                        acc += d
                    else:
                        fidx = len(frames) - 1
                    current_surfs.append(frames[fidx % len(frames)])
                    anim_cnt += 1
                else:
                    current_surfs.append(frames[0])

                gif_flags.append(is_gif)

            if not current_surfs:
                return []

            real_n = len(current_surfs)
            # Clé de cache : inclut le temps arrondi si des GIF sont animés
            time_key = round(now * 8) if (animate and anim_cnt > 0) else 0
            key = (self._offset, self.mode, real_n, zw, zh, is_portrait, time_key)

            if self._cache_key == key and self._cache_items:
                return [(p, s, x + zx, y + zy) for p, s, x, y in self._cache_items]

            if self.mode == "simple":
                items = self._layout_simple(current_surfs, zw, zh, is_portrait, gif_flags)
            else:
                items = self._layout_table(current_surfs, zw, zh, is_portrait, gif_flags)

            # Ne pas cacher si des GIF sont animés (mise à jour chaque ~125ms)
            if anim_cnt == 0:
                self._cache_items = items
                self._cache_key   = key

            return [(p, s, x + zx, y + zy) for p, s, x, y in items]

    # --- Chargement ---

    def _start_load(self):
        if self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        if not (_PIL_OK and _PYGAME_OK):
            self._loading = False
            return

        # Scanner photos finales + miniatures GIF
        all_files: list = []
        for src, is_gif in [(self._source, False), (self._thumb_source, True)]:
            if src.exists():
                try:
                    for p in src.glob("*.jpg"):
                        if p.is_file():
                            all_files.append((p, is_gif))
                except Exception as e:
                    logger.error(f"Carousel scan {src}: {e}")

        if not all_files:
            self._loading = False
            return

        all_files.sort(key=lambda t: t[0].stat().st_mtime, reverse=True)

        new_items = []
        for path, is_gif in all_files[:15]:
            try:
                if is_gif:
                    # Chercher le GIF source correspondant à la miniature
                    gif_path = self._find_gif(path)
                    if gif_path:
                        frames, durs = self._load_gif_frames(gif_path)
                        if frames:
                            new_items.append({
                                "frames":    frames,
                                "durations": durs,
                                "is_gif":    True,
                            })
                            continue
                # Photo fixe (ou GIF sans source)
                img = PILImage.open(path).convert("RGB")
                img.thumbnail((_THUMB_MAX, _THUMB_MAX), PILImage.LANCZOS)
                surf = pygame.image.fromstring(img.tobytes(), img.size, "RGB")
                new_items.append({
                    "frames":    [surf],
                    "durations": [1.0],
                    "is_gif":    is_gif,
                })
            except Exception as e:
                logger.debug(f"Carousel: ignore {path.name}: {e}")

        with self._lock:
            self._items       = new_items
            self._cache_items = []
            self._cache_key   = None

        n_gifs   = sum(1 for it in new_items if it["is_gif"] and len(it["frames"]) > 1)
        n_photos = len(new_items) - n_gifs
        logger.info(f"Carousel: {n_photos} photos + {n_gifs} GIFs animés chargés")
        self._loading = False

    def _find_gif(self, thumb_path: Path) -> Optional[str]:
        """Trouve le fichier GIF source correspondant à une miniature."""
        stem = thumb_path.stem   # gif_0001_20260609_123456
        for d in (self._gif_dir, self._thumb_source.parent / "gifs"):
            p = d / f"{stem}.gif"
            if p.exists():
                return str(p)
        return None

    def _load_gif_frames(self, gif_path: str):
        """Charge toutes les frames d'un GIF en surfaces pygame."""
        try:
            gif    = PILImage.open(gif_path)
            frames = []
            durs   = []
            idx    = 0
            while True:
                try:
                    img = gif.convert("RGB")
                    img.thumbnail((_GIF_FRAME_MAX, _GIF_FRAME_MAX), PILImage.LANCZOS)
                    surf = pygame.image.fromstring(img.tobytes(), img.size, "RGB")
                    dur  = gif.info.get("duration", 180) / 1000.0
                    frames.append(surf)
                    durs.append(max(0.05, dur))
                    gif.seek(idx + 1)
                    idx += 1
                except EOFError:
                    break
            logger.debug(f"GIF carousel : {len(frames)} frames depuis {gif_path}")
            return frames, durs
        except Exception as e:
            logger.debug(f"GIF frames load ({gif_path}): {e}")
            return [], []

    # --- Helpers bordure / ombre ---

    @staticmethod
    def _fit_in_box(surf, box_w, box_h, sf=1.0):
        iw, ih = surf.get_size()
        scale  = min(box_w / iw, box_h / ih) * sf
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        return pygame.transform.smoothscale(surf, (nw, nh))

    @staticmethod
    def _add_border_and_shadow(scaled: "pygame.Surface", is_gif: bool = False):
        pw, ph = scaled.get_size()
        border = max(6, int(min(pw, ph) * 0.068))
        fw, fh = pw + border * 2, ph + border * 2

        photo = pygame.Surface((fw, fh), pygame.SRCALPHA)
        photo.fill((0, 0, 0, 0))
        pygame.draw.rect(photo, (252, 252, 252, 255), (0, 0, fw, fh))
        photo.blit(scaled, (border, border))

        if is_gif:
            try:
                font  = pygame.font.SysFont("dejavusans", max(10, int(min(fw, fh) * 0.12)))
                badge = font.render("GIF", True, (255, 255, 255))
                bw, bh = badge.get_size()
                pad    = max(2, bw // 6)
                bg     = pygame.Surface((bw + pad*2, bh + pad), pygame.SRCALPHA)
                pygame.draw.rect(bg, (148, 103, 189, 220),
                                 (0, 0, bw + pad*2, bh + pad), border_radius=3)
                bg.blit(badge, (pad, pad // 2))
                photo.blit(bg, (fw - bg.get_width() - border,
                                fh - bg.get_height() - border))
            except Exception:
                pass

        shadow = pygame.Surface((fw, fh), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 0))
        pygame.draw.rect(shadow, (0, 0, 0, 88), (0, 0, fw, fh))
        return photo, shadow

    # --- Layouts ---

    def _layout_simple(self, photos, zw, zh, is_portrait, gif_flags=None):
        if not photos:
            return []
        surf   = photos[0]
        iw, ih = surf.get_size()
        BORDER = max(3, int(min(zw, zh) * 0.008))
        scale  = min((zw - BORDER*2 - 4) / iw, (zh - BORDER*2 - 4) / ih)
        nw     = max(1, int(iw * scale))
        nh     = max(1, int(ih * scale))
        scaled = pygame.transform.smoothscale(surf, (nw, nh))
        is_gif = gif_flags[0] if gif_flags else False

        fw, fh = nw + BORDER*2, nh + BORDER*2
        photo  = pygame.Surface((fw, fh), pygame.SRCALPHA)
        photo.fill((0, 0, 0, 0))
        pygame.draw.rect(photo, (252, 252, 252, 255), (0, 0, fw, fh))
        photo.blit(scaled, (BORDER, BORDER))
        shadow = pygame.Surface((fw, fh), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 0))
        pygame.draw.rect(shadow, (0, 0, 0, 65), (0, 0, fw, fh))

        if is_gif:
            photo, shadow = self._add_border_and_shadow(scaled, is_gif=True)
            fw, fh = photo.get_size()

        return [(photo, shadow, (zw - fw) // 2, (zh - fh) // 2)]

    def _layout_table(self, photos, zw, zh, is_portrait, gif_flags=None):
        n = len(photos)
        if n == 0:
            return []

        if is_portrait:
            S_ratio = 0.42 if n <= 2 else (0.33 if n <= 4 else 0.26)
            S       = max(75, min(int(zw * S_ratio), int(zh * 0.82)))
            box_w, box_h = S, S
            max_rot = 5.0
            table   = _TABLE_P.get(n, _TABLE_P[min(n, 9)])
        else:
            S_ratio = 0.22 if n <= 3 else (0.17 if n <= 5 else 0.14)
            S       = max(60, min(int(zw * S_ratio), int(zh * 0.78)))
            box_w, box_h = S, S
            max_rot = 8.0
            table   = _TABLE_L.get(n, _TABLE_L[min(n, 9)])

        items = []
        for idx, (surf, (cx_r, cy_r, raw_angle, sf)) in enumerate(zip(photos, table)):
            angle  = max(-max_rot, min(max_rot, raw_angle))
            is_gif = (gif_flags[idx] if gif_flags and idx < len(gif_flags) else False)

            scaled = self._fit_in_box(surf, box_w, box_h, sf)
            pw, ph = scaled.get_size()
            if pw < 10 or ph < 10:
                continue

            photo_full, shadow_full = self._add_border_and_shadow(scaled, is_gif=is_gif)
            fw, fh = photo_full.get_size()

            if abs(angle) > 0.3:
                rot_photo  = pygame.transform.rotozoom(photo_full,  angle, 1.0)
                rot_shadow = pygame.transform.rotozoom(shadow_full, angle, 1.0)
            else:
                rot_photo, rot_shadow = photo_full, shadow_full
            rw, rh = rot_photo.get_size()

            if rw > zw or rh > zh:
                s = min(zw / rw, zh / rh) * 0.95
                rot_photo  = pygame.transform.smoothscale(rot_photo,  (int(rw*s), int(rh*s)))
                rot_shadow = pygame.transform.smoothscale(rot_shadow, (int(rw*s), int(rh*s)))
                rw, rh     = rot_photo.get_size()

            cx = int(cx_r * zw)
            cy = int(cy_r * zh)
            x  = max(0, min(cx - rw // 2, zw - rw))
            y  = max(0, min(cy - rh // 2, zh - rh))

            items.append((rot_photo, rot_shadow, x, y))

        return items
