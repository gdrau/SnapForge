#!/usr/bin/env python3
"""
PhotoBooth - Point d'entrée principal.
Usage : python src/app.py [--config chemin/config.yaml] [--windowed]
"""
import argparse
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path

# Assure que les modules src/ sont importables depuis n'importe où
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Encodage UTF-8 pour la console Windows (Python 3.7+)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Travail depuis la racine du projet (parent de src/)
os.chdir(_SRC_DIR.parent)


def setup_logging(config) -> None:
    level_str: str = config.get("logging.level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    log_file: str = config.get("logging.file", "logs/photobooth.log")
    max_mb: int = config.get("logging.max_size_mb", 10)
    backups: int = config.get("logging.backup_count", 3)

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_mb * 1024 * 1024, backupCount=backups, encoding="utf-8"
            ),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PhotoBooth Raspberry Pi")
    parser.add_argument("--config", default="config.yaml", help="Fichier de configuration")
    parser.add_argument("--windowed", action="store_true", help="Mode fenêtré (développement)")
    args = parser.parse_args()

    from config import load_config, Config

    raw = load_config(args.config)
    if args.windowed:
        raw.setdefault("app", {})["fullscreen"] = False
    config = Config(raw)

    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("PhotoBooth démarrage…")

    # Imports tardifs pour que le logging soit configuré avant
    from gpio.buttons import ButtonManager
    from gpio.lights import LightManager
    from camera.picamera2_camera import create_camera
    from processing.composer import Composer
    from processing.ai_background import AIBackgroundProcessor
    from processing.gif_maker import GifMaker
    from cloud.uploader import UploadManager
    from print.cups_printer import CupsPrinter
    from qr.qr_generator import QRGenerator
    from ui.pygame_ui import PygameUI
    from state_machine import StateMachine
    from usb.usb_exporter import UsbExporter

    lights       = LightManager(config)
    buttons      = ButtonManager(config)
    usb_exporter = UsbExporter(config)
    camera    = create_camera(config)
    composer  = Composer(config)
    ai_proc   = AIBackgroundProcessor(config)
    gif_maker = GifMaker(config)
    uploader  = UploadManager(config)
    printer   = CupsPrinter(config)
    qr_gen    = QRGenerator(config)
    ui        = PygameUI(config)

    fsm = StateMachine(
        config=config,
        camera=camera,
        lights=lights,
        buttons=buttons,
        composer=composer,
        ai_processor=ai_proc,
        uploader=uploader,
        printer=printer,
        qr_gen=qr_gen,
        ui=ui,
        gif_maker=gif_maker,
        usb_exporter=usb_exporter,
    )
    ui.set_touch_callback(fsm.handle_touch)

    def _shutdown(sig, frame):
        logger.info(f"Signal {sig} reçu — arrêt propre")
        fsm.stop()
        ui.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        fsm.start()
        ui.run()          # Boucle bloquante — thread principal Pygame
    except Exception:
        logger.exception("Erreur fatale")
    finally:
        fsm.stop()
        lights.all_off()
        lights.close()
        buttons.close()
        camera.close()
        logger.info("PhotoBooth arrêté")


if __name__ == "__main__":
    main()
