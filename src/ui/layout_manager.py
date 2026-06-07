"""
LayoutManager — toutes les dimensions de l'interface passent par ici.
Aucun pixel fixe dans les écrans : tout est calculé depuis w/h réels.
"""


class LayoutManager:
    """
    Gestionnaire de layout responsive.

    Usage :
        lm = LayoutManager(screen_w, screen_h)
        font = pygame.font.Font(path, lm.font_md)
        btn_h = lm.btn_h
    """

    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.is_portrait = h > w

        # Dimension minimale — base de calcul des polices et petites dimensions
        dim = min(w, h)

        # ------------------------------------------------------------------
        # Polices (proportionnelles à min(w, h) → cohérentes portrait/paysage)
        # ------------------------------------------------------------------
        self.font_xs  = max(12, int(dim * 0.038))   # ~18px @ 480
        self.font_sm  = max(14, int(dim * 0.046))   # ~22px @ 480
        self.font_md  = max(18, int(dim * 0.063))   # ~30px @ 480
        self.font_lg  = max(24, int(dim * 0.100))   # ~48px @ 480
        self.font_xl  = max(32, int(dim * 0.150))   # ~72px @ 480
        self.font_xxl = max(48, int(dim * 0.250))   # ~120px @ 480

        # ------------------------------------------------------------------
        # Marges et espacement
        # ------------------------------------------------------------------
        self.margin    = max(16, int(w * 0.058))    # ~28px @ 480
        self.gap_sm    = max(6,  int(h * 0.010))    # ~8px @ 800
        self.gap_md    = max(12, int(h * 0.018))    # ~14px @ 800

        # ------------------------------------------------------------------
        # Boutons
        # ------------------------------------------------------------------
        # Hauteur du bouton d'action principal (APPUYEZ POUR COMMENCER…)
        self.btn_h     = max(44, int(h * 0.065))    # ~52px @ 800
        self.btn_pad_x = max(18, int(w * 0.058))    # ~28px @ 480
        self.btn_pad_y = max(10, int(h * 0.018))    # ~14px @ 800

        # ------------------------------------------------------------------
        # Admin
        # ------------------------------------------------------------------
        self.row_h     = max(38, max(self.font_sm + 18,
                             int(h * 0.068)))        # ~54px @ 800
        self.hdr_h     = max(36, int(h * 0.065))    # ~52px @ 800
        # Largeur de la zone valeur dans les lignes admin
        self.val_w     = max(110, int(w * (0.34 if self.is_portrait else 0.27)))

        # ------------------------------------------------------------------
        # Écran d'accueil — proportions verticales (ratio de h)
        # ------------------------------------------------------------------
        # Ces ratios définissent où chaque zone commence (de 0 à 1)
        if self.is_portrait:
            self.idle_title_y     = 0.12    # 12 % → titre
            self.idle_subtitle_y  = 0.22    # 22 % → "Bienvenue !"
            self.idle_carousel_y  = 0.31    # 31 % → début carrousel
            self.idle_btn_y       = 0.91    # 91 % → centre bouton
            self.idle_carousel_max_h = 0.32 # 32 % max hauteur carrousel
        else:
            self.idle_title_y     = 0.15
            self.idle_subtitle_y  = 0.28
            self.idle_carousel_y  = 0.38
            self.idle_btn_y       = 0.87
            self.idle_carousel_max_h = 0.35

        # ------------------------------------------------------------------
        # Utilitaires
        # ------------------------------------------------------------------
        # Taille de l'ombre du carrousel
        self.carousel_shadow_offset = max(3, int(dim * 0.008))

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def px(self, ratio: float, of: str = "h") -> int:
        """Convertit un ratio en pixels (0-1 de w ou h)."""
        return int((self.w if of == "w" else self.h) * ratio)

    def __repr__(self):
        return (f"LayoutManager({self.w}x{self.h} "
                f"{'portrait' if self.is_portrait else 'paysage'} "
                f"font_md={self.font_md} row_h={self.row_h})")
