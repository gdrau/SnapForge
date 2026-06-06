import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import pygame

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

ROW_H = 54       # hauteur d'une ligne de menu
HDR_H = 52       # hauteur de l'en-tête admin
BTN_H = 52       # hauteur du bouton Sauvegarder/Annuler


class _Btn:
    fixed = False   # True = position absolue, non affectée par le scroll admin

    def __init__(self, rect, text, color, text_color=_WHITE, font=None,
                 action=None, data=None, radius=10):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.font = font
        self.action = action
        self.data = data
        self.radius = radius
        self._hover = False

    def draw(self, surf):
        c = tuple(min(v + 25, 255) for v in self.color) if self._hover else self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=self.radius)
        if self.font and self.text:
            ts = self.font.render(str(self.text), True, self.text_color)
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
        self._w = config.get("app.width", 800)
        self._h = config.get("app.height", 480)
        self._fps = config.get("app.fps", 30)
        self._fullscreen = config.get("app.fullscreen", True)
        self._font_path = config.get("app.font_path")
        self._qr_size = config.get("qr.size", 300)

        self._callback: Optional[Callable] = None
        self._screen = None
        self._clock = None
        self._running = False

        # Écran courant
        self._screen_name = "idle"
        self._buttons: List[_Btn] = []
        self._info: dict = {}
        self._preview_frame = None
        self._preview_lock = threading.Lock()

        # Admin
        self._admin_page = "main"
        self._admin_stack: List[str] = []
        self._admin_scroll = 0
        self._admin_scroll_cache: dict = {}
        self._text_editing: Optional[str] = None

        self._fonts: dict = {}
        self._init_pygame()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

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
        specs = {"xs": 18, "sm": 22, "md": 30, "lg": 48, "xl": 72, "xxl": 120}
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

    def show_idle(self, booth_name: str = "SnapForge"):
        self._screen_name = "idle"
        self._info = {"booth_name": booth_name}
        with self._preview_lock:
            self._preview_frame = None
        self._buttons = [
            self._btn_auto("APPUYEZ POUR COMMENCER", _ACCENT,
                           self._w // 2, self._h - 80, font="lg", px=50, py=22,
                           action="open_choose_format")
        ]

    def show_choose_format(self, layouts: List[int], selected: int):
        self._screen_name = "choose_format"
        self._info = {"layouts": layouts, "selected": selected}
        self._rebuild_format_buttons(layouts, selected)

    def update_format_selection(self, selected: int):
        self._info["selected"] = selected

    def _rebuild_format_buttons(self, layouts, selected):
        n = len(layouts)
        margin, gap = 40, 30
        btn_w = (self._w - 2 * margin - gap * (n - 1)) // n
        btn_h = int(self._h * 0.55)
        y = self._h // 2 - btn_h // 2 - 20
        longest = max((f"{v} PHOTO{'S' if v > 1 else ''}" for v in layouts), key=len)
        font = self._best_font_for(longest, btn_w)
        btns = []
        for i, v in enumerate(layouts):
            x = margin + i * (btn_w + gap)
            c = _ACCENT if v == selected else _BLUE
            btns.append(_Btn((x, y, btn_w, btn_h), f"{v} PHOTO{'S' if v > 1 else ''}",
                             c, font=font, action="start_session", data=v, radius=20))
        self._buttons = btns

    def _best_font_for(self, text, max_w, pad=40):
        for key in ("xl", "lg", "md", "sm", "xs"):
            if self._fonts[key].size(text)[0] + pad * 2 <= max_w:
                return self._fonts[key]
        return self._fonts["xs"]

    def show_preview(self, total: int, remaining: int):
        self._screen_name = "preview"
        self._info = {"total": total, "remaining": remaining, "countdown": 0}
        self._buttons = [
            self._btn_auto("CAPTURER", _ACCENT, self._w // 2, self._h - 55,
                           font="md", px=50, py=18, action="start_countdown")
        ]

    def update_preview_frame(self, frame: np.ndarray):
        with self._preview_lock:
            self._preview_frame = frame

    def show_countdown(self, value: int):
        self._info["countdown"] = value
        self._buttons = []

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
        m = 20
        bh, bw = 60, (self._w - 3 * m) // 2
        if printer_enabled:
            self._buttons = [
                self._btn("IMPRIMER", _BLUE, (m, self._h - bh - m, bw, bh), "sm", "confirm_print"),
                self._btn("CONTINUER", _GREEN, (m*2 + bw, self._h - bh - m, bw, bh), "sm", "skip_print"),
            ]
        else:
            self._buttons = [
                self._btn("CONTINUER", _GREEN, (m, self._h - bh - m, self._w - 2*m, bh), "md", "skip_print"),
            ]

    def show_print_wait(self):
        self._info["status"] = "Impression en cours..."

    def show_print_result(self, success: bool):
        self._info["status"] = "Imprime !" if success else "Erreur d'impression"

    def show_qr(self, photo_path: str, qr_image, upload_url):
        self._screen_name = "qr"
        self._info = {"photo": photo_path, "qr": qr_image, "url": upload_url}
        self._buttons = [
            self._btn_auto("RETOUR ACCUEIL", _BLUE, self._w // 2, self._h - 55,
                           font="sm", px=40, py=18, action="return_idle")
        ]

    def show_error(self, message: str):
        self._screen_name = "error"
        self._buttons = []
        self._info = {"msg": str(message)}

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def show_admin(self, settings: dict):
        self._screen_name = "admin"
        self._admin_page = "main"
        self._admin_stack = []
        self._admin_scroll = 0
        self._admin_scroll_cache = {}
        self._text_editing = None
        self._info = {"settings": dict(settings)}
        self._build_admin(settings)

    def _build_admin(self, settings: dict):
        """Reconstruit les boutons de la page admin courante."""
        items = self._admin_items(self._admin_page, settings)
        self._info["items"] = items
        self._rebuild_admin_buttons(items, settings)

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
                {"type": "nav", "label": "Diagnostic GPIO",     "target": "gpio",
                 "desc": "Boutons · LEDs · Journal"},
                {"type": "sep"},
                {"type": "action", "label": "Sauvegarder et quitter", "action": "admin_save",  "color": _GREEN},
                {"type": "action", "label": "Quitter sans sauvegarder", "action": "admin_cancel", "color": _GRAY},
            ]

        if page == "plugins":
            return [
                {"type": "toggle", "label": "QR Code sur résultat", "key": "qr_on_result", "fmt": fmt_on},
                {"type": "toggle", "label": "IA remplacement fond", "key": "ai_enabled",   "fmt": lambda v: "ACTIVEE" if v else "DESACTIVEE"},
                {"type": "toggle", "label": "Impression",           "key": "print_enabled","fmt": lambda v: "ACTIVEE" if v else "DESACTIVEE"},
                {"type": "toggle", "label": "Upload cloud",         "key": "cloud_enabled","fmt": lambda v: "ACTIVE" if v else "DESACTIVE"},
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
                {"type": "text",  "label": "Titre",              "key": "event_title"},
                {"type": "text",  "label": "Description",        "key": "event_description"},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "general":
            return [
                {"type": "text",  "label": "Nom du photobooth", "key": "booth_name"},
                {"type": "cycle", "label": "Compte à rebours",  "key": "countdown", "values": [2,3,5,10], "fmt": fmt_s},
                {"type": "sep"},
                {"type": "back"},
            ]

        if page == "gpio":
            return [
                {"type": "gpio_info"},
                {"type": "sep"},
                {"type": "back"},
            ]

        return [{"type": "back"}]

    def _rebuild_admin_buttons(self, items: list, settings: dict):
        """Construit la liste de boutons pour les items de la page."""
        margin = 28
        panel_w = self._w - 2 * margin
        val_w = 200
        val_x = margin + panel_w - val_w

        btns: List[_Btn] = []
        y = HDR_H + 8

        for item in items:
            itype = item.get("type")

            if itype == "sep":
                y += 12
                continue

            if itype in ("back", "gpio_info"):
                y += ROW_H
                continue

            if itype == "nav":
                # _NavBtn dessine lui-même le fond ET le texte — pas d'overdraw
                btns.append(_NavBtn(
                    (margin, y, panel_w, ROW_H - 4),
                    item["label"], item.get("desc", ""),
                    self._fonts["sm"], self._fonts["xs"],
                    "admin_nav", item["target"],
                ))
                y += ROW_H
                continue

            if itype == "action":
                btns.append(_Btn(
                    (margin, y, panel_w, ROW_H - 4), item["label"], item["color"],
                    font=self._fonts["sm"], action=item["action"], data=None, radius=8,
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
                key = item["key"]
                is_active = self._text_editing == key
                color = _ACCENT if is_active else _PANEL
                btns.append(_Btn(
                    (val_x, y + (ROW_H - 36) // 2, val_w, 36), "",
                    color, action="admin_text_activate", data=key, radius=6,
                ))
                y += ROW_H
                continue

            y += ROW_H

        # Bouton ← Retour fixe en bas pour les sous-pages (non scrollé)
        if self._admin_page != "main":
            back = _Btn(
                (margin, self._h - BTN_H + 2, 170, BTN_H - 12),
                "<  Retour", _PANEL,
                font=self._fonts["sm"], action="admin_back_btn", radius=8,
            )
            back.fixed = True
            btns.append(back)

        self._buttons = btns

    def _admin_max_scroll(self) -> int:
        """Calcule le scroll maximum pour ne pas dépasser le contenu."""
        items = self._info.get("items", [])
        total_h = HDR_H + 8
        for item in items:
            itype = item.get("type")
            total_h += 12 if itype == "sep" else ROW_H
        # Zone visible sous le header
        visible_h = self._h - HDR_H
        return max(0, total_h - visible_h - BTN_H - 8)

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self):
        self._running = True
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    continue

                if event.type == pygame.KEYDOWN:
                    if self._screen_name == "admin":
                        if self._handle_admin_key(event):
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
                self._admin_scroll_cache[self._admin_page] = self._admin_scroll
                self._admin_stack.append(self._admin_page)
                self._admin_page = data
                self._admin_scroll = self._admin_scroll_cache.get(data, 0)
                self._text_editing = None
                self._build_admin(settings)

            elif action == "admin_back_btn":
                if self._admin_stack:
                    prev = self._admin_stack.pop()
                    self._admin_scroll_cache[self._admin_page] = self._admin_scroll
                    self._admin_page = prev
                    self._admin_scroll = self._admin_scroll_cache.get(prev, 0)
                    self._build_admin(settings)
                else:
                    self._emit("admin_cancel")

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

            else:
                self._emit(action, data)
            break

    def _handle_admin_key(self, event) -> bool:
        """Gère les touches clavier dans l'admin. Retourne True si consommé."""
        if self._text_editing:
            settings = self._info.get("settings", {})
            cur = str(settings.get(self._text_editing, ""))
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._text_editing = None
                self._build_admin(settings)
                return True
            if event.key == pygame.K_ESCAPE:
                self._text_editing = None
                self._build_admin(settings)
                return True
            if event.key == pygame.K_BACKSPACE:
                settings[self._text_editing] = cur[:-1]
                self._info["settings"] = settings
                self._build_admin(settings)
                return True
            if event.unicode and event.unicode.isprintable() and len(cur) < 60:
                settings[self._text_editing] = cur + event.unicode
                self._info["settings"] = settings
                self._build_admin(settings)
                return True
            return True  # Consomme tous les events clavier en mode saisie

        if event.key == pygame.K_ESCAPE:
            if self._admin_stack:
                # Retour page précédente
                prev = self._admin_stack.pop()
                self._admin_scroll_cache[self._admin_page] = self._admin_scroll
                self._admin_page = prev
                self._admin_scroll = self._admin_scroll_cache.get(prev, 0)
                self._build_admin(self._info.get("settings", {}))
            else:
                # Sur main → fermer admin
                self._emit("admin_cancel")
            return True
        return False

    def stop(self):
        self._running = False

    def _on_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self._emit("open_admin")
        elif event.key == pygame.K_SPACE:
            if self._screen_name == "idle":
                self._emit("open_choose_format")
            elif self._screen_name == "preview":
                self._emit("start_countdown")

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self):
        dispatch = {
            "idle":          self._r_idle,
            "choose_format": self._r_choose,
            "preview":       self._r_preview,
            "processing":    self._r_processing,
            "review":        self._r_review,
            "qr":            self._r_qr,
            "error":         self._r_error,
            "admin":         self._r_admin,
        }
        dispatch.get(self._screen_name, lambda: self._screen.fill(_DARK))()
        for btn in self._buttons:
            if self._screen_name == "admin":
                if btn.fixed:
                    # Bouton à position fixe (ex: Retour) — dessiné tel quel, pas de clip
                    btn.draw(self._screen)
                else:
                    real_rect = btn.rect.move(0, -self._admin_scroll)
                    if real_rect.bottom <= HDR_H or real_rect.top >= self._h:
                        continue
                    orig = btn.rect
                    btn.rect = real_rect
                    btn.draw(self._screen)
                    btn.rect = orig
            else:
                btn.draw(self._screen)
        pygame.display.flip()

    def _r_idle(self):
        self._screen.fill(_DARK)
        name = self._info.get("booth_name", "SnapForge")
        font = self._best_font_for(name, self._w - 60)
        surf = font.render(name, True, _WHITE)
        self._screen.blit(surf, surf.get_rect(center=(self._w // 2, self._h // 3)))
        self._txt("Bienvenue !", "md", _GRAY, self._w // 2, self._h // 2, cx=True)
        t = int(time.time() * 2) % 3
        for i in range(3):
            pygame.draw.circle(self._screen, _ACCENT if i == t else _GRAY,
                               (self._w // 2 - 20 + i * 20, self._h * 3 // 4 - 60), 7)

    def _r_choose(self):
        self._screen.fill(_DARK)
        self._txt("Combien de photos ?", "lg", _WHITE, self._w // 2, 48, cx=True)
        self._txt("Appuyez sur votre choix pour commencer", "sm", _GRAY,
                  self._w // 2, self._h - 28, cx=True)

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
        self._shadow_txt(f"{total - remaining}/{total}", "sm", _WHITE, 14, 14)

        cd = self._info.get("countdown", 0)
        if cd > 0:
            self._shadow_txt(str(cd), "xxl", _WHITE, self._w // 2, self._h // 2, cx=True)

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
        photo = self._info.get("photo")
        if photo and Path(photo).exists():
            try:
                img = pygame.image.load(photo)
                iw, ih = img.get_size()
                scale = min((self._w - 40) / iw, (self._h - 110) / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = pygame.transform.scale(img, (nw, nh))
                self._screen.blit(img, ((self._w - nw) // 2, 15))
            except Exception as e:
                logger.error(f"Review: {e}")
        if self._info.get("status"):
            self._txt(self._info["status"], "sm", _ACCENT, self._w // 2, self._h - 90, cx=True)

    def _r_qr(self):
        self._screen.fill(_DARK)
        photo = self._info.get("photo")
        if photo and Path(photo).exists():
            try:
                img = pygame.image.load(photo)
                iw, ih = img.get_size()
                scale = min((self._w // 2 - 30) / iw, (self._h - 80) / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                img = pygame.transform.scale(img, (nw, nh))
                self._screen.blit(img, (15, (self._h - nh) // 2))
            except Exception:
                pass
        qr = self._info.get("qr")
        if qr is not None:
            try:
                pil = qr.convert("RGB")
                qsurf = pygame.image.fromstring(pil.tobytes(), pil.size, "RGB")
                sz = self._qr_size
                qsurf = pygame.transform.scale(qsurf, (sz, sz))
                qx = self._w - sz - 15
                qy = (self._h - sz) // 2 - 20
                self._screen.blit(qsurf, (qx, qy))
                self._txt("Scannez pour", "xs", _LGRAY, qx + sz // 2, qy + sz + 8, cx=True)
                self._txt("telecharger", "xs", _LGRAY, qx + sz // 2, qy + sz + 24, cx=True)
            except Exception as e:
                logger.error(f"QR: {e}")
        else:
            self._txt("Photo enregistree !", "md", _LGRAY, self._w * 3 // 4, self._h // 2, cx=True)

    def _r_error(self):
        self._screen.fill((50, 15, 15))
        self._txt("ERREUR", "xl", _RED, self._w // 2, self._h // 3, cx=True)
        self._txt(str(self._info.get("msg", ""))[:70], "xs", _LGRAY, self._w // 2, self._h // 2, cx=True)
        self._txt("Retour automatique...", "xs", _GRAY, self._w // 2, self._h * 2 // 3, cx=True)

    # ------------------------------------------------------------------
    # Rendu admin
    # ------------------------------------------------------------------

    def _r_admin(self):
        self._screen.fill(_DARK)
        settings = self._info.get("settings", {})
        items = self._info.get("items", [])
        scroll = self._admin_scroll
        margin = 28
        panel_w = self._w - 2 * margin
        val_w = 200
        val_x = margin + panel_w - val_w

        # --- Zone scrollable ---
        clip = pygame.Rect(0, HDR_H, self._w, self._h - HDR_H)
        self._screen.set_clip(clip)

        y = HDR_H + 8 - scroll

        for item in items:
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

            if y + ROW_H < HDR_H or y > self._h:
                y += ROW_H
                continue

            cy = y + ROW_H // 2

            if itype == "nav":
                # _NavBtn gère son propre rendu — rien à faire ici
                y += ROW_H
                continue

            if itype in ("action", "back"):
                # Géré par _Btn/_FixedBtn
                y += ROW_H
                continue

            if itype in ("cycle", "toggle"):
                self._txt(item.get("label", ""), "xs", _LGRAY, margin, cy - 1)
                y += ROW_H
                continue

            if itype == "text":
                key = item["key"]
                is_active = self._text_editing == key
                self._txt(item.get("label", ""), "xs", _LGRAY, margin, cy - 1)
                fx, fy = val_x, y + (ROW_H - 36) // 2
                fw, fh = val_w, 36
                pygame.draw.rect(self._screen, _ACCENT if is_active else _PANEL,
                                 (fx, fy, fw, fh), border_radius=6)
                val = str(settings.get(key, ""))
                display = val
                font = self._fonts["xs"]
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
            "main": "ADMINISTRATION",
            "plugins": "PLUGINS",
            "photos": "PHOTOS / TEMPLATES",
            "general": "CONFIGURATION",
            "gpio": "DIAGNOSTIC GPIO",
        }
        title = page_titles.get(self._admin_page, self._admin_page.upper())
        self._txt(title, "md", _WHITE, self._w // 2, HDR_H // 2, cx=True)

        if self._admin_stack:
            self._txt("← ESC", "xs", _GRAY, 12, HDR_H // 2)
        hint = "Entree = confirmer" if self._text_editing else ""
        if hint:
            self._txt(hint, "xs", _ACCENT, self._w - 10, HDR_H // 2, ra=True)

        # Le bouton ← Retour est géré par _FixedBtn dans _rebuild_admin_buttons

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
