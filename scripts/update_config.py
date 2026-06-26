#!/usr/bin/env python3
"""
Mise à jour de config.yaml après git pull.

Compare config.yaml avec config.example.yaml pour identifier les valeurs
personnalisées, lance git pull, puis recrée config.yaml en partant du nouvel
example et en réinjectant les valeurs personnalisées.

Usage :
    python scripts/update_config.py           # Affiche les overrides détectés (sans rien modifier)
    python scripts/update_config.py --pull    # Backup + git pull + recréation du config.yaml
    python scripts/update_config.py --apply   # Applique les overrides sans git pull (après pull manuel)
"""
import sys
import subprocess
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML non installé. Lancer : pip install pyyaml")
    sys.exit(1)

CONFIG_PATH  = ROOT / "config.yaml"
EXAMPLE_PATH = ROOT / "config.example.yaml"
SEP = "─" * 60


# ---------------------------------------------------------------------------
# Helpers YAML
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict, path: Path):
    """Sauvegarde avec tri des clés désactivé pour préserver l'ordre."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# SnapForge — Configuration\n")
        f.write(f"# Généré par update_config.py le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# Référence : config.example.yaml\n\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2)


# ---------------------------------------------------------------------------
# Diff / merge récursif
# ---------------------------------------------------------------------------

def flatten(d: dict, prefix: str = "") -> dict:
    """Aplatit un dict imbriqué en dict de keypaths pointés."""
    out = {}
    for k, v in d.items():
        full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            out.update(flatten(v, full))
        else:
            out[full] = v
    return out


def compute_overrides(user: dict, example: dict) -> dict:
    """
    Retourne un dict plat {keypath: valeur} des clés où user ≠ example.
    Ignore les clés absentes de example (déjà spécifiques à l'utilisateur).
    """
    user_flat    = flatten(user)
    example_flat = flatten(example)
    overrides = {}
    for key, user_val in user_flat.items():
        ex_val = example_flat.get(key)
        if ex_val is None:
            # Clé absente de l'exemple — toujours conserver
            overrides[key] = user_val
        elif user_val != ex_val:
            overrides[key] = user_val
    return overrides


def apply_overrides(base: dict, overrides: dict) -> dict:
    """Applique les overrides plats sur un dict imbriqué (deep copy)."""
    result = deepcopy(base)
    for keypath, value in overrides.items():
        keys = keypath.split(".")
        d = result
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
    return result


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def print_overrides_report(overrides: dict, new_example: dict,
                            old_example: dict, user: dict):
    new_flat  = flatten(new_example)
    old_flat  = flatten(old_example)
    user_flat = flatten(user)

    print(f"\n{'VALEURS PERSONNALISÉES (préservées)':^60}")
    print(SEP)
    if overrides:
        for key, val in sorted(overrides.items()):
            default = old_flat.get(key, "—")
            print(f"  {key}")
            print(f"    défaut exemple : {default!r}")
            print(f"    votre valeur   : {val!r}")
    else:
        print("  Aucune valeur personnalisée détectée.")

    # Clés nouvelles dans le nouvel example (absentes avant)
    new_keys = {k for k in new_flat if k not in old_flat}
    if new_keys:
        print(f"\n{'NOUVELLES CLÉS (ajoutées par la mise à jour)':^60}")
        print(SEP)
        for key in sorted(new_keys):
            print(f"  + {key} = {new_flat[key]!r}")

    # Clés supprimées de l'example
    removed_keys = {k for k in old_flat if k not in new_flat}
    if removed_keys:
        print(f"\n{'CLÉS SUPPRIMÉES DE L\'EXEMPLE':^60}")
        print(SEP)
        for key in sorted(removed_keys):
            user_val = user_flat.get(key)
            if user_val is not None and key in overrides:
                print(f"  - {key} (valeur conservée : {user_val!r})")
            else:
                print(f"  - {key}")

    # Défauts modifiés dans l'exemple (clés non personnalisées par l'user)
    changed_defaults = {
        k: (old_flat[k], new_flat[k])
        for k in new_flat
        if k in old_flat
        and old_flat[k] != new_flat[k]
        and k not in overrides
    }
    if changed_defaults:
        print(f"\n{'DÉFAUTS MIS À JOUR (non personnalisés → valeur nouvelle)':^60}")
        print(SEP)
        for key, (old_v, new_v) in sorted(changed_defaults.items()):
            print(f"  {key}: {old_v!r} → {new_v!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    do_pull  = "--pull"  in args
    do_apply = "--apply" in args
    dry_run  = not do_pull and not do_apply

    print(SEP)
    print("  SnapForge — Mise à jour de config.yaml")
    print(SEP)

    # -- Vérifications préalables -----------------------------------------
    if not CONFIG_PATH.exists():
        print(f"\nERREUR : {CONFIG_PATH} introuvable.")
        print("Créer d'abord config.yaml depuis config.example.yaml :")
        print("  cp config.example.yaml config.yaml")
        sys.exit(1)

    if not EXAMPLE_PATH.exists():
        print(f"\nERREUR : {EXAMPLE_PATH} introuvable.")
        sys.exit(1)

    # -- Chargement --------------------------------------------------------
    print(f"\n  Lecture de config.yaml et config.example.yaml...")
    user_config    = load_yaml(CONFIG_PATH)
    old_example    = load_yaml(EXAMPLE_PATH)

    # -- Calcul des overrides ----------------------------------------------
    overrides = compute_overrides(user_config, old_example)

    print(f"  Overrides détectés : {len(overrides)}")
    for k, v in sorted(overrides.items()):
        print(f"    {k} = {v!r}")

    if dry_run:
        print(f"\n  (mode consultation — aucune modification)")
        print(f"  Lancer avec --pull pour mettre à jour automatiquement.")
        print(f"  Lancer avec --apply pour appliquer sans git pull.")
        print_overrides_report(overrides, old_example, old_example, user_config)
        print(f"\n{SEP}\n")
        return

    # -- Backup ------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ROOT / f"config_backup_{ts}.yaml"
    shutil.copy2(CONFIG_PATH, backup_path)
    print(f"\n  Sauvegarde : {backup_path.name}")

    # -- Git pull ----------------------------------------------------------
    if do_pull:
        print(f"\n  Lancement de git pull...")
        print(SEP)
        result = subprocess.run(["git", "pull"], cwd=ROOT)
        print(SEP)
        if result.returncode != 0:
            print("\nERREUR : git pull a échoué. config.yaml non modifié.")
            print(f"La sauvegarde reste disponible : {backup_path.name}")
            sys.exit(1)

    # -- Rechargement de l'example (potentiellement mis à jour) -----------
    new_example = load_yaml(EXAMPLE_PATH)

    # -- Application des overrides -----------------------------------------
    new_config = apply_overrides(new_example, overrides)

    # -- Écriture ----------------------------------------------------------
    save_yaml(new_config, CONFIG_PATH)
    print(f"\n  config.yaml recréé avec {len(overrides)} valeur(s) personnalisée(s) réinjectée(s).")

    # -- Rapport -----------------------------------------------------------
    print_overrides_report(overrides, new_example, old_example, user_config)

    print(f"\n{SEP}")
    print(f"  Terminé. Sauvegarde : {backup_path.name}")
    print(f"  Référence complète  : config.example.yaml")
    print(SEP)


if __name__ == "__main__":
    main()
