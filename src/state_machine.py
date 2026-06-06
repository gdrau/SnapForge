import logging
import threading
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    CHOOSE_FORMAT = auto()
    PREVIEW = auto()
    COUNTDOWN = auto()
    CAPTURE = auto()
    PROCESSING = auto()
    REVIEW = auto()
    PRINT_WAIT = auto()
    UPLOADING = auto()
    QR_DISPLAY = auto()
    ADMIN = auto()
    ERROR = auto()


class Session:
    """Données d'une session de capture."""

    def __init__(self, layout_count: int, raw_dir: str, final_dir: str):
        self.layout_count = layout_count
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = Path(raw_dir) / self.timestamp
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.final_dir = Path(final_dir)
        self.final_dir.mkdir(parents=True, exist_ok=True)

        # Numéro séquentiel basé sur les fichiers existants
        existing = len(list(self.final_dir.glob("photobooth_*.jpg")))
        self._number = existing + 1

        self.raw_photos: List[str] = []
        self.processed_photos: List[str] = []
        self.final_photo: Optional[str] = None
        self.upload_url: Optional[str] = None
        self.error: Optional[str] = None

    @property
    def final_filename(self) -> str:
        return f"photobooth_{self._number:04d}_{self.timestamp}.jpg"

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
                 uploader, printer, qr_gen, ui):
        self._config = config
        self._camera = camera
        self._lights = lights
        self._buttons = buttons
        self._composer = composer
        self._ai = ai_processor
        self._uploader = uploader
        self._printer = printer
        self._qr = qr_gen
        self._ui = ui

        self._state = State.IDLE
        self._session: Optional[Session] = None
        self._return_timer: Optional[threading.Timer] = None

        self._available_layouts: List[int] = config.get("photos.available_layouts", [1, 4])
        self._default_layout: int = config.get("photos.default_layout", self._available_layouts[0])
        self._countdown_s: int = config.get("camera.countdown_seconds", 3)
        self._template: str = config.get("templates.default", "strip_classic")
        self._font_path: Optional[str] = config.get("app.font_path")
        self._raw_dir: str = config.get("photos.raw_dir", "Photo/raw")
        self._final_dir: str = config.get("photos.final_dir", "Photo/final")

    def start(self):
        self._buttons.on_photo_button(self._on_photo_button)
        self._buttons.on_print_button(self._on_print_button)
        self._lights.startup_on()
        self._go(State.IDLE)

    def stop(self):
        self._cancel_timer()
        self._lights.all_off()
        try:
            self._camera.stop_preview()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Machine d'états
    # ------------------------------------------------------------------

    def _go(self, state: State):
        logger.info(f"[FSM] {self._state.name} -> {state.name}")
        self._state = state
        {
            State.IDLE:          self._enter_idle,
            State.CHOOSE_FORMAT: self._enter_choose_format,
            State.PREVIEW:       self._enter_preview,
            State.COUNTDOWN:     self._enter_countdown,
            State.CAPTURE:       self._enter_capture,
            State.PROCESSING:    self._enter_processing,
            State.REVIEW:        self._enter_review,
            State.PRINT_WAIT:    self._enter_print_wait,
            State.UPLOADING:     self._enter_uploading,
            State.QR_DISPLAY:    self._enter_qr_display,
            State.ADMIN:         self._enter_admin,
            State.ERROR:         self._enter_error,
        }[state]()

    # --- IDLE ---

    def _enter_idle(self):
        self._session = None
        self._lights.all_off()
        self._lights.startup_on()
        self._lights.photo_ready()
        self._ui.show_idle()

    # --- CHOOSE_FORMAT ---

    def _enter_choose_format(self):
        self._lights.sequence_blink()
        self._ui.show_choose_format(self._available_layouts, self._default_layout)

    # --- PREVIEW ---

    def _enter_preview(self):
        self._lights.sequence_on()
        self._ui.show_preview(self._session.layout_count, self._session.remaining)
        self._camera.start_preview(self._ui.update_preview_frame)

    # --- COUNTDOWN ---

    def _enter_countdown(self):
        self._lights.sequence_blink()
        threading.Thread(target=self._run_countdown, daemon=True).start()

    def _run_countdown(self):
        for i in range(self._countdown_s, 0, -1):
            self._ui.show_countdown(i)
            time.sleep(1)
        self._go(State.CAPTURE)

    # --- CAPTURE ---

    def _enter_capture(self):
        path = self._session.next_raw_path()
        self._lights.flash_async()
        threading.Thread(target=self._do_capture, args=(path,), daemon=True).start()

    def _do_capture(self, path: str):
        try:
            self._camera.capture(path)
            self._session.raw_photos.append(path)
            n = len(self._session.raw_photos)
            logger.info(f"Photo {n}/{self._session.layout_count} : {path}")
            self._ui.show_capture_result(path, self._session.remaining)
            time.sleep(0.8)

            if self._session.is_complete:
                self._camera.stop_preview()
                self._go(State.PROCESSING)
            else:
                self._go(State.COUNTDOWN)
        except Exception as e:
            logger.exception("Erreur capture")
            self._session.error = str(e)
            self._go(State.ERROR)

    # --- PROCESSING ---

    def _enter_processing(self):
        self._lights.sequence_blink()
        self._ui.show_processing("Assemblage en cours...")
        threading.Thread(target=self._do_processing, daemon=True).start()

    def _do_processing(self):
        try:
            photos = self._session.raw_photos

            if self._ai.should_apply and self._ai.apply_on == "raw_photo":
                self._ui.show_processing("IA : remplacement de fond...")
                processed = [self._ai.process(p) for p in photos]
                self._session.processed_photos = processed
            else:
                self._session.processed_photos = photos

            self._ui.show_processing("Composition de l'image...")
            self._composer.compose(
                self._session.processed_photos,
                self._template,
                self._session.final_path,
                font_path=self._font_path,
            )
            self._session.final_photo = self._session.final_path

            if self._ai.should_apply and self._ai.apply_on == "final_picture":
                self._ui.show_processing("IA : traitement image finale...")
                out = self._ai.process(self._session.final_path, self._session.final_path)
                self._session.final_photo = out

            self._go(State.REVIEW)
        except Exception as e:
            logger.exception("Erreur traitement")
            self._session.error = str(e)
            self._go(State.ERROR)

    # --- REVIEW ---

    def _enter_review(self):
        self._lights.photo_ready()
        if self._printer.enabled:
            self._lights.print_ready()
        self._ui.show_review(self._session.final_photo, printer_enabled=self._printer.enabled)

    # --- PRINT_WAIT ---

    def _enter_print_wait(self):
        self._lights.print_blink()
        self._ui.show_print_wait()
        threading.Thread(target=self._do_print, daemon=True).start()

    def _do_print(self):
        success = self._printer.print_photo(self._session.final_photo)
        self._ui.show_print_result(success)
        time.sleep(2)
        self._go(State.UPLOADING)

    # --- UPLOADING ---

    def _enter_uploading(self):
        self._lights.sequence_blink()
        self._ui.show_uploading()
        threading.Thread(target=self._do_upload, daemon=True).start()

    def _do_upload(self):
        try:
            url = self._uploader.upload(
                self._session.final_photo, self._session.final_filename
            )
            self._session.upload_url = url
        except Exception as e:
            logger.error(f"Upload: {e}")
        self._go(State.QR_DISPLAY)

    # --- QR_DISPLAY ---

    def _enter_qr_display(self):
        self._lights.all_off()
        self._lights.startup_on()
        qr_img = self._qr.generate(
            self._session.final_filename,
            str(self._session.session_dir / "qrcode.png"),
        )
        self._ui.show_qr(self._session.final_photo, qr_img, self._session.upload_url)
        self._schedule_return(self._qr.display_duration)

    # --- ADMIN ---

    def _enter_admin(self):
        self._cancel_timer()
        try:
            self._camera.stop_preview()
        except Exception:
            pass
        self._lights.all_off()
        self._lights.startup_on()
        self._ui.show_admin(self._build_admin_settings())

    def _build_admin_settings(self) -> dict:
        return {
            'layout_a': self._available_layouts[0] if len(self._available_layouts) > 0 else 1,
            'layout_b': self._available_layouts[-1] if len(self._available_layouts) > 1 else 4,
            'ai_enabled':    self._config.get('ai.enabled', False),
            'print_enabled': self._config.get('printing.enabled', False),
            'cloud_enabled': self._config.get('cloud.enabled', False),
            'countdown':     self._countdown_s,
            'template':      self._template,
        }

    def _apply_admin_settings(self, settings: dict):
        la = int(settings.get('layout_a', 1))
        lb = int(settings.get('layout_b', 4))
        # S'assurer que les 2 options sont différentes
        if la == lb:
            lb = 4 if la != 4 else 1
        self._available_layouts = sorted({la, lb})
        self._default_layout = self._available_layouts[0]

        self._countdown_s = int(settings.get('countdown', 3))
        self._template = settings.get('template', self._template)

        # Mettre à jour la config en mémoire
        self._config.set('photos.available_layouts', self._available_layouts)
        self._config.set('photos.default_layout', self._default_layout)
        self._config.set('ai.enabled', bool(settings.get('ai_enabled', False)))
        self._config.set('printing.enabled', bool(settings.get('print_enabled', False)))
        self._config.set('cloud.enabled', bool(settings.get('cloud_enabled', False)))
        self._config.set('camera.countdown_seconds', self._countdown_s)

        # Mettre à jour les modules
        self._ai._enabled = bool(settings.get('ai_enabled', False))
        self._printer._config_enabled = bool(settings.get('print_enabled', False))
        self._uploader._enabled = bool(settings.get('cloud_enabled', False))

        logger.info(f"Admin: layouts={self._available_layouts} IA={settings.get('ai_enabled')} "
                    f"print={settings.get('print_enabled')} cloud={settings.get('cloud_enabled')}")

    # --- ERROR ---

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

    # ------------------------------------------------------------------
    # Handlers boutons physiques
    # ------------------------------------------------------------------

    def _on_photo_button(self):
        """
        Bouton 1 (photo) = action principale ou option GAUCHE.

        Règle écran par écran :
          IDLE          -> 1 bouton visible -> démarre le choix de format
          CHOOSE_FORMAT -> 2 options       -> sélectionne la 1re option (gauche)
          PREVIEW       -> 1 bouton        -> lance le compte à rebours
          REVIEW        -> 1 ou 2 boutons  -> imprime (si printer) OU continue
          QR_DISPLAY    -> 1 bouton        -> retour accueil
          ERROR         -> retour accueil immédiat
        """
        logger.debug(f"[BTN1] etat={self._state.name}")
        if self._state == State.IDLE:
            self._go(State.CHOOSE_FORMAT)
        elif self._state == State.CHOOSE_FORMAT:
            # Option gauche = 1re option de la liste
            self._start_session(self._available_layouts[0])
        elif self._state == State.PREVIEW:
            self._go(State.COUNTDOWN)
        elif self._state == State.REVIEW:
            if self._printer.enabled:
                self._go(State.PRINT_WAIT)   # bouton gauche = IMPRIMER
            else:
                self._go(State.UPLOADING)    # seul bouton = CONTINUER
        elif self._state in (State.QR_DISPLAY, State.ERROR):
            self._cancel_timer()
            self._go(State.IDLE)

    def _on_print_button(self):
        """
        Bouton 2 (print) = action secondaire ou option DROITE.

        Règle écran par écran :
          CHOOSE_FORMAT -> 2 options      -> sélectionne la 2e option (droite)
          REVIEW        -> 2 boutons      -> continue sans imprimer (droite)
          QR_DISPLAY    -> retour accueil (même que bouton 1)
          Autres        -> ignoré si 1 seul bouton visible
        """
        logger.debug(f"[BTN2] etat={self._state.name}")
        if self._state == State.CHOOSE_FORMAT:
            # Option droite = dernière option de la liste
            self._start_session(self._available_layouts[-1])
        elif self._state == State.REVIEW and self._printer.enabled:
            self._go(State.UPLOADING)    # bouton droit = CONTINUER sans imprimer
        elif self._state == State.QR_DISPLAY:
            self._cancel_timer()
            self._go(State.IDLE)

    # ------------------------------------------------------------------
    # Touchscreen / clavier
    # ------------------------------------------------------------------

    def handle_touch(self, action: str, data=None):
        logger.debug(f"[TOUCH] {action} data={data} etat={self._state.name}")

        if action == "open_admin":
            if self._state != State.ADMIN:
                self._go(State.ADMIN)
            return

        if action == "open_choose_format":
            if self._state == State.IDLE:
                self._go(State.CHOOSE_FORMAT)
            return

        if action == "admin_change":
            # Mise à jour live de l'affichage admin sans sauvegarder
            if self._state == State.ADMIN and isinstance(data, dict):
                self._ui.show_admin(data)
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
                count = data if isinstance(data, int) else self._default_layout
                self._start_session(count)

        elif action == "select_format":
            if self._state == State.CHOOSE_FORMAT and isinstance(data, int):
                self._default_layout = data
                self._ui.update_format_selection(data)

        elif action == "start_countdown":
            if self._state == State.PREVIEW:
                self._go(State.COUNTDOWN)

        elif action == "confirm_print":
            if self._state == State.REVIEW and self._printer.enabled:
                self._go(State.PRINT_WAIT)

        elif action == "skip_print":
            if self._state == State.REVIEW:
                self._go(State.UPLOADING)

        elif action == "return_idle":
            self._cancel_timer()
            self._go(State.IDLE)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _start_session(self, layout_count: int):
        self._session = Session(layout_count, self._raw_dir, self._final_dir)
        self._go(State.PREVIEW)

    def _schedule_return(self, delay: float):
        self._cancel_timer()
        self._return_timer = threading.Timer(delay, self._auto_return)
        self._return_timer.daemon = True
        self._return_timer.start()

    def _auto_return(self):
        self._go(State.IDLE)

    def _cancel_timer(self):
        if self._return_timer:
            self._return_timer.cancel()
            self._return_timer = None

    @property
    def state(self) -> State:
        return self._state
