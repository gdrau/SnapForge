import logging
import shutil
import threading
import time
from collections import deque
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Deque, List, Optional

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    CHOOSE_TYPE   = auto()    # Photo ou GIF ?  (niveau 1)
    CHOOSE_FORMAT = auto()    # 1 photo, 4 photos ?  (niveau 2, si Photo)
    CHOOSE_GIF_ORIENTATION = auto()  # Portrait ou Paysage ? (niveau 3, si GIF)
    PREVIEW = auto()
    COUNTDOWN = auto()
    CAPTURE = auto()
    PROCESSING = auto()
    GIF_PROCESSING = auto()
    REVIEW = auto()
    PRINT_WAIT = auto()
    QR_DISPLAY = auto()
    ADMIN = auto()
    ERROR = auto()
    USB_EXPORT = auto()


def _clear_dir(path: Path) -> int:
    """Vide un dossier sans le supprimer. Retourne le nombre d'éléments supprimés."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return 0
    count = 0
    for item in path.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            count += 1
        except Exception as e:
            logger.warning(f"Suppression impossible : {item} — {e}")
    return count


# États où le timer d'inactivité est actif
_INACTIVITY_STATES = frozenset({
    State.CHOOSE_TYPE,
    State.CHOOSE_FORMAT,
    State.CHOOSE_GIF_ORIENTATION,
    State.PREVIEW,
    State.REVIEW,
    State.PRINT_WAIT,
})


class Session:

    def __init__(self, layout_count: int, raw_dir: str, final_dir: str,
                 is_gif_mode: bool = False, gif_orientation: str = "portrait"):
        self.layout_count = layout_count
        self.is_gif_mode  = is_gif_mode
        self.gif_orientation  = gif_orientation   # "portrait" | "landscape"
        self.timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir  = Path(raw_dir) / self.timestamp
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.final_dir    = Path(final_dir)
        self.final_dir.mkdir(parents=True, exist_ok=True)

        existing       = len(list(self.final_dir.glob("snapforge_*.jpg")))
        self._number   = existing + 1

        self.raw_photos:       List[str] = []
        self.processed_photos: List[str] = []
        self.final_photo:      Optional[str] = None
        self.gif_path:         Optional[str] = None   # chemin du GIF généré
        self.upload_url:       Optional[str] = None
        self.error:            Optional[str] = None

    @property
    def final_filename(self) -> str:
        return f"snapforge_{self._number:04d}_{self.timestamp}.jpg"

    @property
    def final_path(self) -> str:
        return str(self.final_dir / self.final_filename)

    def next_raw_path(self) -> str:
        idx = len(self.raw_photos) + 1
        return str(self.session_dir / f"photo_{self._number:04d}_{idx:02d}_{self.timestamp}.jpg")

    @property
    def is_complete(self) -> bool:
        return len(self.raw_photos) >= self.layout_count

    @property
    def remaining(self) -> int:
        return self.layout_count - len(self.raw_photos)


class StateMachine:

    def __init__(self, config, camera, lights, buttons, composer, ai_processor,
                 uploader, printer, qr_gen, ui, gif_maker=None, usb_exporter=None):
        self._config     = config
        self._camera     = camera
        self._lights     = lights
        self._buttons    = buttons
        self._composer   = composer
        self._ai         = ai_processor
        self._uploader   = uploader
        self._printer    = printer
        self._qr         = qr_gen
        self._ui         = ui
        self._gif_maker      = gif_maker
        self._usb_exporter   = usb_exporter

        self._state = State.IDLE
        self._session: Optional[Session] = None
        self._return_timer: Optional[threading.Timer] = None
        self._inactivity_timer: Optional[threading.Timer] = None
        self._inactivity_timeout: float = float(
            config.get("session.inactivity_timeout_seconds", 10)
        )

        # Options lues depuis config (compatibilité option_a/b + legacy available_layouts)
        self._option_a: int = config.get("photos.option_a",
                          (config.get("photos.available_layouts", [1, 4]) or [1])[0])
        self._option_b: int = config.get("photos.option_b",
                          (config.get("photos.available_layouts", [1, 4]) or [1, 4])[-1])

        self._countdown_s: int = config.get("session.countdown_seconds",
                             config.get("camera.countdown_seconds", 3))
        self._raw_dir: str = config.get("photos.raw_dir", "Photo/raw")
        self._final_dir: str = config.get("photos.final_dir", "Photo/final")

        # Journal GPIO pour le diagnostic
        self._gpio_log: Deque[str] = deque(maxlen=20)

    def start(self):
        self._buttons.on_photo_button(self._on_photo_button)
        self._buttons.on_print_button(self._on_print_button)
        self._buttons.on_usb_button(self._on_usb_button)
        self._ui.set_activity_callback(self._on_user_activity)
        self._lights.startup_on()
        self._go(State.IDLE)

    def stop(self):
        self._cancel_timer()
        self._cancel_inactivity()
        self._lights.all_off()
        try:
            self._camera.stop_preview()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # FSM
    # ------------------------------------------------------------------

    def _go(self, state: State):
        logger.info(f"[FSM] {self._state.name} -> {state.name}")
        self._state = state
        if state in _INACTIVITY_STATES:
            self._reset_inactivity()
        else:
            self._cancel_inactivity()
        {
            State.IDLE:          self._enter_idle,
            State.CHOOSE_TYPE:   self._enter_choose_type,
            State.CHOOSE_FORMAT: self._enter_choose_format,
            State.CHOOSE_GIF_ORIENTATION: self._enter_choose_gif_orientation,
            State.PREVIEW:       self._enter_preview,
            State.COUNTDOWN:     self._enter_countdown,
            State.CAPTURE:       self._enter_capture,
            State.PROCESSING:    self._enter_processing,
            State.REVIEW:        self._enter_review,
            State.PRINT_WAIT:    self._enter_print_wait,
            State.GIF_PROCESSING: self._enter_gif_processing,
            State.QR_DISPLAY:    self._enter_qr_display,
            State.ADMIN:         self._enter_admin,
            State.ERROR:         self._enter_error,
            State.USB_EXPORT:    self._enter_usb_export,
        }[state]()

    def _enter_idle(self):
        self._session = None
        self._lights.all_off()
        self._lights.startup_on()
        self._lights.photo_ready()
        self._ui.show_idle(
            booth_name=self._config.get("app.booth_name", "SnapForge"),
            booth_name_size=int(self._config.get("app.booth_name_size", 0)),
            booth_subtitle=self._config.get("app.booth_subtitle", ""),
            booth_subtitle_size=int(self._config.get("app.booth_subtitle_size", 0)),
        )

    def _enter_choose_type(self):
        """Écran niveau 1 : Photo ou GIF ?"""
        self._lights.sequence_blink()
        self._ui.show_choose_type()

    def _enter_choose_format(self):
        """Écran niveau 2 : nombre de photos (uniquement si type=Photo)."""
        self._lights.sequence_blink()
        self._ui.show_choose_format(
            [self._option_a, self._option_b], self._option_a,
            gif_enabled=False   # GIF déjà géré au niveau 1
        )

    def _enter_choose_gif_orientation(self):
        """Écran niveau 3 : Portrait ou Paysage pour le GIF animé."""
        self._lights.sequence_blink()
        self._ui.show_choose_gif_orientation()

    def _preview_slot_ar(self):
        """Retourne le ratio largeur/hauteur du slot du template final (ou de la capture GIF).

        Ce ratio détermine les proportions de la boîte preview à l'écran, de façon
        à ce que l'utilisateur cadre exactement ce qui sera dans la photo finale.
        """
        if self._session.is_gif_mode:
            if self._session.gif_orientation == "landscape":
                tpl_name = self._config.get("templates.photo_4", "landscape_4photos")
                slot = self._composer.first_slot(tpl_name)
                if slot:
                    return slot["width"] / slot["height"]
                return 1.778  # fallback 16:9
            # Portrait GIF : même slot que 1 photo
            tpl_name = self._config.get("templates.photo_1", "portrait_1photo")
            slot = self._composer.first_slot(tpl_name)
            if slot:
                return slot["width"] / slot["height"]
            cap_w = int(self._config.get("camera.resolution_width", 3280))
            cap_h = int(self._config.get("camera.resolution_height", 2464))
            return cap_h / cap_w
        n = self._session.layout_count
        tpl_name = self._config.get(f"templates.photo_{n}", "portrait_1photo")
        slot = self._composer.first_slot(tpl_name)
        return (slot["width"] / slot["height"]) if slot else None

    def _enter_preview(self):
        self._lights.sequence_on()
        slot_ar = self._preview_slot_ar()
        self._ui.show_preview(self._session.layout_count, self._session.remaining,
                              slot_ar=slot_ar)
        self._camera.start_preview(self._ui.update_preview_frame)

    def _enter_countdown(self):
        self._lights.sequence_blink()
        threading.Thread(target=self._run_countdown, daemon=True).start()

    def _run_countdown(self):
        for i in range(self._countdown_s, 0, -1):
            self._ui.show_countdown(i)
            time.sleep(1)
        # "Souriez !" pendant 700ms avant le déclenchement
        self._ui.show_smile()
        time.sleep(0.7)
        self._go(State.CAPTURE)

    def _enter_capture(self):
        path = self._session.next_raw_path()
        self._lights.flash_async()
        threading.Thread(target=self._do_capture, args=(path,), daemon=True).start()

    def _do_capture(self, path: str):
        try:
            # Laisser la LED atteindre sa luminosité max avant le déclenchement
            pre_delay = float(self._config.get("camera.flash_pre_delay", 0.05))
            if pre_delay > 0:
                time.sleep(pre_delay)
            self._camera.capture(path)
            self._session.raw_photos.append(path)
            n = len(self._session.raw_photos)
            total = self._session.layout_count
            logger.info(f"Photo {n}/{total}: {path}")
            self._ui.show_capture_result(path, self._session.remaining)

            if self._session.is_complete:
                self._camera.stop_preview()
                if self._session.is_gif_mode:
                    self._go(State.GIF_PROCESSING)
                else:
                    self._go(State.PROCESSING)
            else:
                if self._session.is_gif_mode:
                    # Délai configurable entre captures GIF, "Souriez !" visible avant le flash
                    delay = float(self._config.get("gif.delay_between_frames_seconds", 1.0))
                    self._ui.show_smile()
                    time.sleep(delay)
                    self._go(State.CAPTURE)
                else:
                    time.sleep(0.8)
                    self._go(State.COUNTDOWN)

        except Exception as e:
            logger.exception("Erreur capture")
            self._session.error = str(e)
            self._go(State.ERROR)

    def _enter_processing(self):
        self._lights.sequence_blink()
        self._ui.show_processing("Assemblage en cours...")
        threading.Thread(target=self._do_processing, daemon=True).start()

    def _do_processing(self):
        try:
            photos = self._session.raw_photos
            if self._ai.should_apply and self._ai.apply_on == "raw_photo":
                self._ui.show_processing("IA : remplacement de fond...")
                self._session.processed_photos = [self._ai.process(p) for p in photos]
            else:
                self._session.processed_photos = photos

            self._ui.show_processing("Composition de l'image...")

            # Template selon le nombre de photos — compatibilité ancienne et nouvelle config
            n = self._session.layout_count
            template_name = self._config.get(f"templates.photo_{n}")
            if not template_name:
                # Ancienne structure : templates.layout_templates.N
                lt = self._config.get("templates.layout_templates", {})
                template_name = lt.get(n, lt.get(str(n)))
            if not template_name:
                # Valeur par défaut robuste (jamais strip_classic)
                default = self._config.get("templates.default", "")
                template_name = default if default not in ("strip_classic", "strip_4photos", "") \
                                else ("landscape_4photos" if n == 4 else "portrait_1photo")
            logger.info(f"Template selectionne pour {n} photo(s) : '{template_name}' "
                        f"(config keys tries: templates.photo_{n}, templates.layout_templates.{n}, templates.default)")

            self._composer.compose(
                self._session.processed_photos,
                template_name,
                self._session.final_path,
                font_path=self._config.get("app.font_path"),
                title=self._config.get("event.title", ""),
                description=self._config.get("event.description", ""),
                title_size=self._config.get("event.title_font_size"),
                description_size=self._config.get("event.description_font_size"),
            )
            self._session.final_photo = self._session.final_path

            if self._ai.should_apply and self._ai.apply_on == "final_picture":
                self._ui.show_processing("IA : traitement image finale...")
                out = self._ai.process(self._session.final_path, self._session.final_path)
                self._session.final_photo = out

            if self._printer.enabled:
                self._go(State.REVIEW)
            else:
                # Upload géré dans _enter_qr_display pour avoir l'URL réelle avant le QR
                self._go(State.QR_DISPLAY)

        except Exception as e:
            logger.exception("Erreur traitement")
            self._session.error = str(e)
            self._go(State.ERROR)

    def _enter_review(self):
        self._lights.photo_ready()
        self._lights.print_ready()
        self._ui.show_review(self._session.final_photo, printer_enabled=True)

    def _enter_print_wait(self):
        self._lights.print_blink()
        self._ui.show_print_wait()
        threading.Thread(target=self._do_print, daemon=True).start()

    def _do_print(self):
        success = self._printer.print_photo(self._session.final_photo)
        self._ui.show_print_result(success)
        time.sleep(2)
        # Upload géré dans _enter_qr_display
        self._go(State.QR_DISPLAY)

    def _enter_gif_processing(self):
        """Génère le GIF animé depuis les frames brutes, upload, QR code."""
        self._lights.sequence_blink()
        self._ui.show_processing("Création du GIF...")
        threading.Thread(target=self._do_gif_processing, daemon=True).start()

    def _do_gif_processing(self):
        try:
            if not self._gif_maker or not self._gif_maker.enabled:
                logger.error("GifMaker indisponible")
                self._session.error = "Module GIF indisponible"
                self._go(State.ERROR)
                return

            frames = self._session.raw_photos
            gif_path = self._gif_maker.gif_path_for(
                self._session.timestamp, self._session._number
            )
            self._ui.show_processing("Création du GIF...")
            # Crop frames au slot du template correspondant à l'orientation choisie
            n = 4 if self._session.gif_orientation == "landscape" else 1
            tpl_name = self._config.get(f"templates.photo_{n}",
                                        "landscape_4photos" if n == 4 else "portrait_1photo")
            slot = self._composer.first_slot(tpl_name)
            target_ar = (slot["width"] / slot["height"]) if slot else None
            result = self._gif_maker.make_gif(frames, gif_path, target_ar=target_ar)

            if not result:
                self._session.error = "Génération GIF échouée"
                self._go(State.ERROR)
                return

            self._session.gif_path = result

            # Miniature pour le carrousel
            thumb_path = self._gif_maker.thumb_path_for(
                self._session.timestamp, self._session._number
            )
            self._gif_maker.make_thumbnail(result, thumb_path)

            # Utiliser le GIF comme "final_photo" pour l'affichage du résultat
            # (on affiche la première frame via la miniature)
            self._session.final_photo = thumb_path

            self._go(State.QR_DISPLAY)

        except Exception as e:
            logger.exception("Erreur GIF processing")
            self._session.error = str(e)
            self._go(State.ERROR)

    def _enter_qr_display(self):
        """
        1. Upload vers le cloud (synchrone) → obtient l'URL réelle
        2. Génère le QR avec cette URL réelle (pas base_url + filename)
        3. Affiche le résultat avec le bon QR
        """
        self._lights.all_off()
        self._lights.startup_on()

        show_qr  = self._config.get("plugins.qr_on_result", True)
        qr_path  = str(self._session.session_dir / "qrcode.png")
        upload_url = None

        # --- Étape 1 : upload (pendant lequel l'UI montre "Envoi en cours...") ---
        # En mode GIF : uploader le fichier .gif
        if self._uploader.enabled:
            if hasattr(self._ui, 'show_uploading'):
                self._ui.show_uploading()
            try:
                if self._session.is_gif_mode and self._session.gif_path:
                    from pathlib import Path as _P
                    gif_filename = _P(self._session.gif_path).name
                    upload_url   = self._uploader.upload(self._session.gif_path, gif_filename)
                else:
                    upload_url = self._uploader.upload(
                        self._session.final_photo,
                        self._session.final_filename
                    )
                self._session.upload_url = upload_url
                if upload_url:
                    logger.info(f"Upload OK → URL QR : {upload_url}")
                else:
                    logger.warning("Upload a échoué ou retourné None (voir upload_queue)")
            except Exception as e:
                logger.error(f"Upload : {e}")

        # --- Étape 2 : générer le QR ---
        # use_upload_url=true  → URL cloud (Cloudflare R2, etc.) — liens publics
        # use_upload_url=false → URL locale base_url + filename (nginx) — défaut
        # Google Photos productUrl N'EST PAS public → toujours false avec Google Photos
        use_upload_url = self._config.get("qr.use_upload_url", False)

        qr_img = None
        if show_qr:
            if upload_url and use_upload_url:
                # URL directe cloud publique (Cloudflare R2, S3, etc.)
                qr_img = self._qr.generate_from_url(upload_url, qr_path)
                logger.info(f"QR = URL cloud : {upload_url}")
            else:
                # URL locale ou base_url configurée (accessible par tous sur le WiFi)
                qr_img = self._qr.generate(self._session.final_filename, qr_path)
                logger.info("QR = URL locale (base_url + filename)")

            # Dernier recours : charger depuis le PNG déjà sauvegardé
            if qr_img is None and Path(qr_path).exists():
                try:
                    from PIL import Image as _PIL
                    qr_img = _PIL.open(qr_path).convert("RGB")
                    logger.info("QR chargé depuis fichier cache")
                except Exception as e:
                    logger.error(f"Chargement QR cache : {e}")

        # --- Étape 3 : afficher ---
        gif_path = self._session.gif_path if self._session.is_gif_mode else None
        self._ui.show_qr(self._session.final_photo, qr_img, upload_url,
                          gif_path=gif_path)
        self._schedule_return(self._qr.display_duration)

    def _enter_admin(self):
        self._cancel_timer()
        try:
            self._camera.stop_preview()
        except Exception:
            pass
        self._lights.all_off()
        self._lights.startup_on()
        settings = self._build_admin_settings()
        self._ui.show_admin(settings)

    def _build_admin_settings(self) -> dict:
        tpl_names = self._composer.available()
        return {
            # Plugins
            "qr_on_result":    self._config.get("plugins.qr_on_result", True),
            "ai_enabled":      self._config.get("ai.enabled", False),
            "print_enabled":   self._config.get("printing.enabled", False),
            "cloud_enabled":   self._config.get("cloud.enabled", False),
            # Photos
            "option_a":        self._option_a,
            "option_b":        self._option_b,
            "tpl_1":           self._config.get("templates.photo_1", "portrait_1photo"),
            "tpl_2":           self._config.get("templates.photo_2", "portrait_1photo"),
            "tpl_3":           self._config.get("templates.photo_3", "portrait_1photo"),
            "tpl_4":           self._config.get("templates.photo_4", "landscape_4photos"),
            "event_title":      self._config.get("event.title", ""),
            "event_title_size": int(self._config.get("event.title_font_size", 52)),
            "event_description": self._config.get("event.description", ""),
            "event_desc_size":  int(self._config.get("event.description_font_size", 28)),
            # Config générale
            "booth_name":          self._config.get("app.booth_name", "SnapForge"),
            "booth_name_size":     int(self._config.get("app.booth_name_size", 0)),
            "booth_subtitle":      self._config.get("app.booth_subtitle", ""),
            "booth_subtitle_size": int(self._config.get("app.booth_subtitle_size", 0)),
            "countdown":         self._countdown_s,
            # Carrousel
            "carousel_enabled":  self._config.get("home_carousel.enabled", True),
            "carousel_mode":     self._config.get("home_carousel.mode", "table"),
            "carousel_interval": int(self._config.get("home_carousel.interval_seconds", 4)),
            # GIF animé
            "gif_delay_s":   float(self._config.get("gif.delay_between_frames_seconds", 1.0)),
            # Export USB
            "usb_enabled":   bool(self._config.get("usb_export.enabled", False)),
            # Metadata UI
            "_available_templates": tpl_names,
            "_gpio_log":       list(self._gpio_log),
            "_gpio_config": {
                "photo_btn":  self._config.get("gpio.photo_button_pin", 11),
                "print_btn":  self._config.get("gpio.print_button_pin", 13),
                "photo_led":  self._config.get("gpio.photo_led_pin", 7),
                "print_led":  self._config.get("gpio.print_led_pin", 15),
                "startup_led": self._config.get("gpio.startup_led_pin", 29),
                "sequence_led": self._config.get("gpio.sequence_led_pin", 31),
                "flash_led":  self._config.get("gpio.flash_led_pin", 33),
                "bounce_ms":  int(self._config.get("gpio.button_bounce_time", 0.05) * 1000),
            },
        }

    def _apply_admin_settings(self, settings: dict):
        oa = max(1, min(4, int(settings.get("option_a", 1))))
        ob = max(1, min(4, int(settings.get("option_b", 4))))
        if oa == ob:
            ob = 4 if oa != 4 else 1
        self._option_a = oa
        self._option_b = ob
        self._countdown_s = int(settings.get("countdown", 3))

        updates = {
            "photos.option_a":        oa,
            "photos.option_b":        ob,
            "plugins.qr_on_result":   bool(settings.get("qr_on_result", True)),
            "ai.enabled":             bool(settings.get("ai_enabled", False)),
            "printing.enabled":       bool(settings.get("print_enabled", False)),
            "cloud.enabled":          bool(settings.get("cloud_enabled", False)),
            "templates.photo_1":      settings.get("tpl_1", "portrait_1photo"),
            "templates.photo_2":      settings.get("tpl_2", "portrait_1photo"),
            "templates.photo_3":      settings.get("tpl_3", "portrait_1photo"),
            "templates.photo_4":      settings.get("tpl_4", "landscape_4photos"),
            "event.title":                settings.get("event_title", ""),
            "event.title_font_size":      int(settings.get("event_title_size", 52)),
            "event.description":          settings.get("event_description", ""),
            "event.description_font_size": int(settings.get("event_desc_size", 28)),
            "app.booth_name":          settings.get("booth_name", "SnapForge"),
            "app.booth_name_size":     int(settings.get("booth_name_size", 0)),
            "app.booth_subtitle":      settings.get("booth_subtitle", ""),
            "app.booth_subtitle_size": int(settings.get("booth_subtitle_size", 0)),
            "session.countdown_seconds":   self._countdown_s,
            "home_carousel.enabled":       bool(settings.get("carousel_enabled", True)),
            "home_carousel.mode":          settings.get("carousel_mode", "table"),
            "home_carousel.interval_seconds": int(settings.get("carousel_interval", 4)),
            "usb_export.enabled":             bool(settings.get("usb_enabled", False)),
            "gif.delay_between_frames_seconds": float(settings.get("gif_delay_s", 1.0)),
        }
        for key, val in updates.items():
            self._config.set(key, val)

        self._ai._enabled = bool(settings.get("ai_enabled", False))
        self._printer._config_enabled = bool(settings.get("print_enabled", False))
        self._uploader._enabled = bool(settings.get("cloud_enabled", False))

        logger.info(f"Admin applique: options={oa}/{ob} countdown={self._countdown_s}s "
                    f"booth='{settings.get('booth_name')}'")

    def _enter_error(self):
        self._lights.all_off()
        self._lights.startup_on()
        try:
            self._camera.stop_preview()
        except Exception:
            pass
        msg = self._session.error if self._session else "Erreur inconnue"
        self._ui.show_error(msg)
        self._schedule_return(6)

    def _enter_usb_export(self):
        self._lights.all_off()
        self._lights.startup_on()
        self._ui.show_usb_export("Recherche de la clé USB...")
        if self._usb_exporter:
            self._usb_exporter.export(
                status_cb=self._ui.update_usb_status,
                done_cb=self._on_usb_export_done,
            )
        else:
            self._ui.update_usb_status("Export USB non disponible", done=True, success=False)
            self._schedule_return(3)

    def _on_usb_export_done(self, success: bool, message: str):
        self._ui.update_usb_status(message, done=True, success=success)
        self._schedule_return(5)

    # ------------------------------------------------------------------
    # Boutons physiques
    # ------------------------------------------------------------------

    def _log_gpio(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._gpio_log.append(entry)
        logger.debug(f"[GPIO] {entry}")

    def _gif_enabled(self) -> bool:
        return bool(self._config.get("gif.enabled", True) and self._gif_maker)

    def _on_usb_button(self):
        """BTN3 = export USB (PIN 16)."""
        self._log_gpio(f"BTN USB presse (etat={self._state.name})")
        if not self._config.get("usb_export.enabled", False):
            return
        if self._state != State.IDLE:
            logger.info(
                f"Bouton export USB pressé hors écran accueil "
                f"(état={self._state.name}) : action ignorée"
            )
            return
        logger.info("Bouton export USB pressé depuis accueil : vérification clé USB")
        self._go(State.USB_EXPORT)

    def _on_photo_button(self):
        """BTN1 = action principale / gauche."""
        self._log_gpio(f"BTN1 presse (etat={self._state.name})")
        if self._state == State.USB_EXPORT:
            return
        if self._state == State.IDLE:
            # Niveau 1 : Photo ou GIF ?
            self._go(State.CHOOSE_TYPE if self._gif_enabled() else State.CHOOSE_FORMAT)
        elif self._state == State.CHOOSE_TYPE:
            # Photo sélectionné → niveau 2
            self._go(State.CHOOSE_FORMAT)
        elif self._state == State.CHOOSE_FORMAT:
            self._start_session(self._option_a)
        elif self._state == State.CHOOSE_GIF_ORIENTATION:
            # BTN1 = Portrait
            frames = int(self._config.get("gif.frames_count", 6))
            self._start_session(frames, is_gif=True, gif_orientation="portrait")
        elif self._state == State.PREVIEW:
            self._go(State.COUNTDOWN)
        elif self._state == State.REVIEW:
            self._go(State.PRINT_WAIT)
        elif self._state in (State.QR_DISPLAY, State.ERROR):
            self._cancel_timer()
            self._go(State.IDLE)

    def _on_print_button(self):
        """BTN2 = action secondaire / droite."""
        self._log_gpio(f"BTN2 presse (etat={self._state.name})")
        if self._state == State.USB_EXPORT:
            return
        if self._state == State.CHOOSE_TYPE:
            # GIF sélectionné → choisir l'orientation
            self._go(State.CHOOSE_GIF_ORIENTATION)
        elif self._state == State.CHOOSE_GIF_ORIENTATION:
            # BTN2 = Paysage
            frames = int(self._config.get("gif.frames_count", 6))
            self._start_session(frames, is_gif=True, gif_orientation="landscape")
        elif self._state == State.CHOOSE_FORMAT:
            self._start_session(self._option_b)
        elif self._state == State.REVIEW:
            self._go(State.QR_DISPLAY)
        elif self._state == State.QR_DISPLAY:
            self._cancel_timer()
            self._go(State.IDLE)

    # ------------------------------------------------------------------
    # Touchscreen
    # ------------------------------------------------------------------

    def handle_touch(self, action: str, data=None):
        logger.debug(f"[TOUCH] {action} etat={self._state.name}")

        if action == "open_admin":
            if self._state != State.ADMIN:
                self._go(State.ADMIN)
            return

        if action == "open_choose_type":
            if self._state == State.IDLE:
                self._go(State.CHOOSE_TYPE if self._gif_enabled() else State.CHOOSE_FORMAT)
            return

        if action == "open_choose_format":
            if self._state in (State.IDLE, State.CHOOSE_TYPE):
                self._go(State.CHOOSE_FORMAT)
            return

        if action == "back_to_choose_type":
            if self._state == State.CHOOSE_FORMAT:
                self._go(State.CHOOSE_TYPE if self._gif_enabled() else State.IDLE)
            elif self._state == State.CHOOSE_GIF_ORIENTATION:
                self._go(State.CHOOSE_TYPE)
            return

        if action == "admin_save":
            if self._state == State.ADMIN and isinstance(data, dict):
                self._apply_admin_settings(data)
                self._config.save()
                self._go(State.IDLE)
            return

        if action == "admin_cancel":
            if self._state == State.ADMIN:
                self._go(State.IDLE)
            return

        if action == "start_session":
            if self._state in (State.IDLE, State.CHOOSE_FORMAT):
                count = data if isinstance(data, int) else self._option_a
                self._start_session(count)

        elif action == "start_gif":
            if self._state in (State.IDLE, State.CHOOSE_FORMAT, State.CHOOSE_TYPE):
                self._go(State.CHOOSE_GIF_ORIENTATION)

        elif action == "gif_portrait":
            if self._state == State.CHOOSE_GIF_ORIENTATION:
                frames = int(self._config.get("gif.frames_count", 6))
                self._start_session(frames, is_gif=True, gif_orientation="portrait")

        elif action == "gif_landscape":
            if self._state == State.CHOOSE_GIF_ORIENTATION:
                frames = int(self._config.get("gif.frames_count", 6))
                self._start_session(frames, is_gif=True, gif_orientation="landscape")

        elif action == "start_countdown":
            if self._state == State.PREVIEW:
                self._go(State.COUNTDOWN)

        elif action == "confirm_print":
            if self._state == State.REVIEW:
                self._go(State.PRINT_WAIT)

        elif action == "skip_print":
            if self._state == State.REVIEW:
                threading.Thread(target=self._do_upload, daemon=True).start()
                self._go(State.QR_DISPLAY)

        elif action == "confirm_reset":
            if self._state == State.ADMIN:
                self._ui.show_reset_progress("Remise à zéro en cours...")
                threading.Thread(target=self._do_reset_event, daemon=True).start()

        elif action == "return_idle":
            self._cancel_timer()
            self._go(State.IDLE)

        elif action == "quit_app":
            logger.info("Fermeture propre demandee depuis le menu admin")
            self.stop()
            self._ui.stop()

    # ------------------------------------------------------------------

    def _do_reset_event(self):
        """Remet SnapForge à zéro pour un nouvel événement."""
        logger.info("Remise à zéro demandée — confirmation validée")

        # 1. Sauvegarde horodatée de la config
        config_path = Path("config.yaml")
        if config_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = Path(f"config_backup_{ts}.yaml")
            try:
                shutil.copy2(config_path, backup)
                logger.info(f"Sauvegarde config : {backup}")
            except Exception as e:
                logger.warning(f"Sauvegarde config impossible : {e}")

        # 2. Suppression des photos et médias
        dirs = [
            ("photos.final_dir",    "Photo/final",      "photos finales"),
            ("photos.raw_dir",      "Photo/raw",        "photos originales"),
            ("gif.output_dir",      "Photo/gifs",       "GIF animés"),
            ("gif.thumbnails_dir",  "Photo/thumbnails", "miniatures"),
        ]
        for key, default, label in dirs:
            path = Path(self._config.get(key, default))
            n = _clear_dir(path)
            logger.info(f"Suppression {label} : {n} élément(s) supprimé(s) dans {path}")

        # 3. Réinitialisation des textes et tailles
        resets = {
            "event.title":                "",
            "event.description":          "",
            "event.title_font_size":      69,
            "event.description_font_size": 35,
            "app.booth_name":             "SnapForge",
            "app.booth_subtitle":         "",
            "app.booth_name_size":        0,
            "app.booth_subtitle_size":    0,
        }
        for key, val in resets.items():
            self._config.set(key, val)
        logger.info("Réinitialisation titre/description/noms terminée")

        # 4. Sauvegarde de la config réinitialisée
        self._config.save()
        logger.info("Remise à zéro terminée")

        self._ui.update_reset_progress("Remise à zéro terminée", done=True)
        time.sleep(2.5)
        self._go(State.IDLE)

    def _start_session(self, layout_count: int, is_gif: bool = False,
                       gif_orientation: str = "portrait"):
        self._session = Session(layout_count, self._raw_dir, self._final_dir,
                                is_gif_mode=is_gif, gif_orientation=gif_orientation)
        self._go(State.PREVIEW)

    def _schedule_return(self, delay: float):
        self._cancel_timer()
        self._return_timer = threading.Timer(delay, lambda: self._go(State.IDLE))
        self._return_timer.daemon = True
        self._return_timer.start()

    def _cancel_timer(self):
        if self._return_timer:
            self._return_timer.cancel()
            self._return_timer = None

    def _reset_inactivity(self):
        self._cancel_inactivity()
        self._inactivity_timer = threading.Timer(
            self._inactivity_timeout, self._on_inactivity
        )
        self._inactivity_timer.daemon = True
        self._inactivity_timer.start()

    def _cancel_inactivity(self):
        if self._inactivity_timer:
            self._inactivity_timer.cancel()
            self._inactivity_timer = None

    def _on_inactivity(self):
        if self._state in _INACTIVITY_STATES:
            logger.info(
                f"[FSM] Inactivite {self._inactivity_timeout:.0f}s -> retour IDLE "
                f"(depuis {self._state.name})"
            )
            self._go(State.IDLE)

    def _on_user_activity(self):
        """Appelé par l'UI à chaque interaction (clic/touche/tactile)."""
        if self._state in _INACTIVITY_STATES:
            self._reset_inactivity()

    @property
    def state(self) -> State:
        return self._state
