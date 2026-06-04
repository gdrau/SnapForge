#!/usr/bin/env python3
"""
Test boutons et LEDs GPIO.
Exécuter sur le Raspberry Pi : python scripts/test_gpio.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from gpiozero import Button, LED
    GPIO_OK = True
except ImportError:
    print("ERREUR : gpiozero non disponible")
    sys.exit(1)

# Brochage BOARD (numérotation physique)
PINS = {
    "LED photo":     {"type": "led", "pin": 7},
    "LED print":     {"type": "led", "pin": 15},
    "LED startup":   {"type": "led", "pin": 29},
    "LED séquence":  {"type": "led", "pin": 31},
    "LED flash":     {"type": "led", "pin": 33},
    "BTN photo":     {"type": "btn", "pin": 11},
    "BTN print":     {"type": "btn", "pin": 13},
}


def test_leds():
    print("\n=== Test LEDs ===")
    leds = {}
    for name, cfg in PINS.items():
        if cfg["type"] == "led":
            try:
                led = LED(f"BOARD{cfg['pin']}")
                leds[name] = led
                print(f"  {name} (pin {cfg['pin']}) : OK")
            except Exception as e:
                print(f"  {name} (pin {cfg['pin']}) : ERREUR - {e}")

    print("\n  Allumage séquentiel (1s chacune)…")
    for name, led in leds.items():
        print(f"  → {name}")
        led.on()
        time.sleep(1)
        led.off()

    print("\n  Clignotement toutes en même temps (3s)…")
    for led in leds.values():
        led.blink(0.3, 0.3)
    time.sleep(3)
    for led in leds.values():
        led.off()
        led.close()
    print("  LEDs OK")


def test_buttons():
    print("\n=== Test Boutons ===")
    print("  Appuyez sur chaque bouton dans les 10 secondes…\n")

    pressed = {}
    buttons = {}

    for name, cfg in PINS.items():
        if cfg["type"] == "btn":
            try:
                btn = Button(f"BOARD{cfg['pin']}", bounce_time=0.1)
                btn.when_pressed = lambda n=name: pressed.update({n: True}) or print(f"  ✓ {n} pressé")
                buttons[name] = btn
                print(f"  {name} (pin {cfg['pin']}) : initialisé")
            except Exception as e:
                print(f"  {name} (pin {cfg['pin']}) : ERREUR - {e}")

    deadline = time.time() + 10
    while time.time() < deadline:
        if len(pressed) == len(buttons):
            break
        remaining = int(deadline - time.time())
        print(f"\r  Attente : {remaining}s  ", end="", flush=True)
        time.sleep(0.5)

    print()
    for name in buttons:
        status = "✓ OK" if name in pressed else "✗ NON DÉTECTÉ"
        print(f"  {name} : {status}")

    for btn in buttons.values():
        btn.close()


if __name__ == "__main__":
    print("PhotoBooth — Test GPIO")
    test_leds()
    test_buttons()
    print("\nTest terminé.")
