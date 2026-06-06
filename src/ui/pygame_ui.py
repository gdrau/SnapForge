import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import pygame
from PIL import Image

logger = logging.getLogger(__name__)

# Palette
_BLACK      = (0,   0,   0)
_WHITE      = (255, 255, 255)
_DARK       = (22,  27,  34)
_DARK2      = (36,  41,  47)
_PANEL      = (48,  54,  61)
_ACCENT     = (255, 165,   0)
_GREEN      = (46,  160,  67)
_RED        = (207,  34,  46)
_BLUE       = (31,  111, 235)
_GRAY       = (100, 110, 120)
_LIGHT_GRAY = (190, 200, 210)
_DISABLED   = (70,  78,  88)


def _lighten(color, amount=30):
    return tuple(min(v + amount, 255) for v in color)


class _Btn:
    """Bouton cliquable avec texte centré."""

    def __init__(self, rect, text, color, text_color=_WHITE, font=None,
                 action=None, data=None, border_radius=12):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.font = font
        self.action = action
        self.data = data
        self.radius = border_radius
        self._hover = False

    def draw(self, surf: pygame.Surface):
        c = _lighten(self.color) if self._hover else self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=self.radius)
        if self._hover:
            pygame.draw.rect(surf, _WHITE, self.rect, 2, border_radius=self.radius)
        if self.font and self.text:
            ts = self.font.render(self.text, True, self.text_color)
            surf.blit(ts, ts.get_rect(center=self.rect.center))

    def handle(self, event) -> Optional[tuple]:
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return (self.action, self.data)
        return None


