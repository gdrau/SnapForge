#!/usr/bin/env python3
"""
Script de diagnostic imprimante CUPS.
Lancez-le avec : python3 test_printer.py
Copiez-collez la sortie complète pour aider au débogage.
"""
import subprocess
import shutil
import sys

SEP = "-" * 60


def run(cmd, label):
    print(f"\n>>> {label}")
    print(f"    commande : {' '.join(cmd)}")
    if not shutil.which(cmd[0]):
        print(f"    !! '{cmd[0]}' introuvable (CUPS non installé ?)")
        return
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        stdout = r.stdout.strip()
        stderr = r.stderr.strip()
        print(f"    code retour : {r.returncode}")
        if stdout:
            for line in stdout.splitlines():
                print(f"    STDOUT | {line}")
        else:
            print("    STDOUT | (vide)")
        if stderr:
            for line in stderr.splitlines():
                print(f"    STDERR | {line}")
    except subprocess.TimeoutExpired:
        print("    !! timeout (CUPS non réactif ?)")
    except Exception as e:
        print(f"    !! erreur : {e}")


def main():
    print(SEP)
    print("DIAGNOSTIC IMPRIMANTE CUPS")
    print(SEP)

    # 1. Vérifier que CUPS tourne
    run(["lpstat", "-r"], "Statut du serveur CUPS (tourne-t-il ?)")

    # 2. Lister toutes les imprimantes configurées
    run(["lpstat", "-a"], "Imprimantes configurées et acceptation des jobs")

    # 3. Statut détaillé des imprimantes
    run(["lpstat", "-p"], "Statut détaillé (idle / stopped / disabled…)")

    # 4. Imprimantes par défaut
    run(["lpstat", "-d"], "Imprimante par défaut")

    # 5. lpstat -l -p : infos longues (type connexion, URI)
    run(["lpstat", "-l", "-p"], "Infos longues (URI, type connexion)")

    # 6. lpq : file d'attente
    run(["lpq"], "File d'attente globale")

    # 7. Vérifier si un fichier device USB existe
    print(f"\n>>> Fichiers device USB (s'ils existent)")
    import os
    for path in ["/dev/usb/lp0", "/dev/lp0", "/dev/bus/usb"]:
        exists = os.path.exists(path)
        print(f"    {path} : {'EXISTE' if exists else 'absent'}")

    # 8. lsusb si disponible
    if shutil.which("lsusb"):
        run(["lsusb"], "Périphériques USB connectés (lsusb)")
    else:
        print("\n>>> lsusb non disponible")

    print(f"\n{SEP}")
    print("Fin du diagnostic. Copiez toute cette sortie.")
    print(SEP)


if __name__ == "__main__":
    main()
