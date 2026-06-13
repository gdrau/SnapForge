import logging
import os
import shutil
import subprocess
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
        self._raw_dir   = Path(config.get("photos.raw_dir",   "Photo/raw")).resolve()
        self._final_dir = Path(config.get("photos.final_dir", "Photo/final")).resolve()
        self._gifs_dir  = Path(config.get("gif.output_dir",   "Photo/gifs")).resolve()

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
        mount = None
        try:
            logger.info("Export USB demandé")
            logger.info(f"Dossier final  : {self._final_dir} (existe={self._final_dir.exists()})")
            logger.info(f"Dossier raw    : {self._raw_dir} (existe={self._raw_dir.exists()})")
            logger.info(f"Dossier gifs   : {self._gifs_dir} (existe={self._gifs_dir.exists()})")

            status_cb("Recherche de la clé USB...")
            mount = find_usb_mount()
            if not mount:
                logger.warning("Aucune clé USB détectée")
                done_cb(False, "Aucune clé USB détectée")
                return
            logger.info(f"Clé USB : {mount}")

            export_dir = self._resolve_export_dir(mount)
            logger.info(f"Dossier export : {export_dir}")
            status_cb(f"Préparation de {export_dir.name}...")

            dir_tpl  = export_dir / "Photos_Template"
            dir_orig = export_dir / "Photos_Originales"
            dir_gif  = export_dir / "GIF_Animes"

            for d in (dir_tpl, dir_orig, dir_gif):
                d.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier créé : {d}")

            status_cb("Copie des photos finales...")
            logger.info("--- Copie Photos_Template ---")
            n_tpl = self._copy_flat(self._final_dir, dir_tpl, "*.jpg")

            status_cb("Copie des photos originales...")
            logger.info("--- Copie Photos_Originales ---")
            n_orig = self._copy_recursive(self._raw_dir, dir_orig, "*.jpg")

            status_cb("Copie des GIF animés...")
            logger.info("--- Copie GIF_Animes ---")
            n_gif = self._copy_flat(self._gifs_dir, dir_gif, "*.gif")

            total = n_tpl + n_orig + n_gif
            logger.info(f"Copie terminée : {n_tpl} finales, {n_orig} originales, {n_gif} GIFs")

            # --- Synchronisation ---
            status_cb("Synchronisation des données...")
            logger.info("sync : flush des tampons disque...")
            try:
                subprocess.run(["sync"], check=True, timeout=30)
                logger.info("sync : OK")
            except Exception as e:
                logger.warning(f"sync : {e}")

            # --- Démontage ---
            status_cb("Démontage de la clé USB...")
            logger.info(f"umount {mount}...")
            try:
                result = subprocess.run(
                    ["umount", str(mount)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    logger.info("Clé USB démontée avec succès")
                else:
                    logger.warning(f"umount : {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"umount : {e}")

            s = "s" if total != 1 else ""
            done_cb(True, f"Vous pouvez retirer la clé USB\n{total} fichier{s} copié{s}")

        except OSError as e:
            logger.error(f"Erreur export USB (OS) : {e}")
            if hasattr(e, "errno") and e.errno == 28:   # ENOSPC
                done_cb(False, "Espace insuffisant sur la clé USB")
            else:
                done_cb(False, f"Erreur lors de l'export USB\n{e}")
        except Exception as e:
            logger.error(f"Erreur export USB : {e}")
            done_cb(False, "Erreur lors de l'export USB")

    # ------------------------------------------------------------------
    # Copie unitaire avec flush/fsync et validation
    # ------------------------------------------------------------------

    def _copy_one(self, src: Path, dst: Path) -> int:
        """Copie un fichier avec flush/fsync et valide la taille."""
        src_size = src.stat().st_size
        logger.info(f"  {src.name}")
        logger.info(f"    source      : {src} ({src_size:,} octets)")

        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
            fdst.flush()
            os.fsync(fdst.fileno())

        shutil.copystat(src, dst)

        dst_size = dst.stat().st_size
        logger.info(f"    destination : {dst} ({dst_size:,} octets)")

        if dst_size != src_size:
            raise OSError(
                f"Validation échouée : {src.name} "
                f"(source {src_size:,} o ≠ destination {dst_size:,} o)"
            )
        logger.info(f"    validation  : OK")
        return src_size

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
            logger.warning(f"Dossier source introuvable : {src}")
            return 0
        files = sorted(f for f in src.glob(pattern) if f.is_file())
        logger.info(f"{len(files)} fichier(s) trouvé(s) dans {src}")
        count = 0
        for f in files:
            self._copy_one(f, dst / f.name)
            count += 1
        return count

    def _copy_recursive(self, src: Path, dst: Path, pattern: str) -> int:
        """Copie tous les fichiers récursivement, à plat dans dst."""
        if not src.exists():
            logger.warning(f"Dossier source introuvable : {src}")
            return 0
        files = sorted(f for f in src.rglob(pattern) if f.is_file())
        logger.info(f"{len(files)} fichier(s) trouvé(s) dans {src} (récursif)")
        count = 0
        for f in files:
            target = dst / f.name
            if target.exists():
                stem, suffix = f.stem, f.suffix
                i = 1
                while target.exists():
                    target = dst / f"{stem}_{i}{suffix}"
                    i += 1
            self._copy_one(f, target)
            count += 1
        return count