class PygameUI:
    """
    Interface plein écran Pygame.

    Règle de thread safety :
    - Les méthodes show_*() sont appelées depuis des threads FSM : elles ne font
      que mettre à jour l'état interne (_screen_name, _info, _buttons).
    - run() s'exécute dans le thread principal (Pygame l'exige) et appelle _render().
    """

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, config):
        self._w: int = config.get("app.width", 800)
        self._h: int = config.get("app.height", 480)
        self._fps: int = config.get("app.fps", 30)
        self._fullscreen: bool = config.get("app.fullscreen", True)
        self._font_path: Optional[str] = config.get("app.font_path")
        self._qr_size: int = config.get("qr.size", 300)
        self._templates_available: List[str] = config.get("templates.available_templates",
                                                           ["strip_classic", "dark_collage"])

        self._callback: Optional[Callable] = None
        self._screen: Optional[pygame.Surface] = None
        self._clock = None
        self._running = False

        self._screen_name = "idle"
        self._buttons: List[_Btn] = []
        self._info: dict = {}
        self._preview_frame: Optional[np.ndarray] = None
        self._preview_lock = threading.Lock()

        self._fonts: dict = {}
        self._init_pygame()

    def _init_pygame(self):
        pygame.init()
        pygame.mouse.set_visible(not self._fullscreen)
        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if self._fullscreen else 0
        self._screen = pygame.display.set_mode((self._w, self._h), flags)
        pygame.display.set_caption("PhotoBooth")
        self._clock = pygame.time.Clock()
        self._load_fonts()
        logger.info(f"Pygame UI : {self._w}x{self._h} fullscreen={self._fullscreen}")

    def _load_fonts(self):
        specs = {"xs": 18, "sm": 24, "md": 30, "lg": 48, "xl": 72, "xxl": 120}
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

    def _emit(self, action: str, data=None):
        if self._callback:
            threading.Thread(target=self._callback, args=(action, data), daemon=True).start()

    # ------------------------------------------------------------------
    # Helpers construction UI
    # ------------------------------------------------------------------

    def _make_btn(self, text: str, color, rect, font_key="md",
                  action=None, data=None, text_color=_WHITE) -> _Btn:
        return _Btn(rect, text, color, text_color=text_color,
                    font=self._fonts[font_key], action=action, data=data)

    def _text_width(self, text: str, font_key: str) -> int:
        return self._fonts[font_key].size(text)[0]

    def _btn_auto(self, text: str, color, cx: int, cy: int, font_key="md",
                  pad_x=40, pad_y=20, action=None, data=None) -> _Btn:
        """Bouton auto-dimensionné : la taille s'adapte au texte."""
        tw, th = self._fonts[font_key].size(text)
        w, h = tw + pad_x * 2, th + pad_y * 2
        rect = (cx - w // 2, cy - h // 2, w, h)
        return _Btn(rect, text, color, font=self._fonts[font_key], action=action, data=data)

    # ------------------------------------------------------------------
    # API show_*() — appelée depuis threads FSM
    # ------------------------------------------------------------------

    def show_idle(self):
        self._screen_name = "idle"
        self._info = {}
        with self._preview_lock:
            self._preview_frame = None
        self._buttons = [
            self._btn_auto(
                "APPUYEZ POUR COMMENCER", _ACCENT,
                cx=self._w // 2, cy=self._h - 80,
                font_key="lg", pad_x=50, pad_y=22,
                action="open_choose_format",   # -> CHOOSE_FORMAT, pas directement une session
            )
        ]

    def show_choose_format(self, layouts: List[int], selected: int):
        self._screen_name = "choose_format"
        self._info = {"selected": selected, "layouts": layouts}
        self._rebuild_format_buttons(layouts, selected)

    def update_format_selection(self, selected: int):
        self._info["selected"] = selected
        # Plus utilisé pour la mise en évidence, mais conservé pour le bouton physique
        for btn in self._buttons:
            if btn.action == "start_session" and isinstance(btn.data, int):
                btn.color = _ACCENT if btn.data == selected else _DARK2

    def _best_font_for_width(self, text: str, max_w: int, pad: int = 40) -> pygame.font.Font:
        """Retourne la plus grande police qui fait tenir text dans max_w."""
        for key in ("xl", "lg", "md", "sm", "xs"):
            if self._fonts[key].size(text)[0] + pad * 2 <= max_w:
                return self._fonts[key]
        return self._fonts["xs"]

    def _rebuild_format_buttons(self, layouts: List[int], selected: int):
        """
        Un tap sur un format = sélection ET démarrage immédiat.
        La police s'adapte automatiquement à la largeur du bouton.
        """
        btns: List[_Btn] = []
        n = len(layouts)
        margin = 40
        gap = 30
        btn_w = (self._w - 2 * margin - gap * (n - 1)) // n
        btn_h = int(self._h * 0.55)
        y = self._h // 2 - btn_h // 2 - 20

        # Police choisie d'après le label le plus long
        longest = max((f"{v} PHOTO{'S' if v > 1 else ''}" for v in layouts), key=len)
        font = self._best_font_for_width(longest, btn_w)

        for i, v in enumerate(layouts):
            x = margin + i * (btn_w + gap)
            c = _ACCENT if v == selected else _BLUE
            btns.append(_Btn(
                (x, y, btn_w, btn_h),
                f"{v} PHOTO{'S' if v > 1 else ''}",
                c, font=font,
                action="start_session", data=v, border_radius=20,
            ))

        self._buttons = btns

    def show_preview(self, total: int, remaining: int):
        self._screen_name = "preview"
        self._info = {"total": total, "remaining": remaining, "countdown": 0}
        self._buttons = [
            self._btn_auto(
                "CAPTURER", _ACCENT,
                cx=self._w // 2, cy=self._h - 55,
                font_key="md", pad_x=50, pad_y=18,
                action="start_countdown",
            )
        ]

    def update_preview_frame(self, frame: np.ndarray):
        with self._preview_lock:
            self._preview_frame = frame

    def show_countdown(self, value: int):
        self._info["countdown"] = value
        self._buttons = []   # Masque CAPTURER pendant toute la séquence

    def show_capture_result(self, path: str, remaining: int):
        self._info["last_photo"] = path
        self._info["remaining"] = remaining
        self._info["countdown"] = 0

    def show_processing(self, step: str):
        self._screen_name = "processing"
        self._buttons = []
        self._info = {"step": step}
        with self._preview_lock:
            self._preview_frame = None

    def show_review(self, photo_path: str, printer_enabled: bool = False):
        self._screen_name = "review"
        self._info = {"photo": photo_path}
        margin = 20
        btn_h = 60
        btn_w = (self._w - 3 * margin) // 2
        btns: List[_Btn] = []
        if printer_enabled:
            btns.append(_Btn(
                (margin, self._h - btn_h - margin, btn_w, btn_h), "IMPRIMER", _BLUE,
                font=self._fonts["sm"], action="confirm_print",
            ))
            btns.append(_Btn(
                (margin * 2 + btn_w, self._h - btn_h - margin, btn_w, btn_h),
                "CONTINUER", _GREEN, font=self._fonts["sm"], action="skip_print",
            ))
        else:
            btns.append(_Btn(
                (margin, self._h - btn_h - margin, self._w - 2 * margin, btn_h),
                "CONTINUER", _GREEN, font=self._fonts["md"], action="skip_print",
            ))
        self._buttons = btns

    def show_print_wait(self):
        self._info["status"] = "Impression en cours..."

    def show_print_result(self, success: bool):
        self._info["status"] = "Imprime !" if success else "Erreur d'impression"

    def show_uploading(self):
        self._screen_name = "uploading"
        self._buttons = []
        self._info = {}

    def show_qr(self, photo_path: str, qr_image, upload_url: Optional[str]):
        self._screen_name = "qr"
        self._info = {"photo": photo_path, "qr": qr_image, "url": upload_url}
        self._buttons = [
            self._btn_auto(
                "RETOUR ACCUEIL", _BLUE,
                cx=self._w // 2, cy=self._h - 55,
                font_key="sm", pad_x=40, pad_y=18,
                action="return_idle",
            )
        ]

    def show_error(self, message: str):
        self._screen_name = "error"
        self._buttons = []
        self._info = {"msg": message}

    # ------------------------------------------------------------------
    # Menu admin
    # ------------------------------------------------------------------

    def show_admin(self, settings: dict):
        self._screen_name = "admin"
        self._info = {"settings": dict(settings)}
        self._rebuild_admin_buttons(settings)

    def _rebuild_admin_buttons(self, settings: dict):
        btns: List[_Btn] = []
        margin = 30
        row_h = 64
        panel_x = margin
        panel_w = self._w - 2 * margin
        val_w = 220
        val_x = panel_x + panel_w - val_w

        # Défini l'ordre et les items du menu
        items = [
            ("Format option A",  "layout_a",     [1, 2, 3, 4], lambda v: f"{v} PHOTO{'S' if v>1 else ''}"),
            ("Format option B",  "layout_b",     [1, 2, 3, 4], lambda v: f"{v} PHOTO{'S' if v>1 else ''}"),
            ("Compte a rebours", "countdown",    [2, 3, 5, 10], lambda v: f"{v} secondes"),
            ("IA fond",          "ai_enabled",   [False, True], lambda v: "ACTIVEE" if v else "DESACTIVEE"),
            ("Impression",       "print_enabled",[False, True], lambda v: "ACTIVEE" if v else "DESACTIVEE"),
            ("Upload cloud",     "cloud_enabled",[False, True], lambda v: "ACTIVE" if v else "DESACTIVE"),
        ]

        header_h = 70
        separator_h = 16
        start_y = header_h + separator_h

        for i, (label, key, values, fmt) in enumerate(items):
            y = start_y + i * (row_h + 8)
            current = settings.get(key, values[0])
            idx = values.index(current) if current in values else 0
            next_val = values[(idx + 1) % len(values)]

            # Couleur selon la valeur
            if isinstance(current, bool):
                color = _GREEN if current else _DISABLED
            else:
                color = _BLUE

            label_str = fmt(current)
            new_settings = dict(settings)
            new_settings[key] = next_val

            btns.append(_Btn(
                (val_x, y, val_w, row_h - 10), label_str, color,
                font=self._fonts["sm"], action="admin_change", data=dict(new_settings),
                border_radius=8,
            ))

        # Boutons d'action en bas
        action_y = start_y + len(items) * (row_h + 8) + 10
        half = (panel_w - 10) // 2
        btns.append(_Btn(
            (panel_x, action_y, half, 55), "SAUVEGARDER", _GREEN,
            font=self._fonts["sm"], action="admin_save", data=dict(settings), border_radius=10,
        ))
        btns.append(_Btn(
            (panel_x + half + 10, action_y, half, 55), "ANNULER", _GRAY,
            font=self._fonts["sm"], action="admin_cancel", data=None, border_radius=10,
        ))
        self._buttons = btns
        self._info["items"] = items  # pour le rendu des labels

    # ------------------------------------------------------------------
    # Boucle principale (thread principal uniquement)
    # ------------------------------------------------------------------

    def run(self):
        self._running = True
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event)
                for btn in list(self._buttons):
                    r = btn.handle(event)
                    if r:
                        action, data = r
                        # Si admin_change : reconstruire les boutons immédiatement
                        if action == "admin_change" and isinstance(data, dict):
                            self.show_admin(data)
                        # Si admin_save : mettre à jour le bouton save avec data courant
                        if action == "admin_save":
                            data = dict(self._info.get("settings", data or {}))
                        self._emit(action, data)
            self._render()
            self._clock.tick(self._fps)
        pygame.quit()

    def stop(self):
        self._running = False

    def _on_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self._screen_name == "admin":
                self._emit("admin_cancel")
            else:
                self._emit("open_admin")
        elif event.key == pygame.K_SPACE:
            if self._screen_name == "idle":
                self._emit("start_session")
            elif self._screen_name == "preview":
                self._emit("start_countdown")
        elif event.key == pygame.K_p and self._screen_name == "review":
            self._emit("confirm_print")
        elif event.key == pygame.K_RETURN and self._screen_name == "choose_format":
            self._emit("start_session", self._info.get("selected"))

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self):
        sn = self._screen_name
        dispatch = {
            "idle":          self._r_idle,
            "choose_format": self._r_choose,
            "preview":       self._r_preview,
            "processing":    self._r_processing,
            "review":        self._r_review,
            "uploading":     self._r_uploading,
            "qr":            self._r_qr,
            "error":         self._r_error,
            "admin":         self._r_admin,
        }
        dispatch.get(sn, lambda: self._screen.fill(_DARK))()
        for btn in self._buttons:
            btn.draw(self._screen)
        pygame.display.flip()

    # --- IDLE ---

    def _r_idle(self):
        self._screen.fill(_DARK)
        self._text("PHOTOBOOTH", "xl", _WHITE, self._w // 2, self._h // 3, center=True)
        self._text("Bienvenue !", "md", _GRAY, self._w // 2, self._h // 2, center=True)
        t = int(time.time() * 2) % 3
        for i in range(3):
            c = _ACCENT if i == t else _GRAY
            pygame.draw.circle(self._screen, c, (self._w // 2 - 20 + i * 20, self._h * 3 // 4 - 60), 7)
        self._text("ESC = menu admin", "xs", _DISABLED, self._w - 10, self._h - 14,
                   center=False, align_right=True)

    # --- CHOOSE FORMAT ---

    def _r_choose(self):
        self._screen.fill(_DARK)
        self._text("Combien de photos ?", "lg", _WHITE, self._w // 2, 48, center=True)

        self._text("ESC = menu admin", "xs", _DISABLED, self._w - 10, self._h - 12,
                   center=False, align_right=True)

    # --- PREVIEW ---

    def _r_preview(self):
        with self._preview_lock:
            frame = self._preview_frame

        if frame is not None:
            try:
                surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                surf = pygame.transform.scale(surf, (self._w, self._h))
                self._screen.blit(surf, (0, 0))
            except Exception:
                self._screen.fill(_BLACK)
        else:
            self._screen.fill(_BLACK)

        remaining = self._info.get("remaining", 0)
        total = self._info.get("total", 0)
        taken = total - remaining
        self._shadow_text(f"{taken}/{total} photo{'s' if total > 1 else ''}",
                          "sm", _WHITE, 14, 14)

        cd = self._info.get("countdown", 0)
        if cd > 0:
            self._shadow_text(str(cd), "xxl", _WHITE,
                              self._w // 2, self._h // 2, center=True)

        self._text("ESC = admin", "xs", _DISABLED, self._w - 10, self._h - 14,
                   center=False, align_right=True)

    # --- PROCESSING ---

    def _r_processing(self):
        self._screen.fill(_DARK)
        self._text("Traitement...", "lg", _WHITE, self._w // 2, self._h // 3, center=True)
        step = self._info.get("step", "")
        self._text(step, "sm", _ACCENT, self._w // 2, self._h // 2, center=True)
        bar_w = 400
        bar_x = (self._w - bar_w) // 2
        bar_y = self._h * 2 // 3
        pygame.draw.rect(self._screen, _DARK2, (bar_x, bar_y, bar_w, 10), border_radius=5)
        fill = int((time.time() * 80) % (bar_w + 60)) - 30
        fill = max(0, min(fill, bar_w))
        if fill > 0:
            pygame.draw.rect(self._screen, _ACCENT, (bar_x, bar_y, fill, 10), border_radius=5)

    # --- REVIEW ---

    def _r_review(self):
        self._screen.fill(_BLACK)
        photo = self._info.get("photo")
        if photo and Path(photo).exists():
            try:
                img = pygame.image.load(photo)
                iw, ih = img.get_size()
                max_w, max_h = self._w - 40, self._h - 110
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = pygame.transform.scale(img, (nw, nh))
                self._screen.blit(img, ((self._w - nw) // 2, 15))
            except Exception as e:
                logger.error(f"Review image: {e}")
        status = self._info.get("status")
        if status:
            self._text(status, "sm", _ACCENT, self._w // 2, self._h - 90, center=True)


    # --- UPLOADING ---

    def _r_uploading(self):
        self._screen.fill(_DARK)
        self._text("Envoi en cours...", "lg", _WHITE, self._w // 2, self._h // 2, center=True)

    # --- QR ---

    def _r_qr(self):
        self._screen.fill(_DARK)
        photo = self._info.get("photo")
        qr_img = self._info.get("qr")
        if photo and Path(photo).exists():
            try:
                img = pygame.image.load(photo)
                iw, ih = img.get_size()
                max_w = self._w // 2 - 30
                max_h = self._h - 80
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = pygame.transform.scale(img, (nw, nh))
                self._screen.blit(img, (15, (self._h - nh) // 2))
            except Exception:
                pass
        if qr_img is not None:
            try:
                pil = qr_img.convert("RGB")
                qsurf = pygame.image.fromstring(pil.tobytes(), pil.size, "RGB")
                sz = self._qr_size
                qsurf = pygame.transform.scale(qsurf, (sz, sz))
                qx = self._w - sz - 15
                qy = (self._h - sz) // 2 - 20
                self._screen.blit(qsurf, (qx, qy))
                self._text("Scannez pour", "xs", _LIGHT_GRAY, qx + sz // 2, qy + sz + 6, center=True)
                self._text("telecharger", "xs", _LIGHT_GRAY, qx + sz // 2, qy + sz + 24, center=True)
            except Exception as e:
                logger.error(f"QR render: {e}")
        else:
            self._text("Pas de QR code", "sm", _GRAY, self._w * 3 // 4, self._h // 2, center=True)


    # --- ERROR ---

    def _r_error(self):
        self._screen.fill((50, 15, 15))
        self._text("ERREUR", "xl", _RED, self._w // 2, self._h // 3, center=True)
        msg = str(self._info.get("msg", ""))[:70]
        self._text(msg, "xs", _LIGHT_GRAY, self._w // 2, self._h // 2, center=True)
        self._text("Retour a l'accueil...", "xs", _GRAY, self._w // 2, self._h * 2 // 3, center=True)

    # --- ADMIN ---

    def _r_admin(self):
        self._screen.fill(_DARK)
        settings = self._info.get("settings", {})
        items = self._info.get("items", [])

        # En-tête
        header_h = 62
        pygame.draw.rect(self._screen, _PANEL, (0, 0, self._w, header_h))
        self._text("CONFIGURATION", "md", _WHITE, self._w // 2, header_h // 2, center=True)
        self._text("ESC = annuler", "xs", _DISABLED, self._w - 10, header_h // 2,
                   center=False, align_right=True)

        margin = 30
        row_h = 64
        panel_w = self._w - 2 * margin
        val_w = 220
        val_x = margin + panel_w - val_w
        start_y = header_h + 14

        for i, (label, key, values, fmt) in enumerate(items):
            y = start_y + i * (row_h + 8)
            current = settings.get(key, values[0])
            cy = y + (row_h - 10) // 2 - 2

            # Séparateur
            if i > 0:
                pygame.draw.line(self._screen, _PANEL,
                                 (margin, y - 4), (self._w - margin, y - 4), 1)

            # Label
            self._text(label, "sm", _LIGHT_GRAY, margin, cy, center=False)

            # Valeur formatée (rendu par les boutons, juste le texte ici pour debug)
            # Les boutons sont dessinés après dans run()

        # Légende clic
        action_y = start_y + len(items) * (row_h + 8) + 68
        self._text("Cliquez sur une valeur pour la changer", "xs", _DISABLED,
                   self._w // 2, action_y, center=True)

    # ------------------------------------------------------------------
    # Helpers rendu texte + indicateurs boutons
    # ------------------------------------------------------------------

    def _text(self, text: str, size: str, color, x: int, y: int,
              center=False, align_right=False):
        font = self._fonts.get(size, self._fonts["sm"])
        surf = font.render(str(text), True, color)
        if center:
            rect = surf.get_rect(center=(x, y))
        elif align_right:
            rect = surf.get_rect(right=x, centery=y)
        else:
            rect = surf.get_rect(topleft=(x, y))
        self._screen.blit(surf, rect)

    def _shadow_text(self, text: str, size: str, color, x: int, y: int, center=False):
        font = self._fonts.get(size, self._fonts["sm"])
        shadow = font.render(str(text), True, _BLACK)
        main = font.render(str(text), True, color)
        if center:
            r = main.get_rect(center=(x, y))
        else:
            r = main.get_rect(topleft=(x, y))
        self._screen.blit(shadow, r.move(2, 2))
        self._screen.blit(main, r)
