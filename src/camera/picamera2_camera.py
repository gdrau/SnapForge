import logging
import time
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    _PICAMERA2_AVAILABLE = True
except ImportError:
    _PICAMERA2_AVAILABLE = False
    logger.warning("Picamera2 indisponible - utilisation de la caméra simulée")

try:
    from PIL import Image, ImageDraw
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Caméra simulée (développement sans Raspberry Pi)
# ---------------------------------------------------------------------------

class MockCamera:

    def __init__(self, config):
        self._config = config
        self._callback: Optional[Callable] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        logger.info("MockCamera initialisée")

    def start_preview(self, callback: Callable):
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        w = self._config.get("camera.preview_width", 800)
        h = self._config.get("camera.preview_height", 480)
        frame_count = 0
        while self._running:
            # Preview simulé : fond gris avec texte "MODE PC - PAS DE CAMERA"
            frame = np.full((h, w, 3), 45, dtype=np.uint8)          # fond gris sombre
            # Bande centrale plus claire pour indiquer la zone photo
            frame[h//4:h*3//4, w//6:w*5//6] = 70
            # Bordure blanche de la zone photo
            frame[h//4:h//4+3, w//6:w*5//6] = 200
            frame[h*3//4-3:h*3//4, w//6:w*5//6] = 200
            frame[h//4:h*3//4, w//6:w//6+3] = 200
            frame[h//4:h*3//4, w*5//6-3:w*5//6] = 200
            # Animation simple (barre qui se déplace)
            bar_x = int((frame_count * 4) % (w * 5 // 3 - w // 6)) + w // 6
            bar_x = min(bar_x, w * 5 // 6)
            frame[h//2 - 1:h//2 + 1, max(w//6, bar_x - 20):min(w*5//6, bar_x)] = 180
            if self._callback:
                self._callback(frame)
            time.sleep(1 / 30)
            frame_count += 1

    def stop_preview(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def capture(self, output_path: str) -> str:
        """Simulated capture."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        w = self._config.get("camera.resolution_width", 3280)
        h = self._config.get("camera.resolution_height", 2464)
        if _PIL_AVAILABLE:
            # Photo gris neutre avec encadré et texte — ressemble à une photo manquante
            img = Image.new("RGB", (w, h), (80, 80, 80))
            draw = ImageDraw.Draw(img)
            # Rectangle central blanc simulant un sujet
            mx, my = w // 2, h // 2
            rw, rh = int(w * 0.35), int(h * 0.55)
            draw.rectangle([mx - rw, my - rh, mx + rw, my + rh], fill=(200, 200, 200), outline=(255, 255, 255), width=8)
            # Cercle "tête" simulé
            draw.ellipse([mx - rw // 3, my - rh + 60, mx + rw // 3, my - rh + 60 + rw * 2 // 3],
                         fill=(220, 220, 220), outline=(255, 255, 255), width=6)
            # Texte d'identification
            font_size = max(w // 25, 40)
            try:
                from PIL import ImageFont
                for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                             "C:/Windows/Fonts/arial.ttf"):
                    if Path(path).exists():
                        font = ImageFont.truetype(path, font_size)
                        break
                else:
                    font = ImageFont.load_default()
            except Exception:
                font = None
            label = "PHOTO SIMULEE - MODE PC"
            draw.text((mx, my + rh + 60), label, fill=(255, 255, 255), font=font, anchor="mm" if font else None)
            quality = self._config.get("processing.jpeg_quality", 92)
            img.save(output_path, quality=quality)
        else:
            with open(output_path, "wb") as f:
                f.write(b"")
        logger.info(f"MockCamera: capture simulee -> {output_path}")
        return output_path

    def close(self):
        self.stop_preview()


# ---------------------------------------------------------------------------
# Caméra réelle Picamera2
# ---------------------------------------------------------------------------

class Picamera2Camera:

    def __init__(self, config):
        self._config = config
        self._cam: Optional[Picamera2] = None
        self._callback: Optional[Callable] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._manual_exposure = bool(config.get("camera.manual_exposure", False))
        self._init()

    def _init(self):
        try:
            self._cam = Picamera2()
            pw = self._config.get("camera.preview_width", 800)
            ph = self._config.get("camera.preview_height", 480)

            cw = self._config.get("camera.resolution_width", 3280)
            ch = self._config.get("camera.resolution_height", 2464)

            flip_h = int(self._config.get("camera.flip_horizontal", False))
            flip_v = int(self._config.get("camera.flip_vertical", False))
            self._transform = None
            if flip_h or flip_v:
                import libcamera
                self._transform = libcamera.Transform(hflip=flip_h, vflip=flip_v)

            # Config preview avec flux RAW à la résolution native du capteur.
            # L'AE/AWB utilise le flux RAW pour calculer l'exposition correcte.
            cfg_kwargs = {"transform": self._transform} if self._transform else {}
            cfg = self._cam.create_preview_configuration(
                main={"size": (pw, ph), "format": "RGB888"},
                raw={"size": (cw, ch)},
                **cfg_kwargs
            )
            self._cam.configure(cfg)
            self._cam.start()

            # Contrôles ISP post-démarrage
            controls = {}
            # Netteté
            sharpness = float(self._config.get("camera.sharpness", 1.0))
            if sharpness != 1.0:
                controls["Sharpness"] = sharpness
            # Débruitage : 0=désactivé 1=rapide 2=haute qualité
            nr_mode = int(self._config.get("camera.noise_reduction_mode", 1))
            controls["NoiseReductionMode"] = nr_mode
            # Contraste
            contrast = float(self._config.get("camera.contrast", 1.0))
            if contrast != 1.0:
                controls["Contrast"] = contrast
            # Saturation
            saturation = float(self._config.get("camera.saturation", 1.0))
            if saturation != 1.0:
                controls["Saturation"] = saturation
            # Luminosité
            brightness = float(self._config.get("camera.brightness", 0.0))
            if brightness != 0.0:
                controls["Brightness"] = brightness
            # Compensation d'exposition (EV)
            ev = float(self._config.get("camera.exposure_value", 0.0))
            if ev != 0.0:
                controls["ExposureValue"] = ev
            if controls:
                try:
                    self._cam.set_controls(controls)
                except Exception as e:
                    logger.warning(f"Contrôles ISP non supportés : {e}")

            # Exposition manuelle (désactive l'AE automatique si configuré)
            if self._manual_exposure:
                et = int(self._config.get("camera.exposure_time_us", 100000))
                ag = float(self._config.get("camera.analogue_gain", 1.0))
                try:
                    self._cam.set_controls({
                        "AeEnable":     False,
                        "ExposureTime": et,
                        "AnalogueGain": ag,
                    })
                    logger.info(f"Exposition manuelle : {et}µs  gain={ag:.1f} (≈ISO {int(ag*100)})")
                except Exception as e:
                    logger.warning(f"Exposition manuelle non supportée : {e}")

            time.sleep(2.0)  # Laisser le temps au pipeline ISP de stabiliser

            # Vérification : une frame doit arriver dans les 2 secondes suivantes
            # Si la caméra a eu un timeout Unicam, elle devrait s'être rétablie ici
            try:
                test = self._cam.capture_array()
                h, w = test.shape[:2]
                logger.info(f"Picamera2 initialisee et operationnelle ({w}x{h}px)")
            except Exception as test_err:
                logger.warning(
                    f"ATTENTION : premiere frame non recue ({test_err})\n"
                    "  → Verifier le cable nappe de la camera (les deux extremites)\n"
                    "  → Tester independamment : libcamera-hello --timeout 5000"
                )
                # Ne pas abandonner ici — la camera peut quand meme fonctionner
                logger.info("Picamera2 initialisee (avec avertissement cable)")

        except Exception as e:
            logger.error(f"Erreur init Picamera2: {e}")
            self._cam = None

    def start_preview(self, callback: Callable):
        if not self._cam:
            return
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running and self._cam:
            try:
                frame = self._cam.capture_array()
                if self._callback:
                    # Picamera2 livre souvent les frames en BGR malgré le format "RGB888"
                    # (quirk du pipeline VC4) — swap R↔B pour un affichage correct
                    # La capture fichier (JPEG) n'est pas affectée par ce swap
                    if frame is not None and frame.ndim == 3 and frame.shape[2] == 3:
                        frame = frame[:, :, ::-1].copy()
                    self._callback(frame)
            except Exception as e:
                logger.error(f"Erreur preview: {e}")
                time.sleep(0.05)

    def stop_preview(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def capture(self, output_path: str) -> str:
        if not self._cam:
            raise RuntimeError("Caméra non initialisée")

        ae_lock  = bool(self._config.get("camera.ae_lock_before_capture", False))
        ae_delay = float(self._config.get("camera.ae_lock_delay", 0.2))
        _ae_was_locked = False

        # 1. Verrouiller AE/AWB PENDANT que la preview tourne encore
        #    (capture_metadata() donne les réglages auto actuels du pipeline ISP)
        #    Sans objet si exposition manuelle (AeEnable déjà False en permanence)
        if ae_lock and not self._manual_exposure:
            try:
                meta = self._cam.capture_metadata()
                lock = {"AeEnable": False, "AwbEnable": False}
                et = meta.get("ExposureTime")
                ag = meta.get("AnalogueGain")
                cg = meta.get("ColourGains")
                if et:
                    lock["ExposureTime"] = int(et)
                if ag:
                    lock["AnalogueGain"] = float(ag)
                if cg and len(cg) >= 2:
                    lock["ColourGains"] = (float(cg[0]), float(cg[1]))
                self._cam.set_controls(lock)
                time.sleep(ae_delay)   # laisser l'ISP appliquer les valeurs
                _ae_was_locked = True
                logger.debug(f"AE/AWB verrouillés — ET={et}µs  AG={ag:.2f}  WB={cg}")
            except Exception as e:
                logger.warning(f"AE/AWB lock non bloquant : {e}")

        # 2. Arrêter la boucle preview AVANT la capture pour éviter la race condition
        #    (la boucle appelle capture_array() pendant que switch_mode change la config
        #     → corrompt le pipeline ISP après plusieurs sessions)
        was_running = self._running
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cw = self._config.get("camera.resolution_width", 3280)
        ch = self._config.get("camera.resolution_height", 2464)

        try:
            still_kwargs = {"transform": self._transform} if self._transform else {}
            still_cfg = self._cam.create_still_configuration(
                main={"size": (cw, ch), "format": "RGB888"},
                **still_kwargs
            )
            self._cam.switch_mode_and_capture_file(still_cfg, output_path)

        except Exception as e:
            logger.error(f"Erreur capture : {e}")
            raise

        finally:
            # 3. Réactiver AE/AWB pour le retour en preview
            if _ae_was_locked:
                try:
                    self._cam.set_controls({"AeEnable": True, "AwbEnable": True})
                except Exception:
                    pass
            # Toujours redémarrer la boucle preview (même en cas d'erreur)
            if was_running and self._callback:
                self._running = True
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()

        logger.info(f"Capture -> {output_path}")
        return output_path

    def close(self):
        self.stop_preview()
        if self._cam:
            try:
                self._cam.stop()
                self._cam.close()
            except Exception as e:
                logger.error(f"Erreur fermeture caméra: {e}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_camera(config):
    if _PICAMERA2_AVAILABLE:
        return Picamera2Camera(config)
    logger.warning("Picamera2 absente - utilisation de la caméra simulée")
    return MockCamera(config)
