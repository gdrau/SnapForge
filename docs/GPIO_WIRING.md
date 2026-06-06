# Câblage GPIO — SnapForge PhotoBooth Raspberry Pi

> Brochage compatible avec Pibooth. Numérotation physique **(BOARD)**.

---

## Tableau récapitulatif

| Fonction        | Pin physique | BCM | Type   | Rôle                                      |
|-----------------|:------------:|:---:|--------|-------------------------------------------|
| Bouton 1 (photo)| 11           | 17  | Input  | Lancer une session / valider              |
| LED photo       | 7            | 4   | Output | Prête à capturer                          |
| Bouton 2 (print)| 13           | 27  | Input  | Option secondaire / impression            |
| LED impression  | 15           | 22  | Output | Impression en cours / prête               |
| LED startup     | 29           | 5   | Output | Application démarrée                      |
| LED séquence    | 31           | 6   | Output | Séquence en cours (clignotant)            |
| LED flash       | 33           | 13  | Output | Flash au moment de la capture             |

---

## Schéma des connexions

```
Raspberry Pi                    Composant
────────────────────────────────────────────
Pin  2  (5V)      ──────────── Alimentation LEDs (via résistances)
Pin  6  (GND)     ──────────── Masse commune

Pin  7  (BCM 4)   ──── R220Ω ── LED photo (anode)
Pin  9  (GND)     ──────────── LED photo (cathode)

Pin 11  (BCM17)   ──────────── Bouton 1 (photo) NO
Pin  9  (GND)     ──────────── Bouton 1 (photo) autre borne

Pin 13  (BCM27)   ──────────── Bouton 2 (print) NO
Pin 14  (GND)     ──────────── Bouton 2 (print) autre borne

Pin 15  (BCM22)   ──── R220Ω ── LED impression (anode)
Pin 14  (GND)     ──────────── LED impression (cathode)

Pin 29  (BCM 5)   ──── R220Ω ── LED startup (anode)
Pin 30  (GND)     ──────────── LED startup (cathode)

Pin 31  (BCM 6)   ──── R220Ω ── LED séquence (anode)
Pin 30  (GND)     ──────────── LED séquence (cathode)

Pin 33  (BCM13)   ──── R220Ω ── LED flash (anode)
Pin 34  (GND)     ──────────── LED flash (cathode)
```

---

## Câblage LED

```
Pin GPIO (3,3V)
      │
      ├── Résistance 220 Ω (obligatoire)
      │
      ├── Anode LED (+) — côté long
      │
      └── Cathode LED (–) — côté court → GND
```

> ⚠️ Toujours utiliser une résistance **220 Ω minimum**. Sans résistance, la LED peut griller et endommager le Pi.

---

## Câblage bouton poussoir

```
Pin GPIO ──────────────────── Borne 1 du bouton NO
                               Borne 2 du bouton NO ── GND

(gpiozero active la résistance pull-up interne : appui → 0 V → pressed)
```

Les boutons sont configurés avec `bounce_time=0.05s` (50 ms d'anti-rebond) pour une réactivité quasi-immédiate.

---

## Bouton d'arrêt propre (optionnel)

Ajouter dans `/boot/firmware/config.txt` (Trixie) :

```ini
dtoverlay=gpio-shutdown,gpio_pin=3
```

Relier un bouton entre **Pin 5** (GPIO3) et **Pin 6** (GND).  
Un appui déclenche `sudo shutdown -h now` sans script supplémentaire.

---

## Navigation dans l'application

| Bouton | État          | Action                               |
|--------|---------------|--------------------------------------|
| BTN 1  | Accueil       | Aller au choix de format             |
| BTN 1  | Choix format  | Sélectionner option A (ex. 1 photo)  |
| BTN 2  | Choix format  | Sélectionner option B (ex. 4 photos) |
| BTN 1  | Preview       | Lancer le compte à rebours           |
| BTN 1  | Résultat      | Imprimer (si impression activée)     |
| BTN 2  | Résultat      | Continuer sans imprimer              |
| BTN 1  | QR code       | Retour à l'accueil                   |

> Le menu administration est accessible uniquement via la **touche ESC** au clavier.

---

## Test du câblage

```bash
cd /home/guillaume/SnapForge
source venv/bin/activate
python scripts/test_gpio.py
```

---

## Brochage Raspberry Pi 4 (référence)

```
         3V3  (1) (2)  5V
   SDA / GPIO2  (3) (4)  5V
   SCL / GPIO3  (5) (6)  GND      ← Bouton arrêt propre (pin 5)
        GPIO4  (7) (8)  GPIO14/TX
          GND  (9)(10)  GPIO15/RX
       GPIO17 (11)(12)  GPIO18
       GPIO27 (13)(14)  GND
       GPIO22 (15)(16)  GPIO23
         3V3 (17)(18)  GPIO24
       GPIO10 (19)(20)  GND
        GPIO9 (21)(22)  GPIO25
       GPIO11 (23)(24)  GPIO8
          GND (25)(26)  GPIO7
        GPIO0 (27)(28)  GPIO1
        GPIO5 (29)(30)  GND
        GPIO6 (31)(32)  GPIO12
       GPIO13 (33)(34)  GND
       GPIO19 (35)(36)  GPIO16
       GPIO26 (37)(38)  GPIO20
          GND (39)(40)  GPIO21

Pins utilisés (en gras) :
  7  = LED photo      11 = BTN photo
  13 = BTN print      15 = LED print
  29 = LED startup    31 = LED séquence
  33 = LED flash
```
