import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from gpiozero import Button
    _GPIO_AVAILABLE = True
except Exception:
    _GPIO_AVAILABLE = False
    logger.warning("gpiozero indisponible - boutons GPIO simules (mode developpement)")


class PhysicalButton:

    def __init__(self, pin: int, bounce_time: float = 0.05):
        self.pin = pin
        self._button = None
        self._callback: Optional[Callable] = None
        self._press_time: float = 0.0

        if _GPIO_AVAILABLE:
            try:
                self._button = Button(f"BOARD{pin}", bounce_time=bounce_time)
                self._button.when_pressed = self._handle_press
                logger.info(f"Bouton BOARD{pin} initialise (bounce={bounce_time}s)")
            except Exception as e:
                logger.error(f"Erreur init bouton BOARD{pin}: {e}")

    def _handle_press(self):
        now = time.monotonic()
        self._press_time = now
        logger.debug(f"[GPIO] BOARD{self.pin} presse a t={now:.4f}")
        if self._callback:
            # Appel direct dans le thread gpiozero (ne pas creer de thread supplementaire)
            t0 = time.monotonic()
            self._callback()
            elapsed = (time.monotonic() - t0) * 1000
            logger.debug(f"[GPIO] BOARD{self.pin} callback execute en {elapsed:.1f}ms")

    def on_press(self, callback: Callable):
        self._callback = callback

    def is_pressed(self) -> bool:
        return self._button.is_pressed if self._button else False

    def close(self):
        if self._button:
            try:
                self._button.close()
            except Exception:
                pass


class ButtonManager:

    def __init__(self, config):
        self._enabled = config.get("gpio.enabled", True)
        self._buttons: dict = {}

        if self._enabled:
            bounce = config.get("gpio.button_bounce_time", 0.05)
            self._buttons["photo"] = PhysicalButton(
                config.get("gpio.photo_button_pin", 11), bounce
            )
            self._buttons["print"] = PhysicalButton(
                config.get("gpio.print_button_pin", 13), bounce
            )
            self._buttons["usb"] = PhysicalButton(
                config.get("usb_export.button_pin", 16), bounce
            )

    def on_photo_button(self, cb: Callable):
        if "photo" in self._buttons:
            self._buttons["photo"].on_press(cb)

    def on_print_button(self, cb: Callable):
        if "print" in self._buttons:
            self._buttons["print"].on_press(cb)

    def on_usb_button(self, cb: Callable):
        if "usb" in self._buttons:
            self._buttons["usb"].on_press(cb)

    def close(self):
        for b in self._buttons.values():
            b.close()
