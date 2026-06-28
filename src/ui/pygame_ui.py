import logging
import math
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import pygame

from ui.carousel       import CarouselManager
from ui.layout_manager import LayoutManager

logger = logging.getLogger(__name__)

# Palette
_BLACK  = (0,   0,   0)
_WHITE  = (255, 255, 255)
_DARK   = (22,  27,  34)
_DARK2  = (36,  41,  47)
_PANEL  = (48,  54,  61)
_ACCENT = (255, 165,  0)
_GREEN  = (46,  160,  67)
_RED    = (207,  34,  46)
_BLUE   = (31,  111, 235)
_GRAY   = (100, 110, 120)
_LGRAY  = (190, 200, 210)
_DISABLED = (70, 78, 88)

# Ces constantes sont désormais des propriétés dynamiques calculées par LayoutManager.
# Valeurs par défaut (480×800) conservées pour compatibilité pendant la migration.
ROW_H = 54
HDR_H = 52
BTN_H = 52


class _Btn:
    fixed = False   # True = position absolue, non affectée par le scroll admin

    def __init__(self, rect, text, color, text_color=_WHITE, font=None,
                 action=None, data=None, radius=10, no_draw=False, selected=False):
        self.rect     = pygame.Rect(rect)
        self.text     = text
        self.color    = color
        self.text_color = text_color
        self.font     = font
        self.action   = action
        self.data     = data
        self.radius   = radius
        self.no_draw  = no_draw
        self.selected = selected   # True = sélectionné par le clavier
        self._hover   = False

    def draw(self, surf):
        if self.no_draw:
            return
        if self._hover:
            c = tuple(min(v + 25, 255) for v in self.color)
        elif self.selected:
            # Fond plus lumineux quand sélectionné au clavier
            c = tuple(min(v + 60, 255) for v in self.color)
        else:
            c = self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=self.radius)
        # Contour blanc quand sélectionné au clavier
        if self.selected:
            pygame.draw.rect(surf, _WHITE, self.rect,
                             max(2, self.rect.height // 16), border_radius=self.radius)
        if self.font and self.text:
            text = str(self.text)
            max_w = self.rect.width - 12
            # Troncature avec "…" si le texte dépasse la largeur du bouton
            if self.font.size(text)[0] > max_w:
                while len(text) > 1 and self.font.size(text + "…")[0] > max_w:
                    text = text[:-1]
                text += "…"
            ts = self.font.render(text, True, self.text_color)
            surf.blit(ts, ts.get_rect(center=self.rect.center))

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return (self.action, self.data)
        return None


class _NavBtn(_Btn):
    """
    Bouton de navigation admin avec titre + description.
    Se dessine lui-même (évite que le fond ne recouvre le texte).
    """
    def __init__(self, rect, label, desc, font_label, font_desc, action, data):
        super().__init__(rect, "", _DARK2, action=action, data=data, radius=8)
        self._label = label
        self._desc  = desc
        self._fl    = font_label
        self._fd    = font_desc

    def draw(self, surf):
        c = (55, 62, 72) if self._hover else _DARK2
        pygame.draw.rect(surf, c, self.rect, border_radius=8)
        cy = self.rect.centery
        if self._label:
            ts = self._fl.render(self._label, True, _WHITE)
            surf.blit(ts, (self.rect.x + 14, cy - ts.get_height() - 1))
        if self._desc:
            ds = self._fd.render(self._desc, True, _GRAY)
            surf.blit(ds, (self.rect.x + 14, cy + 4))
        arrow = self._fl.render(">", True, _GRAY)
        surf.blit(arrow, arrow.get_rect(right=self.rect.right - 14, centery=cy))


class PygameUI:

    def __init__(self, config):
        # Dimensions de configuration (définissent l'orientation)
        self._config_w    = config.get("app.width", 800)
        self._config_h    = config.get("app.height", 480)
        self._w           = self._config_w
        self._h           = self._config_h
        self._fps         = config.get("app.fps", 30)
        self._fullscreen  = config.get("app.fullscreen", True)
        self._font_path   = config.get("app.font_path")
        self._qr_size     = config.get("qr.size", 300)

        self._callback: Optional[Callable] = None
        self._activity_callback: Optional[Callable] = None
        self._screen = None
        self._clock  = None
        self._running = False

        self._screen_name = "idle"
        self._buttons: List[_Btn] = []
        self._info: dict = {}
        self._preview_frame = None
        self._preview_lock  = threading.Lock()

        self._admin_page            = "main"
        self._admin_stack: List[str] = []
        self._admin_scroll           = 0
        self._admin_scroll_cache: dict = {}
        self._admin_selection: int   = 0
        self._admin_selection_cache: dict = {}
        self._text_editing: Optional[str] = None

        self._fonts: dict = {}
        self._lm: Optional[LayoutManager] = None   # initialisé dans _init_pygame
        self._init_pygame()
        # Carrousel (init après pygame pour les surfaces)
        self._carousel = CarouselManager(config)

    @property
    def screen_name(self) -> str:
        return self._screen_name

    @property
    def _is_portrait(self) -> bool:
        """True si l'écran est en mode portrait (h > w, ex: 480×800)."""
        return self._h > self._w

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_pygame(self):
        """
        Rendu à la résolution NATIVE → zéro pixelation.
        LayoutManager calcule polices/marges proportionnellement à la résolution réelle.

        PC fenêtré  (480×800)   : scale=1.0, identique à la config
        Pi fullscreen (1080×1920): scale=2.25, net et lisible

        Les deux modes donnent le MÊME rendu proportionnel :
        même ratios, mêmes positions relatives, police adaptée à la taille d'écran.
        """
        pygame.init()

        if self._fullscreen:
            info = pygame.display.Info()
            rw   = info.current_w if info.current_w > 0 else self._config_w
            rh   = info.current_h if info.current_h > 0 else self._config_h
            # Maintenir l'orientation configurée
            if (self._config_h > self._config_w) and rw > rh:
                rw, rh = rh, rw   # swap → portrait
            elif (self._config_w > self._config_h) and rh > rw:
                rw, rh = rh, rw   # swap → paysage
            flags         = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
            self._display = pygame.display.set_mode((rw, rh), flags)
        else:
            self._display = pygame.display.set_mode((self._config_w, self._config_h))

        # Masquer le curseur après set_mode (obligatoire sur Windows/certains systèmes)
        pygame.mouse.set_visible(False)

        # self._screen = self._display : rendu direct à la résolution native (net)
        self._screen         = self._display
        self._w, self._h     = self._screen.get_size()
        self._scale          = 1.0   # pas de scaling secondaire
        self._offset_x       = 0
        self._offset_y       = 0

        orient       = "portrait" if self._h > self._w else "paysage"
        scale_factor = round(min(self._w / self._config_w, self._h / self._config_h), 2)

        logger.info(f"Resolution config  : {self._config_w}x{self._config_h}")
        logger.info(f"Resolution rendu   : {self._w}x{self._h}")
        logger.info(f"Orientation        : {orient}")
        logger.info(f"Scale factor       : {scale_factor}")

        pygame.display.set_caption("SnapForge")
        self._clock = pygame.time.Clock()

        # LayoutManager sur la résolution RENDUE
        self._lm = LayoutManager(self._w, self._h)
        global ROW_H, HDR_H, BTN_H
        ROW_H = self._lm.row_h
        HDR_H = self._lm.hdr_h
        BTN_H = self._lm.btn_h

        self._load_fonts()
        logger.info(f"LayoutManager      : {self._lm}")

    def _load_fonts(self):
        """Charge les polices avec des tailles proportionnelles depuis LayoutManager."""
        lm = self._lm
        specs = {
            "xs":  lm.font_xs,
            "sm":  lm.font_sm,
            "md":  lm.font_md,
            "lg":  lm.font_lg,
            "xl":  lm.font_xl,
            "xxl": lm.font_xxl,
        }
        for name, size in specs.items():
            try:
                if self._font_path and Path(self._font_path).exists():
                    self._fonts[name] = pygame.font.Font(self._font_path, size)
                else:
                    self._fonts[name] = pygame.font.SysFont("dejavusans", size)
            except Exception:
                self._fonts[name] = pygame.font.Font(None, max(size, 12))

    def set_touch_callback(self, cb: Callable):
        self._callback = cb

    def set_activity_callback(self, cb: Callable):
        self._activity_callback = cb

    def _notify_activity(self):
        if self._activity_callback:
            threading.Thread(target=self._activity_callback, daemon=True).start()

    def _emit(self, action: str, data=None):
        if self._callback:
            threading.Thread(target=self._callback, args=(action, data), daemon=True).start()

    def _btn(self, text, color, rect, font="md", action=None, data=None, radius=10):
        return _Btn(rect, text, color, font=self._fonts[font], action=action, data=data, radius=radius)

    def _btn_auto(self, text, color, cx, cy, font="md", px=40, py=18, action=None, data=None):
        tw, th = self._fonts[font].size(str(text))
        w, h = tw + px * 2, th + py * 2
        return _Btn((cx - w//2, cy - h//2, w, h), text, color,
                    font=self._fonts[font], action=action, data=data)

    # ------------------------------------------------------------------
    # show_* — appelés depuis threads FSM
    # ------------------------------------------------------------------

    def show_idle(self, booth_name: str = "SnapForge",
                 booth_name_size: int = 0,
                 booth_subtitle: str = "",
                 booth_subtitle_size: int = 0):
        self._screen_name = "idle"
        self._info = {
            "booth_name":          booth_name,
            "booth_name_size":     booth_name_size,
            "booth_subtitle":      booth_subtitle,
            "booth_subtitle_size": booth_subtitle_size,
        }
        with self._preview_lock:
            self._preview_frame = None
        # Police et position du bouton adaptées à la largeur de l'écran
        txt      = "APPUYEZ POUR COMMENCER"
        font_key = "md" if self._is_portrait else "lg"
        px       = 20   if self._is_portrait else 50
        # Centre du bouton : marge en bas = btn_h + 2×gap_md (confortable, non collé)
        lm = self._lm
        cy = self._h - lm.btn_h - lm.gap_md * 2
        self._buttons = [
            self._btn_auto(txt, _ACCENT, self._w // 2, cy,
                           font=font_key, px=px, py=22,
                           action="open_choose_type")
        ]
        # Recharger les photos du carrousel après chaque retour à l'accueil
        self._carousel.refresh()

    def clear_carousel(self):
        """Vide immédiatement le carrousel (à appeler avant refresh après un reset)."""
        self._carousel.clear()

    def show_choose_type(self):
        """Écran niveau 1 : Photo ou GIF ?"""
        self._screen_name = "choose_type"
        self._info = {}
        lm = self._lm
        m  = lm.margin
        bw = int(self._w * 0.78) if self._is_portrait else (self._w - 3*m) // 2
        bh = max(60, int(self._h * 0.20))
        font = self._best_font_for("GIF ANIME", bw, pad=30)

        if self._is_portrait:
            gap     = max(14, int(self._h * 0.025))
            total_h = 2 * bh + gap
            y0      = self._h // 2 - total_h // 2
            x       = (self._w - bw) // 2
            self._buttons = [
                _Btn((x, y0, bw, bh), "PHOTO",     _BLUE,
                     font=font, action="open_choose_format", radius=20),
                _Btn((x, y0 + bh + gap, bw, bh), "GIF ANIME", (148, 103, 189),
                     font=font, action="open_choose_gif_orientation",           radius=20),
            ]
        else:
            gap = m
            y   = self._h // 2 - bh // 2
            x0  = m
            x1  = m * 2 + bw
            self._buttons = [
                _Btn((x0, y, bw, bh), "PHOTO",     _BLUE,
                     font=font, action="open_choose_format", radius=20),
                _Btn((x1, y, bw, bh), "GIF ANIME", (148, 103, 189),
                     font=font, action="open_choose_gif_orientation",           radius=20),
            ]

    def show_choose_format(self, layouts: List[int], selected: int,
                           gif_enabled: bool = False):
        self._screen_name = "choose_format"
        self._info = {"layouts": layouts, "selected": selected, "gif_enabled": gif_enabled}
        self._rebuild_format_buttons(layouts, selected, gif_enabled)

    def show_choose_gif_orientation(self):
        """Écran niveau 3 : Portrait ou Paysage pour le GIF animé."""
        self._screen_name = "choose_gif_orientation"
        self._info = {}
        lm  = self._lm
        m   = lm.margin
        bw  = int(self._w * 0.78) if self._is_portrait else (self._w - 3 * m) // 2
        bh  = max(60, int(self._h * 0.20))
        font = self._best_font_for("PAYSAGE", bw, pad=30)

        if self._is_portrait:
            gap    = max(14, int(self._h * 0.025))
            total_h = 2 * bh + gap
            y0     = self._h // 2 - total_h // 2
            x      = (self._w - bw) // 2
            self._buttons = [
                _Btn((x, y0,            bw, bh), "PORTRAIT", _BLUE,
                     font=font, action="gif_portrait",  radius=20),
                _Btn((x, y0 + bh + gap, bw, bh), "PAYSAGE",  _GREEN,
                     font=font, action="gif_landscape", radius=20),
            ]
        else:
            gap = m
            y   = self._h // 2 - bh // 2
            x0  = m
            x1  = m * 2 + bw
            self._buttons = [
                _Btn((x0, y, bw, bh), "PORTRAIT", _BLUE,
                     font=font, action="gif_portrait",  radius=20),
                _Btn((x1, y, bw, bh), "PAYSAGE",  _GREEN,
                     font=font, action="gif_landscape", radius=20),
            ]

    def update_format_selection(self, selected: int):
        self._info["selected"] = selected

    def _rebuild_format_buttons(self, layouts, selected, gif_enabled=False):
        n      = len(layouts)
        n_all  = n + (1 if gif_enabled else 0)  # total incluant GIF
        longest = max((f"{v} PHOTO{'S' if v > 1 else ''}" for v in layouts), key=len)
        btns   = []

        if self._is_portrait:
            btn_area_top = int(self._h * 0.18)
            btn_area_bot = int(self._h * 0.87)
            available_h  = btn_area_bot - btn_area_top
            btn_h  = min(int(self._h * 0.22), (available_h - (n_all - 1) * 16) // n_all)
            btn_h  = max(52, btn_h)
            btn_w  = int(self._w * 0.78)
            gap_v  = max(12, (available_h - n_all * btn_h) // (n_all + 1))
            y_start = btn_area_top + gap_v
            font = self._best_font_for(longest, btn_w)
            for i, v in enumerate(layouts):
                x = (self._w - btn_w) // 2
                y = y_start + i * (btn_h + gap_v)
                c = _ACCENT if v == selected else _BLUE
                btns.append(_Btn((x, y, btn_w, btn_h),
                                 f"{v} PHOTO{'S' if v > 1 else ''}",
                                 c, font=font, action="start_session", data=v, radius=20))
            if gif_enabled:
                gif_y = y_start + n * (btn_h + gap_v)
                btns.append(_Btn((x, gif_y, btn_w, btn_h), "GIF ANIME",
                                 (148, 103, 189), font=font,
                                 action="start_gif", data=None, radius=20))
        else:
            all_labels = [f"{v} PHOTO{'S' if v > 1 else ''}" for v in layouts]
            if gif_enabled:
                all_labels.append("GIF")
            margin, gap = 30, 20
            btn_w = (self._w - 2*margin - gap*(n_all-1)) // n_all
            btn_h = int(self._h * 0.55)
            y     = self._h // 2 - btn_h // 2 - 20
            font  = self._best_font_for(max(all_labels, key=len), btn_w)
            for i, v in enumerate(layouts):
                x = margin + i * (btn_w + gap)
                c = _ACCENT if v == selected else _BLUE
                btns.append(_Btn((x, y, btn_w, btn_h),
                                 f"{v} PHOTO{'S' if v > 1 else ''}",
                                 c, font=font, action="start_session", data=v, radius=20))
            if gif_enabled:
                gx = margin + n * (btn_w + gap)
                btns.append(_Btn((gx, y, btn_w, btn_h), "GIF",
                                 (148, 103, 189), font=font,
                                 action="start_gif", data=None, radius=20))

        self._buttons = btns

    def _best_font_for(self, text, max_w, pad=40):
        for key in ("xl", "lg", "md", "sm", "xs"):
            if self._fonts[key].size(text)[0] + pad * 2 <= max_w:
                return self._fonts[key]
        return self._fonts["xs"]

    def _font_at_size(self, size: int):
        """Charge une police à la taille exacte en pixels."""
        size = max(8, size)
        try:
            if self._font_path and Path(self._font_path).exists():
                return pygame.font.Font(self._font_path, size)
            return pygame.font.SysFont("dejavusans", size)
        except Exception:
            return pygame.font.Font(None, size)

    def show_preview(self, total: int, remaining: int, slot_ar=None):
        self._screen_name = "preview"
        self._info = {"total": total, "remaining": remaining, "countdown": 0,
                      "slot_ar": slot_ar}
        lm = self._lm
        # Bouton fixe en bas de l'écran (sous la boîte preview quelle que soit sa taille)
        btn_cy = self._h - lm.btn_h - lm.gap_md
        self._buttons = [
            self._btn_auto("CAPTURER", _ACCENT, self._w // 2, btn_cy,
                           font="md", px=50, py=18, action="start_countdown")
        ]

    def update_preview_frame(self, frame: np.ndarray):
        with self._preview_lock:
            self._preview_frame = frame

    def show_countdown(self, value: int):
        self._info["countdown"] = value
        self._info["smile"]     = False
        self._buttons = []

    def show_smile(self, countdown: int = 0):
        """Affiche 'Souriez !' (+ décompte optionnel entre captures GIF)."""
        self._info["countdown"] = countdown
        self._info["smile"]     = True
        self._buttons = []

    def show_gif_frame_counter(self, current: int, total: int):
        """Affiche 'Image N/total' pendant la capture rapide GIF."""
        self._info["gif_counter"]  = f"Image {current}/{total}"
        self._info["countdown"]    = 0
        self._info["smile"]        = False

    def show_capture_result(self, path: str, remaining: int):
        self._info["last_photo"] = path
        self._info["remaining"]  = remaining
        self._info["countdown"]  = 0
        self._info["smile"]      = False
        self._info["gif_counter"] = ""

    def show_processing(self, step: str):
        self._screen_name = "processing"
        self._buttons = []
        self._info = {"step": step}
        with self._preview_lock:
            self._preview_frame = None

    def show_review(self, photo_path: str, printer_enabled: bool = False):
        self._screen_name = "review"
        self._info = {"photo": photo_path}
        m  = 20
        bh = max(80, self._lm.btn_h)
        bw = (self._w - 3 * m) // 2
        if printer_enabled:
            self._buttons = [
                self._btn("IMPRIMER",  _BLUE,  (m,        self._h - bh - m, bw, bh), "md", "confirm_print"),
                self._btn("CONTINUER", _GREEN, (m*2 + bw, self._h - bh - m, bw, bh), "md", "skip_print"),
            ]
        else:
            self._buttons = [
                self._btn("CONTINUER", _GREEN, (m, self._h - bh - m, self._w - 2*m, bh), "md", "skip_print"),
            ]

    def show_print_wait(self):
        """Cache les boutons : le message d'impression apparaît en premier plan."""
        self._buttons = []
        self._info["status"] = "Impression en cours..."

    def show_print_result(self, success: bool, msg: str = None):
        """Cache les boutons : le message résultat apparaît en premier plan."""
        self._buttons = []
        self._info["status"] = msg if msg is not None else ("Imprimé !" if success else "Erreur d'impression")

    def show_qr(self, photo_path: str, qr_image, upload_url, gif_path: str = None):
        self._screen_name = "qr"
        self._info = {
            "photo":         photo_path,
            "qr":            qr_image,
            "url":           upload_url,
            "gif_path":      gif_path,
            "gif_frames":    None,      # chargé en arrière-plan
            "gif_durations": None,
            "gif_frame_idx": 0,
            "gif_frame_t":   0.0,
        }
        lm     = self._lm
        btn_cy = self._h - lm.btn_h // 2 - lm.gap_md
        self._buttons = [
            self._btn_auto("RETOUR ACCUEIL", _BLUE, self._w // 2, btn_cy,
                           font="xs", px=28, py=10, action="return_idle")
        ]
        # Charger les frames GIF en arrière-plan
        if gif_path and Path(gif_path).exists():
            threading.Thread(target=self._load_gif_frames,
                             args=(gif_path,), daemon=True).start()

    def _load_gif_frames(self, gif_path: str):
        """Charge toutes les frames du GIF en arrière-plan pour l'animation."""
        try:
            from PIL import Image as PILImg
            gif    = PILImg.open(gif_path)
            frames = []
            durs   = []
            idx    = 0
            while True:
                try:
                    frame = gif.convert("RGB")
                    surf  = pygame.image.fromstring(frame.tobytes(), frame.size, "RGB")
                    dur   = gif.info.get("duration", 180) / 1000.0
                    frames.append(surf)
                    durs.append(max(0.05, dur))
                    gif.seek(idx + 1)
                    idx += 1
                except EOFError:
                    break
            self._info["gif_frames"]    = frames
            self._info["gif_durations"] = durs
            self._info["gif_frame_t"]   = time.time()
            logger.info(f"GIF animé : {len(frames)} frames chargées depuis {gif_path}")
        except Exception as e:
            logger.error(f"Chargement GIF frames : {e}")

    def show_uploading(self):
        """Affiche brièvement 'Envoi en cours...' pendant l'upload cloud."""
        self._screen_name = "uploading"
        self._buttons     = []
        self._info        = {}

    def show_error(self, message: str):
        self._screen_name = "error"
        self._buttons = []
        self._info = {"msg": str(message)}

    def show_usb_export(self, status: str = ""):
        self._screen_name = "usb_export"
        self._buttons = []
        self._info = {"usb_status": status, "usb_done": False, "usb_success": True}

    def update_usb_status(self, status: str, done: bool = False, success: bool = True):
        # Sépare le message principal du sous-titre (séparateur \n)
        parts = status.split("\n", 1)
        self._info["usb_status"]   = parts[0]
        self._info["usb_subtitle"] = parts[1] if len(parts) > 1 else ""
        self._info["usb_done"]     = done
        self._info["usb_success"]  = success

    @staticmethod
    def _confirm_quit_geometry(w, h, lm):
        """Calcul des dimensions du dialogue Quitter — partagé render + show."""
        box_w  = min(int(w * 0.88), int(lm.font_md * 20))
        box_h  = int(h * 0.40)               # boîte plus grande = plus de place
        box_x  = (w - box_w) // 2
        box_y  = h // 2 - box_h // 2
        gap    = max(8, lm.gap_sm)
        half   = (box_w - gap) // 2
        bh     = lm.btn_h
        by     = box_y + int(box_h * 0.66)   # boutons dans les 33 % bas de la boîte
        bx     = box_x
        return box_x, box_y, box_w, box_h, bx, by, half, bh, gap

    def show_confirm_quit(self):
        """
        Dialogue de confirmation de fermeture.
        NE PAS effacer self._info — contient les settings admin pour le retour.
        """
        self._screen_name = "confirm_quit"
        self._info["quit_sel"] = 0   # 0 = Annuler (défaut sécurisé), 1 = Confirmer
        self._build_confirm_quit_buttons(0)

    def _build_confirm_quit_buttons(self, sel: int):
        """Construit les boutons Annuler/Confirmer avec la sélection active."""
        lm = self._lm
        box_x, box_y, box_w, box_h, bx, by, half, bh, gap = \
            self._confirm_quit_geometry(self._w, self._h, lm)
        self._buttons = [
            _Btn((bx,          by, half, bh), "Annuler",   _GRAY,
                 font=self._fonts["sm"], action="cancel_quit", radius=8,
                 selected=(sel == 0)),
            _Btn((bx+half+gap, by, half, bh), "Confirmer", _RED,
                 font=self._fonts["sm"], action="quit_app",    radius=8,
                 selected=(sel == 1)),
        ]

    def cancel_confirm_overlay(self):
        """Retour au menu admin depuis une boîte de confirmation (Annuler GPIO)."""
        self._admin_selection = 0
        self._screen_name = "admin"
        settings = self._info.get("settings", {})
        self._build_admin(settings)

    def show_reset_progress(self, message: str = ""):
        self._screen_name = "reset_progress"
        self._buttons = []
        self._info["reset_msg"]  = message
        self._info["reset_done"] = False

    def update_reset_progress(self, message: str, done: bool = False):
        self._info["reset_msg"]  = message
        self._info["reset_done"] = done

    def show_reset_confirm(self):
        """Dialogue de confirmation de remise à zéro."""
        self._screen_name = "reset_confirm"
        self._info["reset_sel"] = 0   # 0 = Annuler (défaut sécurisé), 1 = Confirmer
        self._build_reset_confirm_buttons(0)

    def _build_reset_confirm_buttons(self, sel: int):
        """Construit les boutons Annuler/Confirmer avec la sélection active."""
        lm  = self._lm
        w, h = self._w, self._h
        box_w = min(int(w * 0.88), int(lm.font_md * 22))
        box_h = int(h * 0.52)
        box_x = (w - box_w) // 2
        box_y = h // 2 - box_h // 2
        gap   = max(8, lm.gap_sm)
        half  = (box_w - gap) // 2
        bh    = lm.btn_h
        by    = box_y + box_h - bh - gap * 2
        self._buttons = [
            _Btn((box_x,          by, half, bh), "Annuler",   _GRAY,
                 font=self._fonts["sm"], action="cancel_reset",  radius=8,
                 selected=(sel == 0)),
            _Btn((box_x+half+gap, by, half, bh), "Confirmer", _RED,
                 font=self._fonts["sm"], action="confirm_reset", radius=8,
                 selected=(sel == 1)),
        ]

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def show_admin(self, settings: dict):
        self._screen_name = "admin"
        self._admin_page = "main"
        self._admin_stack = []
        self._admin_scroll = 0
        self._admin_scroll_cache = {}
        self._admin_selection = 0
        self._admin_selection_cache = {}
        self._text_editing = None
        self._info = {"settings": dict(settings)}
        self._build_admin(settings)

    def _build_admin(self, settings: dict):
        """Reconstruit les boutons de la page admin courante."""
        items = self._admin_items(self._admin_page, settings)
        self._info["items"] = items
        self._rebuild_admin_buttons(items, settings)
        # Si la sélection pointe sur un item non-focusable (ex: "info"),
        # snap vers le premier focusable de la page
        focusable = self._admin_focusable(items)
        if focusable and self._admin_selection not in focusable:
            self._admin_selection = focusable[0]

    def update_admin_settings(self, settings: dict):
        """Met à jour les settings et reconstruit la page admin courante (sans reset scroll)."""
        self._info["settings"] = dict(settings)
        self._build_admin(settings)

    def _admin_items(self, page: str, settings: dict) -> list:
        """Retourne la liste des items pour une page admin."""
        tpls = settings.get("_available_templates", [])
        fmt_n = lambda v: f"{v} PHOTO{'S' if v>1 else ''}"
        fmt_s = lambda v: f"{v} sec"
        fmt_on = lambda v: "ACTIVE" if v else "INACTIF"
        fmt_tpl = lambda v: v if v else "—"

        if page == "main":
            return [
                {"type": "nav", "label": "Plugins",             "target": "plugins",
                 "desc": "QR Code · IA · Impression · Upload"},
                {"type": "nav", "label": "Photos / Templates",  "target": "photos",
                 "desc": "Formats · Templates · Titres"},
                {"type": "nav", "label": "Configuration",       "target": "general",
                 "desc": "Nom du photobooth · Délai"},
                {"type": "nav", "label": "GIF animé",            "target": "gif",
                 "desc": "Délai entre photos"},
                {"type": "nav", "label": "Export USB",           "target": "usb",
                 "desc": "Copie des photos sur clé USB"},
                {"type": "nav", "label": "Impression",           "target": "print",
                 "desc": "File d'attente · Vider la file"},
                {"type": "nav", "label": "Diagnostic GPIO",     "target": "gpio",
                 "desc": "Boutons · LEDs · Journal"},
                {"type": "sep"},
                {"type": "action", "label": "Sauvegarder et quitter",  "action": "admin_save",           "color": _GREEN},
                {"type": "action", "label": "Retour à l'accueil",       "action": "admin_cancel",         "color": _GRAY},
                {"type": "action", "label": "Remise à zéro",            "action": "admin_confirm_reset",  "color": _RED},
                {"type": "action", "label": "Quitter l'application",    "action": "admin_confirm_quit",   "color": _RED},
            ]

        if page == "plugins":
            return [
                {"type": "toggle", "label": "QR Code sur résultat",   "key": "qr_on_result",      "fmt": fmt_on},
                {"type": "toggle", "label": "IA remplacement fond",   "key": "ai_enabled",         "fmt": lambda v: "ACTIVEE" if v else "DESACTIVEE"},
                {"type": "toggle", "label": "Impression",             "key": "print_enabled",      "fmt": lambda v: "ACTIVEE" if v else "DESACTIVEE"},
                {"type": "toggle", "label": "Upload cloud",           "key": "cloud_enabled",      "fmt": lambda v: "ACTIVE" if v else "DESACTIVE"},
                {"type": "sep"},
                {"type": "toggle", "label": "Carrousel d'accueil",   "key": "carousel_enabled",   "fmt": fmt_on},
                {"type": "cycle",  "label": "Mode carrousel",         "key": "carousel_mode",
                 "values": ["table", "simple"],
                 "fmt": lambda v: "TABLE" if v == "table" else "SIMPLE"},
                {"type": "cycle",  "label": "Intervalle (sec)",       "key": "carousel_interval",
                 "values": [2, 3, 4, 6, 10],
                 "fmt": lambda v: f"{v} sec"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "photos":
            return [
                {"type": "cycle", "label": "Option A (bouton 1)", "key": "option_a", "values": [1,2,3,4], "fmt": fmt_n},
                {"type": "cycle", "label": "Option B (bouton 2)", "key": "option_b", "values": [1,2,3,4], "fmt": fmt_n},
                {"type": "sep"},
                {"type": "cycle", "label": "Template 1 photo",   "key": "tpl_1", "values": tpls or ["portrait_1photo"], "fmt": fmt_tpl},
                {"type": "cycle", "label": "Template 2 photos",  "key": "tpl_2", "values": tpls or ["portrait_1photo"], "fmt": fmt_tpl},
                {"type": "cycle", "label": "Template 3 photos",  "key": "tpl_3", "values": tpls or ["portrait_1photo"], "fmt": fmt_tpl},
                {"type": "cycle", "label": "Template 4 photos",  "key": "tpl_4", "values": tpls or ["landscape_4photos"], "fmt": fmt_tpl},
                {"type": "sep"},
                {"type": "text",  "label": "Titre",              "key": "event_title",       "wide": True},
                {"type": "cycle", "label": "Taille titre",       "key": "event_title_size",
                 "values": [28, 36, 44, 52, 60, 72, 80, 90, 100, 110, 120, 130, 140, 150, 160],
                 "fmt": lambda v: f"{v} pt"},
                {"type": "text",  "label": "Description",        "key": "event_description", "wide": True},
                {"type": "cycle", "label": "Taille description", "key": "event_desc_size",
                 "values": [12, 16, 20, 24, 28, 36, 44, 52, 60, 69, 80, 90, 100, 110, 120],
                 "fmt": lambda v: f"{v} pt"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "general":
            fmt_px = lambda v: "Auto" if v == 0 else f"{v} px"
            return [
                {"type": "text",  "label": "Nom du photobooth", "key": "booth_name", "wide": True},
                {"type": "cycle", "label": "Taille ligne 1",    "key": "booth_name_size",
                 "values": [0, 24, 32, 40, 48, 56, 64, 72, 80, 96, 112],
                 "fmt": fmt_px},
                {"type": "sep"},
                {"type": "text",  "label": "Deuxième ligne",    "key": "booth_subtitle", "wide": True},
                {"type": "cycle", "label": "Taille ligne 2",    "key": "booth_subtitle_size",
                 "values": [0, 18, 24, 32, 40, 48, 56, 64, 72],
                 "fmt": fmt_px},
                {"type": "sep"},
                {"type": "cycle", "label": "Compte à rebours",  "key": "countdown", "values": [2,3,5,10], "fmt": fmt_s},
                {"type": "sep"},
                {"type": "toggle", "label": "Flash activé",   "key": "flash_enabled", "fmt": fmt_on},
                {"type": "cycle",  "label": "Mode flash",      "key": "flash_mode",
                 "values": ["photo", "continu"],
                 "fmt": lambda v: "PHOTO" if v == "photo" else "CONTINU"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "gif":
            return [
                {"type": "cycle", "label": "Délai entre photos", "key": "gif_delay_s",
                 "values": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                 "fmt": lambda v: f"{v} s"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "usb":
            return [
                {"type": "toggle", "label": "Export USB activé", "key": "usb_enabled",
                 "fmt": fmt_on},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "gpio":
            return [
                {"type": "gpio_info"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "print":
            jobs = settings.get("_print_jobs", [])
            items: list = []
            if jobs:
                for job in jobs[:10]:
                    items.append({"type": "info", "label": job})
            else:
                items.append({"type": "info", "label": "Aucune impression en attente"})
            items += [
                {"type": "sep"},
                {"type": "action", "label": "Vider la file d'impression",
                 "action": "admin_print_cancel_all", "color": _RED},
                {"type": "sep"},
                {"type": "back"},
            ]
            return items

        return [{"type": "back"}]

    @property
    def _admin_margin(self) -> int:
        """Marge admin avec padding visible de chaque côté."""
        return max(28, int(self._w * 0.075))  # ~36px @ 480, ~60px @ 800

    def _rebuild_admin_buttons(self, items: list, settings: dict):
        """Construit la liste de boutons pour les items de la page."""
        margin  = self._admin_margin
        panel_w = self._w - 2 * margin
        val_w   = max(140, int(panel_w * (0.55 if self._is_portrait else 0.45)))
        val_x   = margin + panel_w - val_w

        btns: List[_Btn] = []
        y = HDR_H + 8

        for item_idx, item in enumerate(items):
            itype  = item.get("type")
            is_sel = (item_idx == self._admin_selection) and not self._text_editing

            if itype == "sep":
                y += 12
                continue

            if itype in ("back", "gpio_info", "info"):
                y += ROW_H
                continue

            if itype == "nav":
                btns.append(_NavBtn(
                    (margin, y, panel_w, ROW_H - 4),
                    item["label"], item.get("desc", ""),
                    self._fonts["sm"], self._fonts["xs"],
                    "admin_nav", item["target"],
                ))
                y += ROW_H
                continue

            if itype == "action":
                # Pleine largeur — sélection visible via couleur+bordure blanche
                btns.append(_Btn(
                    (margin, y, panel_w, ROW_H - 4), item["label"], item["color"],
                    font=self._fonts["sm"], action=item["action"], data=None, radius=8,
                    selected=is_sel,
                ))
                y += ROW_H
                continue

            if itype in ("cycle", "toggle"):
                key = item["key"]
                values = item.get("values", [False, True])
                current = settings.get(key, values[0])
                idx = values.index(current) if current in values else 0
                next_val = values[(idx + 1) % len(values)]
                fmt = item.get("fmt", str)
                is_bool = isinstance(current, bool)
                color = (_GREEN if current else _DISABLED) if is_bool else _BLUE
                btns.append(_Btn(
                    (val_x, y + (ROW_H - 36) // 2, val_w, 36),
                    fmt(current), color,
                    font=self._fonts["sm"], action="admin_cycle",
                    data={"key": key, "value": next_val}, radius=6,
                ))
                y += ROW_H
                continue

            if itype == "text":
                key     = item["key"]
                is_wide = item.get("wide", False)
                if is_wide:
                    # Champ pleine largeur sur 2 lignes :
                    # ligne 1 = label, ligne 2 = champ de saisie
                    field_h = ROW_H + 8
                    btns.append(_Btn(
                        (margin, y + ROW_H, panel_w, field_h), "",
                        _PANEL, action="admin_text_activate", data=key, radius=6,
                        no_draw=True,
                    ))
                    y += ROW_H + field_h + 6   # 2 lignes + espacement
                else:
                    btns.append(_Btn(
                        (val_x, y + (ROW_H - 36) // 2, val_w, 36), "",
                        _PANEL, action="admin_text_activate", data=key, radius=6,
                        no_draw=True,
                    ))
                    y += ROW_H
                continue

            y += ROW_H

        # Bouton ← Retour fixe en bas — largeur proportionnelle à l'écran
        if self._admin_page != "main":
            lm      = self._lm
            back_w  = max(180, int(self._w * 0.42))   # 42% largeur, min 180px
            back_h  = max(44, lm.btn_h - 6)           # hauteur correcte
            back_x  = margin
            back_y  = self._h - back_h - max(8, lm.gap_sm)
            back    = _Btn(
                (back_x, back_y, back_w, back_h),
                "<  Retour", _PANEL,
                font=self._fonts["sm"], action="admin_back_btn", radius=8,
            )
            back.fixed = True
            btns.append(back)

        self._buttons = btns

    def _admin_max_scroll(self) -> int:
        """Scroll maximum : contenu s'arrête avant le bouton fixe du bas."""
        items        = self._info.get("items", [])
        content_h    = self._admin_content_height(items)
        bottom_res   = self._admin_bottom_reserved()
        scrollable_h = self._h - HDR_H - bottom_res
        return max(0, content_h - scrollable_h)

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def _to_logical(self, real_x: int, real_y: int):
        """Convertit coordonnées écran réel → canvas logique."""
        if self._scale <= 0:
            return real_x, real_y
        lx = int((real_x - self._offset_x) / self._scale)
        ly = int((real_y - self._offset_y) / self._scale)
        return (max(0, min(lx, self._w - 1)), max(0, min(ly, self._h - 1)))

    def run(self):
        self._running = True
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    continue

                # Toute interaction utilisateur → reset timer d'inactivité
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    self._notify_activity()

                # Convertir les coordonnées souris/touch vers le canvas logique
                # (nécessaire quand scale != 1.0, i.e. Pi fullscreen)
                if hasattr(event, 'pos') and self._scale != 1.0:
                    lx, ly = self._to_logical(*event.pos)
                    event  = pygame.event.Event(event.type,
                                                {**event.__dict__, 'pos': (lx, ly)})

                if event.type == pygame.KEYDOWN:
                    if self._screen_name == "admin":
                        if self._handle_admin_key(event):
                            continue
                    elif self._screen_name == "confirm_quit":
                        if self._handle_confirm_quit_key(event):
                            continue
                    elif self._screen_name == "reset_confirm":
                        if self._handle_reset_confirm_key(event):
                            continue
                    self._on_key(event)
                    continue

                if event.type == pygame.MOUSEWHEEL and self._screen_name == "admin":
                    delta = -event.y * 18
                    max_s = self._admin_max_scroll()
                    self._admin_scroll = max(0, min(self._admin_scroll + delta, max_s))
                    continue

                # Admin : séparer boutons fixes (pos absolue) et scrollables
                pos = getattr(event, "pos", None)
                if pos and self._screen_name == "admin":
                    translated = (pos[0], pos[1] + self._admin_scroll)
                    fake = pygame.event.Event(event.type, {**event.__dict__, "pos": translated})
                    self._handle_buttons(event, fake)   # event=original pour fixed, fake pour scrollé
                else:
                    self._handle_buttons(event)

            self._render()
            self._clock.tick(self._fps)
        pygame.mouse.set_visible(True)
        pygame.quit()

    def _handle_buttons(self, event, scrolled_event=None):
        """
        scrolled_event : événement avec position translatee par scroll (admin uniquement).
        Les boutons fixes (back, save, cancel) utilisent event (position absolue).
        Les autres utilisent scrolled_event.
        """
        for btn in list(self._buttons):
            ev = event if btn.fixed else (scrolled_event or event)
            r = btn.handle(ev)
            if not r:
                continue
            action, data = r
            settings = self._info.get("settings", {})

            if action == "admin_nav":
                self._admin_navigate_to(data, settings)

            elif action == "admin_back_btn":
                self._admin_go_back(settings)

            elif action == "admin_cycle":
                key, val = data["key"], data["value"]
                settings[key] = val
                self._info["settings"] = settings
                self._build_admin(settings)

            elif action == "admin_text_activate":
                self._text_editing = data
                self._build_admin(settings)

            elif action == "admin_save":
                self._emit("admin_save", dict(settings))

            elif action == "admin_cancel":
                self._emit("admin_cancel")

            elif action == "admin_confirm_reset":
                self.show_reset_confirm()

            elif action == "cancel_reset":
                self._admin_selection = 0
                self._screen_name = "admin"
                self._build_admin(settings)

            elif action == "admin_confirm_quit":
                # Affiche la boîte de confirmation sans quitter immédiatement
                self.show_confirm_quit()

            elif action == "quit_app":
                self._emit("quit_app")

            elif action == "cancel_quit":
                # Reset sélection → évite que le bouton Quitter reste "rose" (selected+60)
                self._admin_selection = 0
                self._screen_name = "admin"
                self._build_admin(settings)

            else:
                self._emit(action, data)
            break

    def _handle_admin_key(self, event) -> bool:
        """Navigation clavier dans le menu admin — logique centralisée."""
        settings = self._info.get("settings", {})
        items    = self._info.get("items", [])

        # Mode saisie texte — consomme TOUTES les touches
        if self._text_editing:
            cur = str(settings.get(self._text_editing, ""))
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self._text_editing = None
                self._build_admin(settings)
            elif event.key == pygame.K_BACKSPACE:
                settings[self._text_editing] = cur[:-1]
                self._info["settings"] = settings
                self._build_admin(settings)
            elif event.unicode and event.unicode.isprintable() and len(cur) < 60:
                settings[self._text_editing] = cur + event.unicode
                self._info["settings"] = settings
                self._build_admin(settings)
            return True

        focusable = self._admin_focusable(items)
        if not focusable:
            if event.key == pygame.K_ESCAPE:
                self._admin_go_back(settings)
            return True

        sel = self._admin_selection if self._admin_selection in focusable else focusable[0]
        pos = focusable.index(sel)

        # Navigation verticale — CLAMPAGE (pas de wrap)
        if event.key == pygame.K_DOWN:
            new_pos = min(pos + 1, len(focusable) - 1)  # ne dépasse jamais le dernier
            self._admin_selection = focusable[new_pos]
            self._scroll_to_selection(items)
            return True

        if event.key == pygame.K_UP:
            new_pos = max(pos - 1, 0)  # ne remonte jamais avant le premier
            self._admin_selection = focusable[new_pos]
            self._scroll_to_selection(items)
            return True

        if event.key == pygame.K_ESCAPE:
            self._admin_go_back(settings)
            return True

        item  = items[sel]
        itype = item.get("type")

        if event.key == pygame.K_LEFT:
            if itype in ("cycle", "toggle"):
                self._admin_cycle_item(item, settings, -1)
            else:
                self._admin_go_back(settings)
            return True

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_RIGHT):
            if itype == "nav":
                self._admin_navigate_to(item["target"], settings)
            elif itype in ("cycle", "toggle"):
                self._admin_cycle_item(item, settings, +1)
            elif itype == "text":
                self._text_editing = item["key"]
                self._build_admin(settings)
            elif itype == "action":
                act = item.get("action")
                if act == "admin_save":
                    self._emit("admin_save", dict(settings))
                elif act == "admin_cancel":
                    self._emit("admin_cancel")
                elif act == "admin_confirm_reset":
                    self.show_reset_confirm()
                elif act == "admin_confirm_quit":
                    self.show_confirm_quit()
                else:
                    self._emit(act)
            elif itype == "back":
                self._admin_go_back(settings)
            return True

        return True

    # ------------------------------------------------------------------
    # Helpers navigation admin
    # ------------------------------------------------------------------

    @staticmethod
    def _admin_focusable(items: list) -> list:
        """Indices des items navigables (exclut sep et gpio_info)."""
        return [i for i, it in enumerate(items)
                if it.get("type") not in ("sep", "gpio_info", "info")]

    def _admin_navigate_to(self, target: str, settings: dict):
        """Navigation FORWARD vers un sous-menu. Toujours reset à 0 (pas de restauration)."""
        # Sauvegarder position actuelle (pour le BACK)
        self._admin_selection_cache[self._admin_page] = self._admin_selection
        self._admin_scroll_cache[self._admin_page]    = self._admin_scroll
        self._admin_stack.append(self._admin_page)
        self._admin_page = target
        # Toujours partir du début (reset — pas de restauration de cache)
        self._admin_scroll    = 0
        self._admin_selection = 0
        self._text_editing    = None
        self._build_admin(settings)

    def _admin_go_back(self, settings: dict):
        """Navigation BACK — restaure la position de la page parente."""
        if self._admin_stack:
            self._admin_selection_cache[self._admin_page] = self._admin_selection
            self._admin_scroll_cache[self._admin_page]    = self._admin_scroll
            prev = self._admin_stack.pop()
            self._admin_page      = prev
            self._admin_scroll    = self._admin_scroll_cache.get(prev, 0)
            self._admin_selection = self._admin_selection_cache.get(prev, 0)
            self._text_editing    = None
            self._build_admin(settings)
        else:
            self._emit("admin_cancel")

    def _admin_cycle_item(self, item: dict, settings: dict, direction: int = 1):
        """Cycle la valeur d'un item (+1 ou -1)."""
        key    = item["key"]
        values = item.get("values", [False, True])
        cur    = settings.get(key, values[0])
        idx    = values.index(cur) if cur in values else 0
        settings[key] = values[(idx + direction) % len(values)]
        self._info["settings"] = settings
        self._build_admin(settings)

    @staticmethod
    def _item_height(item: dict) -> int:
        """Hauteur en pixels d'un item admin."""
        itype = item.get("type")
        if itype == "sep":
            return 12
        if itype == "text" and item.get("wide", False):
            return ROW_H + (ROW_H + 8) + 6   # label + champ + gap
        return ROW_H

    def _admin_content_height(self, items: list) -> int:
        """Hauteur totale du contenu scrollable pour une liste d'items."""
        settings = self._info.get("settings", {})
        h = 8
        for item in items:
            itype = item.get("type")
            if itype == "gpio_info":
                gpio_cfg = settings.get("_gpio_config", {})
                gpio_log = settings.get("_gpio_log", [])
                h += ROW_H * (len(gpio_cfg) + 2) + min(len(gpio_log), 6) * 26
            else:
                h += self._item_height(item)
        return h

    def _admin_bottom_reserved(self) -> int:
        """Hauteur réservée en bas pour le bouton fixe (non-main pages)."""
        return BTN_H + 8 if self._admin_page != "main" else 0

    def _scroll_to_selection(self, items: list):
        """Scroll pour garder l'item sélectionné visible dans la zone scrollable."""
        settings = self._info.get("settings", {})
        y = HDR_H + 8
        for i, item in enumerate(items):
            if i == self._admin_selection:
                break
            itype = item.get("type")
            if itype == "gpio_info":
                gpio_cfg = settings.get("_gpio_config", {})
                gpio_log = settings.get("_gpio_log", [])
                y += ROW_H * (len(gpio_cfg) + 2) + min(len(gpio_log), 6) * 26
            else:
                y += self._item_height(item)

        bottom_reserved = self._admin_bottom_reserved()
        visible_bottom  = self._h - bottom_reserved
        if y - self._admin_scroll < HDR_H + 4:
            self._admin_scroll = max(0, y - HDR_H - 8)
        elif y - self._admin_scroll + ROW_H > visible_bottom:
            self._admin_scroll = y + ROW_H - visible_bottom
        self._admin_scroll = max(0, min(self._admin_scroll, self._admin_max_scroll()))

    def stop(self):
        self._running = False

    def _handle_reset_confirm_key(self, event) -> bool:
        """Navigation Left/Right entre Annuler et Confirmer. Enter = valider la sélection."""
        sel = self._info.get("reset_sel", 0)

        if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
            new_sel = 1 - sel
            self._info["reset_sel"] = new_sel
            self._build_reset_confirm_buttons(new_sel)
            return True

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if sel == 1:   # Confirmer sélectionné
                self._emit("confirm_reset")
            else:          # Annuler sélectionné
                self._admin_selection = 0
                settings = self._info.get("settings", {})
                self._screen_name = "admin"
                self._build_admin(settings)
            return True

        if event.key == pygame.K_ESCAPE:
            self._admin_selection = 0
            settings = self._info.get("settings", {})
            self._screen_name = "admin"
            self._build_admin(settings)
            return True

        return True

    def _handle_confirm_quit_key(self, event) -> bool:
        """Navigation Left/Right entre Annuler et Confirmer. Enter = valider la sélection."""
        sel = self._info.get("quit_sel", 0)

        if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
            new_sel = 1 - sel
            self._info["quit_sel"] = new_sel
            self._build_confirm_quit_buttons(new_sel)
            return True

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if sel == 1:   # Confirmer sélectionné
                self._emit("quit_app")
            else:          # Annuler sélectionné
                self.cancel_confirm_overlay()
            return True

        if event.key == pygame.K_ESCAPE:
            self.cancel_confirm_overlay()
            return True

        return True   # consomme toutes les touches en mode confirmation

    def _on_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self._screen_name == "confirm_quit":
                # ESC annule la confirmation de fermeture
                settings = self._info.get("settings", {})
                self._screen_name = "admin"
                self._build_admin(settings)
            else:
                self._emit("open_admin")
        elif event.key == pygame.K_SPACE:
            if self._screen_name == "idle":
                self._emit("open_choose_type")
            elif self._screen_name == "choose_type":
                self._emit("open_choose_format")   # Photo par défaut
            elif self._screen_name == "choose_format":
                self._emit("back_to_choose_type")
            elif self._screen_name == "choose_gif_orientation":
                self._emit("back_to_choose_type")
            elif self._screen_name == "preview":
                self._emit("start_countdown")

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self):
        dispatch = {
            "idle":          self._r_idle,
            "choose_type":   self._r_choose_type,
            "choose_format": self._r_choose,
            "choose_gif_orientation": self._r_choose_gif_orientation,
            "preview":       self._r_preview,
            "processing":    self._r_processing,
            "review":        self._r_review,
            "qr":            self._r_qr,
            "error":         self._r_error,
            "usb_export":    self._r_usb_export,
            "admin":         self._r_admin,
            "confirm_quit":  self._r_confirm_quit,
            "reset_confirm":   self._r_reset_confirm,
            "reset_progress":  self._r_reset_progress,
        }
        # 1. Rendu sur le canvas logique (self._screen = 480×800 toujours)
        dispatch.get(self._screen_name, lambda: self._screen.fill(_DARK))()
        for btn in self._buttons:
            if self._screen_name == "admin":
                if btn.fixed:
                    btn.draw(self._screen)
                else:
                    real_rect = btn.rect.move(0, -self._admin_scroll)
                    if real_rect.bottom <= HDR_H or real_rect.top >= self._h:
                        continue
                    orig      = btn.rect
                    btn.rect  = real_rect
                    btn.draw(self._screen)
                    btn.rect  = orig
            else:
                btn.draw(self._screen)

        # self._screen == self._display → rendu direct, pas de scaling
        pygame.display.flip()

    def _r_idle(self):
        """Écran d'accueil — toutes les positions via LayoutManager."""
        self._screen.fill(_DARK)
        lm           = self._lm
        name         = self._info.get("booth_name", "SnapForge")
        has_carousel = self._carousel.enabled and self._carousel.has_photos()

        # --- Positions proportionnelles depuis LayoutManager ---
        title_y    = lm.px(lm.idle_title_y)
        subtitle_y = lm.px(lm.idle_subtitle_y)
        btn_cy     = lm.px(lm.idle_btn_y)

        # --- Ligne 1 : nom du photobooth ---
        name_size = self._info.get("booth_name_size", 0)
        font1 = (self._font_at_size(name_size) if name_size > 0
                 else self._best_font_for(name, self._w - lm.margin * 2))
        ts1 = font1.render(name, True, _WHITE)
        self._screen.blit(ts1, ts1.get_rect(center=(self._w // 2, title_y)))

        # --- Ligne 2 : deuxième ligne configurable (optionnelle, juste sous ligne 1) ---
        sub_text = self._info.get("booth_subtitle", "")
        if sub_text:
            sub_size = self._info.get("booth_subtitle_size", 0)
            font2 = (self._font_at_size(sub_size) if sub_size > 0
                     else self._fonts["md"])
            ts2 = font2.render(sub_text, True, _LGRAY)
            line2_y = title_y + ts1.get_height() // 2 + max(6, lm.gap_sm) + ts2.get_height() // 2
            self._screen.blit(ts2, ts2.get_rect(center=(self._w // 2, line2_y)))

        # --- "Bienvenue !" toujours présent ---
        self._txt("Bienvenue !", "md", _GRAY, self._w // 2, subtitle_y, cx=True)

        # --- Zone carrousel bornée au-dessus du bouton ---
        btn_h_est   = lm.btn_h
        btn_top     = btn_cy - btn_h_est // 2
        safe_margin = max(16, int(self._h * 0.03))

        zone_x   = lm.margin
        zone_w   = self._w - lm.margin * 2
        zone_y   = subtitle_y + lm.gap_md + lm.gap_sm
        zone_bot = btn_top - safe_margin
        # Utiliser TOUT l'espace disponible entre sous-titre et bouton
        # (plus de cap arbitraire — zone aussi grande que possible)
        zone_h   = max(60, zone_bot - zone_y)

        if has_carousel and zone_h >= 60:
            self._carousel.update()
            shadow_off = lm.carousel_shadow_offset
            items = self._carousel.get_render_items(
                zone_x, zone_y, zone_w, zone_h, self._is_portrait
            )
            for _ph, shadow, x, y in items:
                self._screen.blit(shadow, (x + shadow_off, y + shadow_off))
            for photo, _sh, x, y in items:
                self._screen.blit(photo, (x, y))
        else:
            # Animation points (aucune photo encore)
            t      = int(time.time() * 2) % 3
            dy     = zone_y + zone_h // 2
            dot_r  = max(5, int(lm.font_xs * 0.35))
            dot_sp = dot_r * 3
            for i in range(3):
                pygame.draw.circle(self._screen, _ACCENT if i == t else _GRAY,
                                   (self._w // 2 - dot_sp + i * dot_sp, dy), dot_r)

    def _r_choose_type(self):
        """Niveau 1 : Photo ou GIF ?"""
        self._screen.fill(_DARK)
        self._txt_fit("Quel type de souvenir ?", _WHITE,
                      self._w // 2, int(self._h * 0.12), max_w=self._w - 20, cx=True)
        hint = "BTN 1 = Photo   |   BTN 2 = GIF" if not self._is_portrait else ""
        if hint:
            self._txt_fit(hint, _GRAY, self._w // 2, int(self._h * 0.92),
                          max_w=self._w - 20, cx=True)

    def _r_choose(self):
        self._screen.fill(_DARK)
        # Titre : 10 % depuis le haut (pas collé au bord)
        title_y = max(40, int(self._h * 0.10))
        self._txt_fit("Combien de photos ?", _WHITE, self._w // 2, title_y,
                      max_w=self._w - 20, cx=True)
        # Hint : 92 % de la hauteur (pas collé au bas)
        hint_y = int(self._h * 0.92)
        hint = "Appuyez pour commencer" if self._is_portrait else "Appuyez sur votre choix pour commencer"
        self._txt_fit(hint, _GRAY, self._w // 2, hint_y,
                      max_w=self._w - 20, cx=True)

    def _r_choose_gif_orientation(self):
        """Niveau 3 GIF : Portrait ou Paysage ?"""
        self._screen.fill(_DARK)
        self._txt_fit("GIF ANIMÉ", _WHITE,
                      self._w // 2, int(self._h * 0.12), max_w=self._w - 20, cx=True)
        hint = "BTN 1 = Portrait   |   BTN 2 = Paysage" if not self._is_portrait else ""
        if hint:
            self._txt_fit(hint, _GRAY, self._w // 2, int(self._h * 0.92),
                          max_w=self._w - 20, cx=True)

    def _preview_box(self, slot_ar):
        """Calcule (box_x, box_y, box_w, box_h) pour la boîte preview centrée.

        La boîte est contenue dans l'espace entre l'en-tête et le bouton CAPTURER,
        avec des marges latérales.  Son ratio est celui du slot template (slot_ar).
        """
        lm      = self._lm
        TOP     = 44                           # espace en-tête pour le compteur
        SIDE    = 16                           # marge latérale
        btn_top = self._h - lm.btn_h - lm.gap_md
        avail_w = self._w - 2 * SIDE
        avail_h = btn_top - lm.gap_md - TOP   # hauteur libre entre header et bouton

        ar = slot_ar if (slot_ar and slot_ar > 0) else (avail_w / max(avail_h, 1))

        if avail_w / max(avail_h, 1) >= ar:   # limité par la hauteur disponible
            box_h = avail_h
            box_w = int(box_h * ar)
        else:                                  # limité par la largeur disponible
            box_w = avail_w
            box_h = int(box_w / ar)

        box_x = (self._w - box_w) // 2
        box_y = TOP + (avail_h - box_h) // 2
        return box_x, box_y, box_w, box_h

    def _r_preview(self):
        # Fond sombre — la preview est contenue dans une boîte, pas en plein écran
        self._screen.fill(_DARK)

        slot_ar = self._info.get("slot_ar")
        box_x, box_y, box_w, box_h = self._preview_box(slot_ar)

        # Rendu de la frame caméra dans la boîte
        with self._preview_lock:
            frame = self._preview_frame
        if frame is not None:
            try:
                surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                # Appliquer le même center-crop que _fit_crop dans composer :
                # on extrait la région centrale qui correspond au slot final.
                if slot_ar and slot_ar > 0:
                    sw, sh = surf.get_size()
                    src_r = sw / max(sh, 1)
                    if src_r > slot_ar:
                        # Frame plus large que le slot : crop latéral
                        _ch = sh
                        _cw = int(sh * slot_ar)
                        _cx = (sw - _cw) // 2
                        _cy = 0
                    else:
                        # Frame plus haute que le slot : crop vertical
                        _cw = sw
                        _ch = int(sw / slot_ar)
                        _cx = 0
                        _cy = (sh - _ch) // 2
                    if _cw > 0 and _ch > 0 and _cw <= sw and _ch <= sh:
                        surf = surf.subsurface((_cx, _cy, _cw, _ch))
                surf = pygame.transform.scale(surf, (box_w, box_h))
                self._screen.blit(surf, (box_x, box_y))
            except Exception:
                pass

        # Cadre de délimitation de la zone active
        pygame.draw.rect(self._screen, (160, 160, 160), (box_x, box_y, box_w, box_h), 1)

        # Compteur de photos (en-tête, hors boîte)
        remaining = self._info.get("remaining", 0)
        total     = self._info.get("total", 0)
        self._shadow_txt(f"{total - remaining}/{total}", "sm", _WHITE, 14, 14)

        # Souriez / compte à rebours — jamais les deux en même temps
        box_cx  = box_x + box_w // 2
        box_cy  = box_y + box_h // 2
        cd    = self._info.get("countdown", 0)
        smile = self._info.get("smile", False)
        if cd > 0:
            # Chiffre au centre (identique pour 1 photo, 4 photos et GIF)
            self._shadow_txt(str(cd), "xxl", _WHITE, box_cx, box_cy, cx=True)
        elif smile:
            # "Souriez !" en haut de la boîte quand décompte terminé
            smile_y = box_y + max(40, box_h // 8)
            self._shadow_txt("Souriez !", "xl", _ACCENT, box_cx, smile_y, cx=True)

    def _r_processing(self):
        self._screen.fill(_DARK)
        self._txt("Traitement...", "lg", _WHITE, self._w // 2, self._h // 3, cx=True)
        self._txt(self._info.get("step", ""), "sm", _ACCENT, self._w // 2, self._h // 2, cx=True)
        bw, bx = 400, (self._w - 400) // 2
        by = self._h * 2 // 3
        pygame.draw.rect(self._screen, _DARK2, (bx, by, bw, 10), border_radius=5)
        fill = max(0, min(int((time.time() * 80) % (bw + 60)) - 30, bw))
        if fill > 0:
            pygame.draw.rect(self._screen, _ACCENT, (bx, by, fill, 10), border_radius=5)

    def _r_review(self):
        self._screen.fill(_BLACK)
        lm     = self._lm
        status = self._info.get("status")
        m      = 20
        bh     = max(80, lm.btn_h)

        # Zone disponible pour la photo (réduite quand les boutons sont visibles)
        reserved = (bh + m * 2) if not status else 0
        photo = self._info.get("photo")
        if photo and Path(photo).exists():
            try:
                img = pygame.image.load(photo)
                iw, ih = img.get_size()
                scale = min((self._w - 40) / iw, (self._h - reserved - 30) / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = pygame.transform.scale(img, (nw, nh))
                self._screen.blit(img, ((self._w - nw) // 2, 15))
            except Exception as e:
                logger.error(f"Review: {e}")

        if status:
            # Bandeaux de statut centré, en premier plan, sur fond semi-transparent
            is_error = "erreur" in status.lower() or "error" in status.lower()
            color    = _RED if is_error else _GREEN
            bw       = self._w - 2 * m
            bh_msg   = int(lm.font_lg * 2.2)
            bx       = m
            by       = self._h // 2 - bh_msg // 2
            overlay  = pygame.Surface((bw, bh_msg), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            self._screen.blit(overlay, (bx, by))
            pygame.draw.rect(self._screen, color, (bx, by, bw, bh_msg), 3, border_radius=10)
            self._txt_fit(status, color, self._w // 2, by + bh_msg // 2,
                          max_w=bw - 20, cx=True)

    def _get_gif_current_frame(self):
        """Retourne la frame courante du GIF animé et avance si nécessaire."""
        frames = self._info.get("gif_frames")
        if not frames:
            return None
        durs = self._info.get("gif_durations") or [0.18] * len(frames)
        idx  = self._info.get("gif_frame_idx", 0) % len(frames)
        t    = self._info.get("gif_frame_t", time.time())
        now  = time.time()
        if now - t >= durs[idx % len(durs)]:
            idx = (idx + 1) % len(frames)
            self._info["gif_frame_idx"] = idx
            self._info["gif_frame_t"]   = now
        return frames[idx]

    def _r_qr(self):
        """
        Mode GIF  : [ GIF animé centré ] [ QR ] [ Scannez ] [ Retour ]
        Mode Photo : [ Photo ] [ QR ] [ Scannez ] [ Retour ]

        Paysage : photo gauche, QR droite.
        """
        self._screen.fill(_DARK)
        photo    = self._info.get("photo")
        qr       = self._info.get("qr")
        gif_path = self._info.get("gif_path")
        lm       = self._lm
        is_gif   = bool(gif_path)

        btn_cy  = self._h - lm.btn_h // 2 - lm.gap_md
        btn_top = btn_cy - lm.btn_h // 2
        gap     = max(6, lm.gap_sm)

        if self._is_portrait:
            # -- Calcul bottom-up --
            text_h  = lm.font_xs + 2
            text_cy = btn_top - gap - text_h // 2

            qr_sz   = max(80, int(self._w * 0.24))
            qr_bot  = btn_top - gap - text_h - gap
            qr_y    = qr_bot - qr_sz
            qx      = (self._w - qr_sz) // 2

            # 3. Contenu principal (GIF animé OU photo fixe)
            photo_max_h = qr_y - gap * 2
            photo_max_w = self._w - gap * 2

            if is_gif:
                # GIF animé : afficher la frame courante
                frame = self._get_gif_current_frame()
                if frame:
                    iw, ih = frame.get_size()
                    scale = min(photo_max_w / iw, photo_max_h / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    if nw != iw:
                        frame = pygame.transform.scale(frame, (nw, nh))
                    px = (self._w - nw) // 2
                    py = gap + max(0, (photo_max_h - nh) // 2)
                    self._screen.blit(frame, (px, py))
                else:
                    # GIF pas encore chargé → texte d'attente
                    self._txt("Chargement GIF...", "sm", _GRAY,
                               self._w // 2, gap + photo_max_h // 2, cx=True)
            elif photo and Path(photo).exists():
                try:
                    img = pygame.image.load(photo)
                    iw, ih = img.get_size()
                    scale = min(photo_max_w / iw, photo_max_h / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    img = pygame.transform.scale(img, (nw, nh))
                    px  = (self._w - nw) // 2
                    py  = gap + max(0, (photo_max_h - nh) // 2)
                    self._screen.blit(img, (px, py))
                except Exception as e:
                    logger.error(f"QR photo: {e}")

            # 4. QR code
            if qr is not None:
                try:
                    pil   = qr.convert("RGB")
                    qsurf = pygame.image.fromstring(pil.tobytes(), pil.size, "RGB")
                    qsurf = pygame.transform.smoothscale(qsurf, (qr_sz, qr_sz))
                    bg    = pygame.Surface((qr_sz + 6, qr_sz + 6))
                    bg.fill(_WHITE); bg.set_alpha(240)
                    self._screen.blit(bg,    (qx - 3, qr_y - 3))
                    self._screen.blit(qsurf, (qx,     qr_y))
                    # Texte entre QR et bouton
                    self._txt("Scannez pour télécharger", "xs", _LGRAY,
                               self._w // 2, text_cy, cx=True)
                except Exception as e:
                    logger.error(f"QR: {e}")
            else:
                self._txt("Photo enregistrée !", "sm", _LGRAY,
                           self._w // 2, qr_y + qr_sz // 2, cx=True)

        else:
            # ----- PAYSAGE : photo gauche, QR droite -----
            half = avail_w // 2
            photo_rect = None
            if photo and Path(photo).exists():
                try:
                    img = pygame.image.load(photo)
                    iw, ih = img.get_size()
                    scale = min((half - 15) / iw, (avail_h - 20) / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    img = pygame.transform.scale(img, (nw, nh))
                    px  = (half - nw) // 2
                    py  = (avail_h - nh) // 2
                    self._screen.blit(img, (px, py))
                    photo_rect = pygame.Rect(px, py, nw, nh)
                except Exception:
                    pass

            if qr is not None:
                try:
                    pil   = qr.convert("RGB")
                    qr_sz = max(60, min(avail_h - 50, half - 20))
                    qsurf = pygame.image.fromstring(pil.tobytes(), pil.size, "RGB")
                    qsurf = pygame.transform.smoothscale(qsurf, (qr_sz, qr_sz))
                    qx    = half + (half - qr_sz) // 2
                    qy    = (avail_h - qr_sz) // 2 - 15
                    bg    = pygame.Surface((qr_sz + 6, qr_sz + 6))
                    bg.fill(_WHITE); bg.set_alpha(240)
                    self._screen.blit(bg, (qx - 3, qy - 3))
                    self._screen.blit(qsurf, (qx, qy))
                    self._txt("Scannez pour", "xs", _LGRAY,
                              qx + qr_sz // 2, qy + qr_sz + 6, cx=True)
                    self._txt("télécharger", "xs", _LGRAY,
                              qx + qr_sz // 2, qy + qr_sz + 21, cx=True)
                except Exception as e:
                    logger.error(f"QR landscape: {e}")
            elif photo_rect is None:
                self._txt("Photo enregistrée !", "md", _LGRAY,
                          avail_w * 3//4, avail_h // 2, cx=True)

    def _r_error(self):
        self._screen.fill((50, 15, 15))
        self._txt("ERREUR", "xl", _RED, self._w // 2, self._h // 3, cx=True)
        self._txt(str(self._info.get("msg", ""))[:70], "xs", _LGRAY, self._w // 2, self._h // 2, cx=True)
        self._txt("Retour automatique...", "xs", _GRAY, self._w // 2, self._h * 2 // 3, cx=True)

    def _r_usb_export(self):
        self._screen.fill(_DARK)
        lm       = self._lm
        cx       = self._w // 2
        done     = self._info.get("usb_done", False)
        success  = self._info.get("usb_success", True)
        status   = self._info.get("usb_status", "")
        subtitle = self._info.get("usb_subtitle", "")

        # Titre
        self._txt("Export USB", "xl", _WHITE, cx, int(self._h * 0.20), cx=True)

        # Ligne décorative
        line_y = int(self._h * 0.30)
        bar_w  = min(int(self._w * 0.55), 320)
        pygame.draw.line(self._screen, _ACCENT,
                         (cx - bar_w // 2, line_y), (cx + bar_w // 2, line_y), 2)

        # Message de statut principal
        status_y = int(self._h * 0.48)
        color    = (_GREEN if success else _RED) if done else _LGRAY
        self._txt_fit(status, color, cx, status_y,
                      max_w=self._w - lm.margin * 2, cx=True)

        # Sous-titre (ex: "42 fichiers copiés")
        if subtitle:
            self._txt_fit(subtitle, _GRAY, cx, int(self._h * 0.58),
                          max_w=self._w - lm.margin * 2, cx=True)

        if done:
            self._txt("Retour automatique...", "xs", _GRAY, cx, int(self._h * 0.72), cx=True)
        else:
            # Animation 3 points
            t      = int(time.time() * 2) % 3
            dot_r  = max(5, int(lm.font_xs * 0.35))
            dot_sp = dot_r * 3
            dy     = int(self._h * 0.68)
            for i in range(3):
                pygame.draw.circle(self._screen,
                                   _ACCENT if i == t else _GRAY,
                                   (cx - dot_sp + i * dot_sp, dy), dot_r)

    def _r_confirm_quit(self):
        """Dialogue de confirmation — layout unifié avec show_confirm_quit."""
        self._screen.fill(_DARK)
        lm = self._lm
        box_x, box_y, box_w, box_h, *_ = \
            self._confirm_quit_geometry(self._w, self._h, lm)
        radius = max(10, int(lm.font_xs * 0.7))

        # Boîte
        pygame.draw.rect(self._screen, _DARK2, (box_x, box_y, box_w, box_h), border_radius=radius)
        pygame.draw.rect(self._screen, _RED,   (box_x, box_y, box_w, box_h), 2, border_radius=radius)

        cx = self._w // 2
        self._txt_fit("Voulez-vous vraiment quitter SnapForge ?", _WHITE, cx,
                      box_y + int(box_h * 0.22), max_w=box_w - 20, cx=True)
        self._txt_fit("L'application va se fermer.", _GRAY, cx,
                      box_y + int(box_h * 0.42), max_w=box_w - 20, cx=True)

    def _r_reset_confirm(self):
        """Dialogue de confirmation de remise à zéro."""
        self._screen.fill(_DARK)
        lm  = self._lm
        w, h = self._w, self._h
        box_w = min(int(w * 0.88), int(lm.font_md * 22))
        box_h = int(h * 0.52)
        box_x = (w - box_w) // 2
        box_y = h // 2 - box_h // 2
        radius = max(10, int(lm.font_xs * 0.7))
        cx = w // 2

        pygame.draw.rect(self._screen, _DARK2, (box_x, box_y, box_w, box_h), border_radius=radius)
        pygame.draw.rect(self._screen, _RED,   (box_x, box_y, box_w, box_h), 2, border_radius=radius)

        self._txt_fit("Remise à zéro",
                      _RED,   cx, box_y + int(box_h * 0.12), max_w=box_w - 20, cx=True)
        self._txt_fit("Cette action supprime TOUTES les photos",
                      _WHITE, cx, box_y + int(box_h * 0.28), max_w=box_w - 24, cx=True)
        self._txt_fit("et GIF de l'événement actuel.",
                      _WHITE, cx, box_y + int(box_h * 0.38), max_w=box_w - 24, cx=True)
        self._txt_fit("Assurez-vous d'avoir fait un export USB.",
                      _GRAY,  cx, box_y + int(box_h * 0.50), max_w=box_w - 24, cx=True)
        self._txt_fit("Entree = confirmer     Echap = annuler",
                      _DISABLED, cx, box_y + int(box_h * 0.63), max_w=box_w - 24, cx=True)

    # ------------------------------------------------------------------
    def _r_reset_progress(self):
        """Écran affiché pendant et après la remise à zéro."""
        self._screen.fill(_DARK)
        lm   = self._lm
        cx   = self._w // 2
        msg  = self._info.get("reset_msg", "")
        done = self._info.get("reset_done", False)

        self._txt("Remise à zéro", "xl", _WHITE, cx, int(self._h * 0.22), cx=True)

        bar_w = min(int(self._w * 0.55), 320)
        line_y = int(self._h * 0.32)
        pygame.draw.line(self._screen, _RED,
                         (cx - bar_w // 2, line_y), (cx + bar_w // 2, line_y), 2)

        color = _GREEN if done else _LGRAY
        self._txt_fit(msg, color, cx, int(self._h * 0.50),
                      max_w=self._w - lm.margin * 2, cx=True)

        if done:
            self._txt("Retour à l'accueil...", "xs", _GRAY, cx, int(self._h * 0.65), cx=True)
        else:
            t     = int(time.time() * 2) % 3
            dot_r = max(5, int(lm.font_xs * 0.35))
            dot_sp = dot_r * 3
            dy    = int(self._h * 0.65)
            for i in range(3):
                pygame.draw.circle(self._screen,
                                   _RED if i == t else _GRAY,
                                   (cx - dot_sp + i * dot_sp, dy), dot_r)

    # Rendu admin
    # ------------------------------------------------------------------

    def _r_admin(self):
        self._screen.fill(_DARK)
        settings = self._info.get("settings", {})
        items    = self._info.get("items", [])
        scroll   = self._admin_scroll
        margin   = self._admin_margin                   # même valeur que _rebuild_admin_buttons
        panel_w  = self._w - 2 * margin
        val_w    = max(120, int(panel_w * (0.40 if self._is_portrait else 0.32)))
        val_x    = margin + panel_w - val_w

        # --- Zone scrollable (s'arrête avant le bouton fixe du bas) ---
        bottom_res  = self._admin_bottom_reserved()
        scroll_area_h = self._h - HDR_H - bottom_res
        clip = pygame.Rect(0, HDR_H, self._w, scroll_area_h)
        self._screen.set_clip(clip)

        y = HDR_H + 8 - scroll
        sel = self._admin_selection

        for idx, item in enumerate(items):
            itype = item.get("type")

            if itype == "sep":
                sy = y + 6
                if HDR_H <= sy <= self._h:
                    pygame.draw.line(self._screen, _PANEL, (margin, sy), (self._w - margin, sy), 1)
                y += 12
                continue

            if itype == "gpio_info":
                self._r_admin_gpio_rows(y, settings)
                gpio_cfg = settings.get("_gpio_config", {})
                y += ROW_H * (len(gpio_cfg) + 2)
                continue

            item_h = self._item_height(item)
            if y + item_h < HDR_H or y > self._h:
                y += item_h
                continue

            cy = y + ROW_H // 2

            # Sélection clavier : fond surligné + barre orange proportionnelle
            # "back" exclu ici — sa barre est dessinée sur le bouton fixe
            if idx == sel and not self._text_editing and itype != "back":
                # Fond légèrement plus clair sur toute la ligne
                hl = pygame.Surface((panel_w, ROW_H - 4))
                hl.fill((60, 72, 88))
                hl.set_alpha(200)
                self._screen.blit(hl, (margin, y + 2))
                # Barre orange — largeur proportionnelle à la marge (visible à toute résolution)
                bar_w = max(5, int(margin * 0.22))
                bar_x = max(0, margin - bar_w - 4)
                pygame.draw.rect(self._screen, _ACCENT,
                                 (bar_x, y + 2, bar_w, ROW_H - 8),
                                 border_radius=max(2, bar_w // 2))

            if itype == "nav":
                # _NavBtn gère son propre rendu — rien à faire ici
                y += ROW_H
                continue

            if itype in ("action", "back"):
                # Géré par _Btn/_FixedBtn
                y += ROW_H
                continue

            if itype == "info":
                self._txt(item.get("label", ""), "xs", _LGRAY, margin, cy - 1)
                y += ROW_H
                continue

            if itype in ("cycle", "toggle"):
                self._txt(item.get("label", ""), "xs", _LGRAY, margin, cy - 1)
                y += ROW_H
                continue

            if itype == "text":
                key       = item["key"]
                is_active = self._text_editing == key
                is_wide   = item.get("wide", False)
                font      = self._fonts["xs"]
                val       = str(settings.get(key, ""))

                if is_wide:
                    # Ligne 1 : label
                    self._txt(item.get("label", ""), "xs", _LGRAY, margin, y + ROW_H // 2)
                    # Ligne 2 : champ pleine largeur
                    field_h = ROW_H + 8
                    fx, fy = margin, y + ROW_H
                    fw, fh = panel_w, field_h
                    pygame.draw.rect(self._screen, _ACCENT if is_active else _PANEL,
                                     (fx, fy, fw, fh), border_radius=6)
                    # Texte : tronquer depuis le début pour afficher la fin
                    display = val
                    max_fw  = fw - 16
                    while font.size(display)[0] > max_fw and display:
                        display = display[1:]
                    if is_active and int(time.time() * 2) % 2 == 0:
                        display += "|"
                    ts = font.render(display, True, _WHITE)
                    self._screen.blit(ts, (fx + 8, fy + (fh - ts.get_height()) // 2))
                    y += ROW_H + field_h + 6
                else:
                    # Champ standard : label à gauche, champ à droite
                    self._txt(item.get("label", ""), "xs", _LGRAY, margin, cy - 1)
                    fx, fy = val_x, y + (ROW_H - 36) // 2
                    fw, fh = val_w, 36
                    pygame.draw.rect(self._screen, _ACCENT if is_active else _PANEL,
                                     (fx, fy, fw, fh), border_radius=6)
                    display = val
                    while font.size(display)[0] > fw - 16 and display:
                        display = display[1:]
                    if is_active and int(time.time() * 2) % 2 == 0:
                        display += "|"
                    ts = font.render(display, True, _WHITE)
                    self._screen.blit(ts, (fx + 8, fy + (fh - ts.get_height()) // 2))
                    y += ROW_H
                continue

            y += ROW_H

        # Indicateur de scroll
        max_s = self._admin_max_scroll()
        if max_s > 0 and scroll > 0:
            pct = scroll / max_s
            bar_h = max(30, int((self._h - HDR_H) * 0.4))
            bar_y = HDR_H + int(pct * (self._h - HDR_H - bar_h))
            pygame.draw.rect(self._screen, _GRAY, (self._w - 5, bar_y, 3, bar_h), border_radius=2)

        self._screen.set_clip(None)

        # En-tête fixe
        pygame.draw.rect(self._screen, _PANEL, (0, 0, self._w, HDR_H))
        page_titles = {
            "main":    "ADMINISTRATION",
            "plugins": "PLUGINS",
            "photos":  "PHOTOS / TEMPLATES",
            "general": "CONFIGURATION",
            "usb":     "EXPORT USB",
            "print":   "IMPRESSION",
            "gpio":    "DIAGNOSTIC GPIO",
        }
        title = page_titles.get(self._admin_page, self._admin_page.upper())
        self._txt(title, "md", _WHITE, self._w // 2, HDR_H // 2, cx=True)

        if self._admin_stack:
            self._txt("← ESC", "xs", _GRAY, 12, HDR_H // 2)
        hint = "Entree = confirmer" if self._text_editing else ""
        if hint:
            self._txt(hint, "xs", _ACCENT, self._w - 10, HDR_H // 2, ra=True)

        # Indicateur focus sur le bouton ← Retour quand il est sélectionné
        items = self._info.get("items", [])
        back_indices = [i for i, it in enumerate(items) if it.get("type") == "back"]
        if back_indices and self._admin_selection == back_indices[0]:
            lm     = self._lm
            back_h = max(44, lm.btn_h - 6)
            by     = self._h - back_h - max(8, lm.gap_sm)
            pygame.draw.rect(self._screen, _ACCENT,
                             (margin - 8, by + 2, 4, back_h - 8), border_radius=2)

    def _r_admin_gpio_rows(self, start_y: int, settings: dict):
        """Affiche les infos GPIO dans la page diagnostic."""
        gpio_cfg = settings.get("_gpio_config", {})
        gpio_log = settings.get("_gpio_log", [])
        margin = 28
        y = start_y

        labels = {
            "photo_btn":   ("Bouton photo",     "BOARD 11 / BCM17"),
            "print_btn":   ("Bouton print",     "BOARD 13 / BCM27"),
            "photo_led":   ("LED photo",        "BOARD 7  / BCM4"),
            "print_led":   ("LED impression",   "BOARD 15 / BCM22"),
            "startup_led": ("LED startup",      "BOARD 29 / BCM5"),
            "sequence_led":("LED séquence",     "BOARD 31 / BCM6"),
            "flash_led":   ("LED flash",        "BOARD 33 / BCM13"),
        }
        for key, (label, pin) in labels.items():
            if y + ROW_H < HDR_H or y > self._h:
                y += ROW_H
                continue
            cy = y + ROW_H // 2
            self._txt(label, "xs", _LGRAY, margin, cy)
            val = gpio_cfg.get(key, pin)
            self._txt(str(val) if val != pin else pin, "xs", _BLUE,
                      self._w - margin - 5, cy, ra=True)
            y += ROW_H

        bounce = gpio_cfg.get("bounce_ms", 50)
        self._txt(f"Anti-rebond : {bounce} ms", "xs", _GRAY, margin, y + 10)
        y += ROW_H

        # Journal
        if gpio_log:
            self._txt("Journal GPIO :", "xs", _ACCENT, margin, y + 14)
            y += ROW_H
            for entry in reversed(gpio_log[-6:]):
                if y > self._h:
                    break
                self._txt(entry, "xs", _LGRAY, margin + 8, y + 10)
                y += 26

    # ------------------------------------------------------------------
    # Helpers texte
    # ------------------------------------------------------------------

    def _txt_fit(self, text: str, color, x: int, y: int,
                 max_w: int = 0, cx: bool = False):
        """
        Affiche un texte en choisissant automatiquement la plus grande police
        qui tient dans max_w (défaut = self._w - 20).
        Utilisez cette méthode pour tous les titres d'écran afin de supporter
        les deux orientations sans overflow.
        """
        max_w = max_w or (self._w - 20)
        font = self._best_font_for(str(text), max_w, pad=0)
        surf = font.render(str(text), True, color)
        rect = surf.get_rect(center=(x, y)) if cx else surf.get_rect(topleft=(x, y))
        self._screen.blit(surf, rect)

    def _txt(self, text, size, color, x, y, cx=False, ra=False):
        font = self._fonts.get(size, self._fonts["sm"])
        surf = font.render(str(text), True, color)
        if cx:
            rect = surf.get_rect(center=(x, y))
        elif ra:
            rect = surf.get_rect(right=x, centery=y)
        else:
            rect = surf.get_rect(topleft=(x, y))
        self._screen.blit(surf, rect)

    def _shadow_txt(self, text, size, color, x, y, cx=False):
        font = self._fonts.get(size, self._fonts["sm"])
        sh = font.render(str(text), True, _BLACK)
        mn = font.render(str(text), True, color)
        r = mn.get_rect(center=(x, y)) if cx else mn.get_rect(topleft=(x, y))
        self._screen.blit(sh, r.move(2, 2))
        self._screen.blit(mn, r)
