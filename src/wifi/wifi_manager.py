import logging
import shutil
import socket
import subprocess
from typing import List, Tuple

logger = logging.getLogger(__name__)

_NMCLI = shutil.which("nmcli")


def available() -> bool:
    return _NMCLI is not None


def scan_networks() -> List[str]:
    """Retourne la liste des SSIDs visibles (dédupliqués, sans cache)."""
    if not _NMCLI:
        return []
    try:
        result = subprocess.run(
            [_NMCLI, "--get-values", "SSID", "dev", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=20,
        )
        seen: set = set()
        networks: List[str] = []
        for line in result.stdout.splitlines():
            ssid = line.strip()
            if ssid and ssid not in seen:
                seen.add(ssid)
                networks.append(ssid)
        return networks
    except Exception as e:
        logger.error(f"Erreur scan WiFi : {e}")
        return []


def get_current_ssid() -> str:
    """Retourne le SSID du réseau actuellement connecté, ou chaîne vide."""
    if not _NMCLI:
        return ""
    try:
        result = subprocess.run(
            [_NMCLI, "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                return line[4:].strip()
    except Exception:
        pass
    return ""


def get_ip_address() -> str:
    """Retourne l'adresse IP locale, ou '---'."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "---"


def connect(ssid: str, password: str) -> Tuple[bool, str]:
    """Connecte au réseau WiFi. Retourne (succès, message)."""
    if not _NMCLI:
        return False, "nmcli introuvable sur ce système"
    if not ssid:
        return False, "Aucun réseau sélectionné"
    try:
        cmd = [_NMCLI, "dev", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            ip = get_ip_address()
            suffix = f"  IP : {ip}" if ip != "---" else ""
            return True, f"Connecté à {ssid}{suffix}"
        err = (result.stderr or result.stdout).strip()
        if any(w in err.lower() for w in ("authorization", "polkit", "permission", "not authorized")):
            return False, "Permission refusée — ajouter l'utilisateur au groupe netdev"
        return False, (err[:80] if err else "Connexion échouée")
    except subprocess.TimeoutExpired:
        return False, "Délai dépassé (30s)"
    except Exception as e:
        return False, str(e)[:80]
