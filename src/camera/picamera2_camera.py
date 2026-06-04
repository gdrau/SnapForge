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
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            t = frame_count % 256
            frame[:, :, 0] = t
            frame[:, :, 1] = 100
            frame[:, :, 2] = 255 - t
            # Texte simulé
            frame[h // 2 - 2 : h // 2 + 2, w // 3 : w * 2 // 3] = 255
            if self._callback:
                self._callback(frame)
            time.sleep(1 / 30)
            frame_count += 1

    def stop_preview(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def capture(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        w = self._config.get("camera.resolution_width", 3280)
        h = self._config.get("camera.resolution_height", 2464)
        if _PIL_AVAILABLE:
            import random
            img = Image.new("RGB", (w, h), (140, 160, 200))
            draw = ImageDraw.Draw(img)
            for _ in range(15):
                x, y = random.randint(0, w), random.randint(0, h)
                r = random.randint(20, 180)
                c = (random.randint(100, 255), random.randint(80, 200), random.randint(80, 200))
                draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
            draw.text((w // 2 - 100, h // 2), "PHOTO SIMULÉE", fill=(255, 255, 255))
            quality = self._config.get("processing.jpeg_quality", 92)
            img.save(output_path, quality=quality)
        else:
            # Fallback brut sans PIL
            with open(output_path, "wb") as f:
                f.write(b"")
        logger.info(f"MockCamera: capture -> {output_path}")
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
        self._init()

    def _init(self):
        try:
            self._cam = Picamera2()
            pw = self._config.get("camera.preview_width", 800)
            ph = self._config.get("camera.preview_height", 480)
            cw = self._config.get("camera.resolution_width", 3280)
            ch = self._config.get("camera.resolution_height", 2464)

            # Configuration preview + buffer haute résolution
            cfg = self._cam.create_preview_configuration(
                main={"size": (pw, ph), "format": "RGB888"},
                raw={"size": (cw, ch)},
            )
            self._cam.configure(cfg)

            flip_h = int(self._config.get("camera.flip_horizontal", False))
            flip_v = int(self._config.get("camera.flip_vertical", False))
            if flip_h or flip_v:
                import libcamera
                self._cam.camera_configuration()["transform"] = libcamera.Transform(
                    hflip=flip_h, vflip=flip_v
                )

            self._cam.start()
            time.sleep(2.0)  # Chauffe capteur + AE
            logger.info("Picamera2 initialisée")
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

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cw = self._config.get("camera.resolution_width", 3280)
        ch = self._config.get("camera.resolution_height", 2464)

        # Bascule en mode still haute résolution, capture, revient en preview
        still_cfg = self._cam.create_still_configuration(
            main={"size": (cw, ch), "format": "RGB888"}
        )
        self._cam.switch_mode_and_capture_file(still_cfg, output_path)
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
