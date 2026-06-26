import logging
import time
import threading
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from gpiozero import LED
    _GPIO_AVAILABLE = True
except Exception:
    _GPIO_AVAILABLE = False
    logger.warning("gpiozero indisponible - LEDs GPIO simulées (mode développement)")


class PhysicalLED:

    def __init__(self, pin: int):
        self.pin = pin
        self._led = None
        self._blink_stop = threading.Event()
        self._blink_thread: Optional[threading.Thread] = None

        if _GPIO_AVAILABLE:
            try:
                self._led = LED(f"BOARD{pin}")
                logger.info(f"LED initialisée sur pin BOARD {pin}")
            except Exception as e:
                logger.error(f"Erreur init LED pin {pin}: {e}")

    def on(self):
        self._stop_blink()
        if self._led:
            self._led.on()

    def off(self):
        self._stop_blink()
        if self._led:
            self._led.off()

    def blink(self, on_time: float = 0.5, off_time: float = 0.5):
        self._stop_blink()
        self._blink_stop.clear()
        self._blink_thread = threading.Thread(
            target=self._blink_loop, args=(on_time, off_time), daemon=True
        )
        self._blink_thread.start()

    def _blink_loop(self, on_time: float, off_time: float):
        while not self._blink_stop.is_set():
            if self._led:
                self._led.on()
            if self._blink_stop.wait(on_time):
                break
            if self._led:
                self._led.off()
            self._blink_stop.wait(off_time)
        if self._led:
            self._led.off()

    def _stop_blink(self):
        self._blink_stop.set()
        if self._blink_thread and self._blink_thread.is_alive():
            self._blink_thread.join(timeout=1.0)

    def close(self):
        self._stop_blink()
        if self._led:
            try:
                self._led.close()
            except Exception:
                pass


class LightManager:
    """Contrôle centralisé de toutes les LEDs du photobooth."""

    def __init__(self, config):
        self._enabled = config.get("gpio.enabled", True)
        self._leds: dict[str, PhysicalLED] = {}
        self._flash_duration = config.get("camera.flash_duration", 0.3)

        if self._enabled:
            pins = {
                "photo":    config.get("gpio.photo_led_pin",    7),
                "print":    config.get("gpio.print_led_pin",   15),
                "startup":  config.get("gpio.startup_led_pin", 29),
                "sequence": config.get("gpio.sequence_led_pin",31),
                "flash":    config.get("gpio.flash_led_pin",   33),
            }
            for name, pin in pins.items():
                self._leds[name] = PhysicalLED(pin)

    def _get(self, name: str) -> Optional[PhysicalLED]:
        return self._leds.get(name)

    # --- API publique ---

    def startup_on(self):
        led = self._get("startup")
        if led:
            led.on()

    def photo_ready(self):
        led = self._get("photo")
        if led:
            led.on()

    def photo_off(self):
        led = self._get("photo")
        if led:
            led.off()

    def sequence_on(self):
        led = self._get("sequence")
        if led:
            led.on()

    def sequence_blink(self):
        led = self._get("sequence")
        if led:
            led.blink(0.3, 0.3)

    def sequence_off(self):
        led = self._get("sequence")
        if led:
            led.off()

    def flash(self, duration: Optional[float] = None):
        led = self._get("flash")
        if led:
            led.on()
            time.sleep(duration or self._flash_duration)
            led.off()

    def flash_async(self, duration: Optional[float] = None):
        threading.Thread(target=self.flash, args=(duration,), daemon=True).start()

    def flash_on(self):
        led = self._get("flash")
        if led:
            led.on()

    def flash_off(self):
        led = self._get("flash")
        if led:
            led.off()

    def print_ready(self):
        led = self._get("print")
        if led:
            led.on()

    def print_blink(self):
        led = self._get("print")
        if led:
            led.blink(0.5, 0.5)

    def print_off(self):
        led = self._get("print")
        if led:
            led.off()

    def all_off(self):
        for led in self._leds.values():
            led.off()

    def close(self):
        for led in self._leds.values():
            led.close()
