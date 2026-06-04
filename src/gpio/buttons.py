import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from gpiozero import Button
    _GPIO_AVAILABLE = True
except Exception:
    _GPIO_AVAILABLE = False
    logger.warning("gpiozero indisponible - boutons GPIO simulés (mode développement)")


class PhysicalButton:

    def __init__(self, pin: int, bounce_time: float = 0.3):
        self.pin = pin
        self._button = None
        self._callback: Optional[Callable] = None

        if _GPIO_AVAILABLE:
            try:
                # gpiozero accepte "BOARD<n>" pour la numérotation physique
                self._button = Button(f"BOARD{pin}", bounce_time=bounce_time)
                self._button.when_pressed = self._handle_press
                logger.info(f"Bouton initialisé sur pin BOARD {pin}")
            except Exception as e:
                logger.error(f"Erreur init bouton pin {pin}: {e}")

    def _handle_press(self):
        if self._callback:
            # Exécution dans un thread pour ne pas bloquer gpiozero
            threading.Thread(target=self._callback, daemon=True).start()

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
    """Gestion centralisée des boutons physiques du photobooth."""

    def __init__(self, config):
        self._enabled = config.get("gpio.enabled", True)
        self._buttons: dict[str, PhysicalButton] = {}

        if self._enabled:
            bounce = config.get("gpio.button_bounce_time", 0.3)
            self._buttons["photo"] = PhysicalButton(
                config.get("gpio.photo_button_pin", 11), bounce
            )
            self._buttons["print"] = PhysicalButton(
                config.get("gpio.print_button_pin", 13), bounce
            )

    def on_photo_button(self, callback: Callable):
        if "photo" in self._buttons:
            self._buttons["photo"].on_press(callback)

    def on_print_button(self, callback: Callable):
        if "print" in self._buttons:
            self._buttons["print"].on_press(callback)

    def close(self):
        for btn in self._buttons.values():
            btn.close()
