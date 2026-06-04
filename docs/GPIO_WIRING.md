# Câblage GPIO — PhotoBooth Raspberry Pi

> Brochage compatible avec Pibooth. Numérotation physique (BOARD).

## Schéma des connexions

```
Raspberry Pi                Composant
─────────────────────────────────────────────
Pin  2  (5V)      ──────── Alimentation LEDs (via résistances)
Pin  6  (GND)     ──────── Masse commune
Pin  7  (BCM 4)   ──────── LED photo (anode via R 220Ω)
Pin  9  (GND)     ──────── Masse bouton photo
Pin 11  (BCM17)   ──────── Bouton photo (NO, entre pin et GND)
Pin 13  (BCM27)   ──────── Bouton impression/export (NO)
Pin 14  (GND)     ──────── Masse bouton impression
Pin 15  (BCM22)   ──────── LED impression (anode via R 220Ω)
Pin 29  (BCM 5)   ──────── LED startup (anode via R 220Ω)
Pin 31  (BCM 6)   ──────── LED séquence/preview (anode via R 220Ω)
Pin 33  (BCM13)   ──────── LED flash (anode via R 220Ω)

Optionnel — bouton arrêt propre :
Pin  5  (SCL/GPIO3) + Pin 6 (GND)  avec dtoverlay=gpio-shutdown dans /boot/config.txt
```

## Tableau récapitulatif

| Fonction       | Pin physique | BCM | Type  | Connexion              |
|----------------|:------------:|:---:|-------|------------------------|
| Bouton photo   | 11           | 17  | Input | Entre pin et GND (pull-up interne) |
| LED photo      | 7            | 4   | Output| Via résistance 220 Ω → GND |
| Bouton print   | 13           | 27  | Input | Entre pin et GND       |
| LED print      | 15           | 22  | Output| Via résistance 220 Ω → GND |
| LED startup    | 29           | 5   | Output| Via résistance 220 Ω → GND |
| LED séquence   | 31           | 6   | Output| Via résistance 220 Ω → GND |
| LED flash      | 33           | 13  | Output| Via résistance 220 Ω → GND |

## Câblage LED (schéma simple)

```
Pin GPIO (3,3V)
      │
      ├── Résistance 220 Ω
      │
      ├── Anode LED (+)
      │
      └── Cathode LED (–) → GND (Pin 6, 9, 14, 20, 25, 30, 34 ou 39)
```

## Câblage bouton poussoir

```
Pin GPIO ──────────────────── Pin 1 du bouton
                               Pin 2 du bouton ── GND

(gpiozero active la résistance pull-up interne : appui = 0V = pressed)
```

## Activation du bouton d'arrêt propre (optionnel)

Ajouter dans `/boot/firmware/config.txt` (Bookworm) :

```ini
dtoverlay=gpio-shutdown,gpio_pin=3
```

Puis relier un bouton entre Pin 5 (GPIO3) et Pin 6 (GND).
Un appui déclenche `sudo shutdown -h now` sans script supplémentaire.

## Vérification du câblage

```bash
python scripts/test_gpio.py
```

## Notes importantes

- Utilisez des résistances **220 Ω minimum** pour les LEDs (Pi → 3,3V, dépasse 16 mA sans résistance).
- La LED flash peut être remplacée par un module flash dédié avec transistor NPN (BC547) si vous voulez plus de luminosité.
- gpiozero utilise `BOARD<n>` pour la numérotation physique ; ne pas confondre avec BCM.
