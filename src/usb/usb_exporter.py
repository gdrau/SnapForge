import logging
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_EXPORT_BASE = "Photos_PhotoBooth"


def find_usb_mount() -> Optional[Path]:
    """Détecte automatiquement la première clé USB montée sous /media ou /run/media."""
    for base in (Path("/media"), Path("/run/media")):
        if not base.exists():
            continue
        try:
            for lvl1 in sorted(base.iterdir()):
                if not lvl1.is_dir():
                    continue
                try:
                    sub_dirs = [s for s in lvl1.iterdir() if s.is_dir()]
                except PermissionError:
                    continue
                if sub_dirs:
                    # /media/<user>/<device> — ex: /media/pi/USB_DRIVE
                    for mount in sorted(sub_dirs):
                        try:
                            list(mount.iterdir())
                            logger.info(f"Clé USB trouvée : {mount}")
                            return mount
                        except PermissionError:
                            pass
                else:
                    # /media/<device> direct
                    try:
                        list(lvl1.iterdir())
                        logger.info(f"Clé USB trouvée : {lvl1}")
                        return lvl1
                    except PermissionError:
                        pass
        except PermissionError:
            pass
    return None


class UsbExporter:

    def __init__(self, config):
        self._raw_dir   = Path(config.get("photos.raw_dir",   "Photo/raw"))
        self._final_dir = Path(config.get("photos.final_dir", "Photo/final"))
        self._gifs_dir  = Path(config.get("gif.output_dir",   "Photo/gifs"))

    def export(
        self,
        status_cb: Callable[[str], None],
        done_cb:   Callable[[bool, str], None],
    ):
        """Lance l'export vers la clé USB dans un thread daemon."""
        threading.Thread(
            target=self._run,
            args=(status_cb, done_cb),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Thread d'export
    # ------------------------------------------------------------------

    def _run(self, status_cb, done_cb):
        try:
            logger.info("Export USB demandé")
            status_cb("Recherche de la clé USB...")

            mount = find_usb_mount()
            if not mount:
                logger.warning("Aucune clé USB détectée")
                done_cb(False, "Aucune clé USB détectée")
                return
            logger.info(f"Clé USB détectée : {mount}")

            export_dir = self._resolve_export_dir(mount)
            logger.info(f"Création du dossier {export_dir.name}")
            status_cb(f"Préparation de {export_dir.name}...")

            dir_tpl  = export_dir / "Photos_Template"
            dir_orig = export_dir / "Photos_Originales"
            dir_gif  = export_dir / "GIF_Animes"

            for d in (dir_tpl, dir_orig, dir_gif):
                d.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier créé : {d}")

            status_cb("Copie des photos finales...")
            logger.info("Copie Photos_Template")
            n_tpl = self._copy_flat(self._final_dir, dir_tpl, "*.jpg")

            status_cb("Copie des photos originales...")
            logger.info("Copie Photos_Originales")
            n_orig = self._copy_recursive(self._raw_dir, dir_orig, "*.jpg")

            status_cb("Copie des GIF animés...")
            logger.info("Copie GIF_Animes")
            n_gif = self._copy_flat(self._gifs_dir, dir_gif, "*.gif")

            total = n_tpl + n_orig + n_gif
            s = "s" if total != 1 else ""
            msg = f"Export terminé — {total} fichier{s} copié{s}"
            logger.info(f"Export terminé : {n_tpl} finales, {n_orig} originales, {n_gif} GIFs")
            done_cb(True, msg)

        except OSError as e:
            logger.error(f"Erreur export USB (OS) : {e}")
            if hasattr(e, "errno") and e.errno == 28:   # ENOSPC
                done_cb(False, "Espace insuffisant sur la clé USB")
            else:
                done_cb(False, "Erreur lors de l'export USB")
        except Exception as e:
            logger.error(f"Erreur export USB : {e}")
            done_cb(False, "Erreur lors de l'export USB")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_export_dir(self, mount: Path) -> Path:
        base = mount / _EXPORT_BASE
        if not base.exists():
            return base
        i = 1
        while (mount / f"{_EXPORT_BASE}_{i}").exists():
            i += 1
        return mount / f"{_EXPORT_BASE}_{i}"

    def _copy_flat(self, src: Path, dst: Path, pattern: str) -> int:
        """Copie les fichiers correspondant au pattern (non récursif)."""
        if not src.exists():
            return 0
        count = 0
        for f in sorted(src.glob(pattern)):
            if f.is_file():
                shutil.copy2(f, dst / f.name)
                count += 1
        return count

    def _copy_recursive(self, src: Path, dst: Path, pattern: str) -> int:
        """Copie tous les fichiers récursivement, à plat dans dst."""
        if not src.exists():
            return 0
        count = 0
        for f in sorted(src.rglob(pattern)):
            if not f.is_file():
                continue
            target = dst / f.name
            if target.exists():
                stem, suffix = f.stem, f.suffix
                i = 1
                while target.exists():
                    target = dst / f"{stem}_{i}{suffix}"
                    i += 1
            shutil.copy2(f, target)
            count += 1
        return count
