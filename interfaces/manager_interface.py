import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
import threading
import time
from models.database import DatabaseManager
from config.settings import DATABASE_PATH
import os
import math
import re

# ---- Configuration visuelle rapide ----
DEBUG = False         # Mettre True pour logs de debug
COLUMNS = 7           # Nombre de postes par ligne
CARD_PAD_X = 6        # Espacement horizontal entre les cartes
CARD_PAD_Y = 6        # Espacement vertical entre les cartes
TV_BEZEL_COLOR = "#2C3E50" # Couleur du cadre de la télé
TV_SCREEN_OFF_COLOR = "#333333" # Écran éteint (gris foncé)
TV_SCREEN_ON_COLOR = "#1E90FF"  # Écran allumé (bleu vif)
TV_STAND_COLOR = "#CCCCCC"      # Pied de la télé (gris clair)
# ------------------------------------------------

def normalize_console_name(name: str) -> str:
    """Normalise (strip, upper) et réduit les variantes courantes à des clés canoniques."""
    if not name:
        return ""
    s = re.sub(r'[^A-Z0-9]', '', name.strip().upper())
    mapping = {
        "PS2": "PS2", "PS3": "PS3", "PS4": "PS4", "PS5": "PS5",
        "PLAYSTATION2": "PS2", "PLAYSTATION3": "PS3", "PLAYSTATION4": "PS4", "PLAYSTATION5": "PS5",
        "PSII": "PS2", "PSIII": "PS3", "PSIV": "PS4",
        "XBOX": "XBOX", "XBOXONE": "XBOX", "XBOX360": "XBOX",
    }
    if s in mapping:
        return mapping[s]
    for k in mapping:
        if s.startswith(k):
            return mapping[k]
    return s

class ManagerInterface:
    def __init__(self, user_id):
        self.user_id = user_id
        self.root = tk.Tk()
        self.root.title("RDM gSalle - Interface Gérant")
        try:
            self.root.state('zoomed')
        except:
            pass

        self.selected_console_filter = tk.StringVar(value="TOUT")
        self.postes_data = {}
        self.running = True
        self.db = DatabaseManager(DATABASE_PATH)

        self.recette_visible = False
        self.card_widgets = {}
        
        self.load_logo()
        self.create_interface()
        self.load_postes()
        self.start_timer()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_logo(self):
        """Charge le logo depuis le dossier assets."""
        try:
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.png")
            if os.path.exists(logo_path):
                from PIL import Image, ImageTk
                image = Image.open(logo_path)
                image = image.resize((34, 34), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(image)
            else:
                self.logo_image = None
        except Exception as e:
            print(f"Erreur de chargement du logo: {e}")
            self.logo_image = None

    def get_user_info(self):
        """Récupère les informations de l'utilisateur connecté."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM users WHERE id = ?", (self.user_id,))
                result = cursor.fetchone()
                return {"username": result[0] if result else "Gérant"}
        except Exception as e:
            print(f"Erreur de récupération des infos utilisateur: {e}")
            return {"username": "Gérant"}

    def _lighten_color(self, hex_color, factor=30):
        """Éclaircit une couleur hexadécimale."""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        lightened_rgb = tuple(min(255, c + factor) for c in rgb)
        return '#%02x%02x%02x' % lightened_rgb

    def _on_button_enter(self, event):
        """Effet hover quand la souris entre sur le bouton."""
        # Utilise _original_bg pour restaurer la couleur correcte
        event.widget.config(bg=self._lighten_color(getattr(event.widget, '_original_bg', event.widget.cget('bg'))))

    def _on_button_leave(self, event):
        """Effet hover quand la souris quitte le bouton."""
        event.widget.config(bg=getattr(event.widget, '_original_bg', event.widget.cget('bg')))

    def create_interface(self):
        """Crée et organise tous les widgets de l'interface."""
        main_container = tk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)

        # === Sidebar Gauche ===
        sidebar = tk.Frame(main_container, bg="#2C3E50", width=240)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # En-tête de la sidebar (logo + titre)
        header_frame = tk.Frame(sidebar, bg="#2C3E50")
        header_frame.pack(fill=tk.X, pady=8, padx=8)

        if self.logo_image:
            logo_label = tk.Label(header_frame, image=self.logo_image, bg="#2C3E50")
            logo_label.pack(side=tk.LEFT, padx=(0, 6))

        title_label = tk.Label(header_frame, text="RDM gSalle", font=("Arial", 15, "bold"),
                               bg="#2C3E50", fg="white")
        title_label.pack(side=tk.LEFT)

        # Informations de l'utilisateur
        user_info = self.get_user_info()
        user_frame = tk.Frame(sidebar, bg="#2C3E50")
        user_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        user_label = tk.Label(user_frame,
                              text=f"👤 {user_info['username']}\n🎯 Gérant",
                              font=("Arial", 9),
                              bg="#2C3E50",
                              fg="#BDC3C7",
                              justify=tk.LEFT)
        user_label.pack(anchor=tk.W)

        # Boutons de navigation
        nav_frame = tk.Frame(sidebar, bg="#2C3E50")
        nav_frame.pack(fill=tk.X, padx=6)

        nav_buttons = [
            ("🎮 Sessions", "#3498DB"),
            ("👥 Clients", "#9B59B6"),
            ("📊 Rapports", "#E67E22"),
            ("🎁 Bonus du jour", "#F39C12"),
            ("📦 Abonnements", "#1ABC9C")
        ]

        for text, color in nav_buttons:
            btn = tk.Button(nav_frame,
                            text="  " + text,
                            font=("Arial", 9, "bold"),
                            bg=color,
                            fg="white",
                            relief="flat",
                            bd=0,
                            cursor="hand2",
                            anchor="w",
                            justify="left",
                            padx=10,
                            pady=5,
                            command=lambda t=text: self.add_alert(f"📋 {t} sélectionné"))
            btn._original_bg = color
            btn.bind("<Enter>", self._on_button_enter)
            btn.bind("<Leave>", self._on_button_leave)
            btn.pack(fill=tk.X, pady=2)

        # Zone d'alertes
        alert_frame = tk.Frame(sidebar, bg="#2C3E50")
        alert_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        alert_title = tk.Label(alert_frame, text="🚨 Alertes", font=("Arial", 10, "bold"), bg="#2C3E50", fg="white")
        alert_title.pack(pady=(0, 4))
        self.alert_text = tk.Text(alert_frame, height=6, font=("Arial", 9), bg="#34495E", fg="#ECF0F1", relief="flat",
                                  wrap=tk.WORD)
        self.alert_text.pack(fill=tk.BOTH, expand=True)

        # Boutons du bas de la sidebar
        bottom_frame = tk.Frame(sidebar, bg="#2C3E50")
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=6)
        bottom_buttons = [("🏠 Accueil", "#34495E"), ("⚙️ Paramètres", "#34495E"), ("🚪 Déconnexion", "#E74C3C")]
        for text, color in bottom_buttons:
            btn = tk.Button(bottom_frame,
                            text="  " + text,
                            font=("Arial", 9, "bold"),
                            bg=color,
                            fg="white",
                            relief="flat",
                            bd=0,
                            cursor="hand2",
                            anchor="w",
                            justify="left",
                            padx=10,
                            pady=5,
                            command=lambda t=text: self.handle_bottom_button(t))
            btn._original_bg = color
            btn.bind("<Enter>", self._on_button_enter)
            btn.bind("<Leave>", self._on_button_leave)
            btn.pack(fill=tk.X, pady=2)

        # === Zone Principale ===
        main_area = tk.Frame(main_container, bg="#ECF0F1")
        main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        content_frame = tk.Frame(main_area, bg="#ECF0F1")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # En-tête de la zone principale
        header_main = tk.Frame(content_frame, bg="#ECF0F1")
        header_main.pack(fill=tk.X, pady=(0, 6))
        title_main = tk.Label(header_main, text="🎮 Gestion des Postes", font=("Arial", 16, "bold"),
                              bg="#ECF0F1", fg="#2C3E50")
        title_main.pack(side=tk.LEFT)
        self.time_label = tk.Label(header_main, text="", font=("Arial", 9), bg="#ECF0F1", fg="#7F8C8D")
        self.time_label.pack(side=tk.RIGHT)
        self.update_time()

        # Filtres de console
        filter_frame = tk.LabelFrame(content_frame, text="🔍 Filtrer par Console", font=("Arial", 9, "bold"),
                                     bg="#ECF0F1", fg="#2C3E50", padx=6, pady=4)
        filter_frame.pack(fill=tk.X, pady=(0, 6))
        filter_container = tk.Frame(filter_frame, bg="#ECF0F1")
        filter_container.pack()
        console_types = [("TOUT", "#34495E"), ("PS2", "#E74C3C"), ("PS3", "#3498DB"), ("PS4", "#9B59B6"),
                         ("PS5", "#1ABC9C"), ("XBOX", "#27AE60")]
        for console, color in console_types:
            btn = tk.Radiobutton(filter_container, text=console, variable=self.selected_console_filter,
                                 value=normalize_console_name(console),
                                 command=self.filter_postes, font=("Arial", 8, "bold"),
                                 bg=color, fg="white", selectcolor=color, relief="flat", cursor="hand2", padx=6, pady=3)
            btn.pack(side=tk.LEFT, padx=3)

        # Statistiques rapides (avec bouton pour la recette)
        stats_frame = tk.LabelFrame(content_frame, text="📊 Stats", font=("Arial", 9, "bold"),
                                    bg="#ECF0F1", fg="#2C3E50", padx=4, pady=3)
        stats_frame.pack(fill=tk.X, pady=(0, 6))
        stats_container = tk.Frame(stats_frame, bg="#ECF0F1")
        stats_container.pack(fill=tk.X)
        self.stats_labels = {}
        stats_info = [("Postes Libres", "🟢", "#27AE60"), ("Postes Occupés", "🔴", "#E74C3C"),
                      ("En Maintenance", "🟡", "#F39C12"), ("Recette du Jour", "💰", "#3498DB")]
        for label, icon, color in stats_info:
            stat_frame = tk.Frame(stats_container, bg="#ECF0F1")
            stat_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            tk.Label(stat_frame, text=icon, font=("Arial", 12), bg="#ECF0F1").pack()
            value_label = tk.Label(stat_frame, text="0", font=("Arial", 11, "bold"), bg="#ECF0F1", fg=color)
            value_label.pack()
            tk.Label(stat_frame, text=label, font=("Arial", 8), bg="#ECF0F1", fg="#7F8C8D").pack()
            if label == "Recette du Jour":
                toggle_btn = tk.Button(stat_frame, text="Voir", font=("Arial", 8), command=self.toggle_recette,
                                       padx=6, pady=2, cursor="hand2")
                toggle_btn.pack(pady=(4, 0))
                self.recette_toggle_btn = toggle_btn
            self.stats_labels[label] = value_label

        # Zone de la grille des postes (avec Canvas et Scrollbar)
        postes_frame = tk.LabelFrame(content_frame, text="🎯 Postes de Jeu", font=("Arial", 10, "bold"),
                                     bg="#ECF0F1", fg="#2C3E50", padx=6, pady=6)
        postes_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(postes_frame, bg="white", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(postes_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="white")
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Support de la molette de la souris
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Barre de statut en bas de la fenêtre principale
        status_bar = tk.Frame(self.root, bg="#34495E", height=24)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        status_bar.pack_propagate(False)
        self.status_label = tk.Label(status_bar, text="✅ Système opérationnel - Tous les postes surveillés",
                                     font=("Arial", 9), bg="#34495E", fg="#2C3E50")
        self.status_label.pack(side=tk.LEFT, padx=8, pady=2)
        connection_label = tk.Label(status_bar, text="🟢 Base de données connectée", font=("Arial", 9), bg="#34495E",
                                    fg="#2C3E50")
        connection_label.pack(side=tk.RIGHT, padx=8, pady=2)

        self.add_alert("💡 Système démarré - Interface gérant opérationnelle")

    def toggle_recette(self):
        """Bascule la visibilité de la recette du jour."""
        self.recette_visible = not self.recette_visible
        try:
            self.recette_toggle_btn.config(text="Cacher" if self.recette_visible else "Voir")
        except:
            pass
        self.update_stats()

    def load_postes(self):
        """Charge les postes de test (avec normalisation des consoles)."""
        self.postes_data = {}
        test_postes = [
            {"id": i, "nom": f"Poste {i}",
             "type_console": ("PS4" if i % 3 == 0 else "PS5" if i % 3 == 1 else "XBOX"),
             "statut": "occupe" if i % 4 == 0 else "libre" if i % 5 != 0 else "maintenance"}
            for i in range(1, 21) # 20 postes de test
        ]
        for poste in test_postes:
            canon = normalize_console_name(poste.get("type_console"))
            poste["type_console"] = canon
            self.postes_data[poste["id"]] = {
                **poste,
                "temps_restant": 1800 if poste["statut"] == "occupe" else 0, # 30 minutes
                "client_nom": f"Client {poste['id']}" if poste["statut"] == "occupe" else "",
                "montant_paye": 200 if poste["statut"] == "occupe" else 0
            }
        self.update_postes_display(columns=COLUMNS)
        self.update_stats()

    def _normalize_postes(self):
        """Assure que tous les postes ont type_console normalisé."""
        for pid, poste in list(self.postes_data.items()):
            if "type_console" in poste:
                poste["type_console"] = normalize_console_name(poste["type_console"])
            else:
                poste["type_console"] = ""

    def _clear_scrollable(self):
        """Détruit TOUS les widgets enfants du scrollable_frame. À utiliser avec parcimonie."""
        for w in list(self.scrollable_frame.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass

    def update_postes_display(self, columns=COLUMNS):
        """
        Met à jour l'affichage des postes.
        Cache/affiche les cartes existantes et crée de nouvelles si nécessaire.
        """
        self._normalize_postes()

        filtered_postes = self.get_filtered_postes()

        if not self.postes_data:
            self._clear_scrollable()
            loading_label = tk.Label(self.scrollable_frame, text="Chargement des postes...", font=("Arial", 12),
                                     bg="white", fg="#7F8C8D")
            loading_label.grid(row=0, column=0, pady=20, padx=10, sticky="n")
            return

        if not filtered_postes:
            for pid, wdict in self.card_widgets.items():
                wdict["outer"].grid_forget()
            no_data_label = tk.Label(self.scrollable_frame, text="Aucun poste trouvé pour ce filtre", font=("Arial", 12),
                                     bg="white", fg="#7F8C8D")
            no_data_label.grid(row=0, column=0, pady=50, padx=10, sticky="n")
            return
        else:
            for w in self.scrollable_frame.winfo_children():
                if w.winfo_class() == "Label" and "Aucun poste" in w.cget("text"):
                    w.destroy()

        remaining_in_filter = set()
        row, col = 0, 0
        for poste_id, poste in filtered_postes.items():
            remaining_in_filter.add(poste_id)
            wdict = self.card_widgets.get(poste_id)

            if wdict:
                outer = wdict["outer"]
                self._update_card_widgets(poste, wdict)
                outer.grid(row=row, column=col, padx=CARD_PAD_X, pady=CARD_PAD_Y, sticky="nsew")
            else:
                wdict = self._create_card_widgets(poste)
                self.card_widgets[poste_id] = wdict
                outer = wdict["outer"]
                outer.grid(row=row, column=col, padx=CARD_PAD_X, pady=CARD_PAD_Y, sticky="nsew")

            col += 1
            if col >= columns:
                col = 0
                row += 1
        
        for pid, wdict in self.card_widgets.items():
            if pid not in remaining_in_filter:
                wdict["outer"].grid_forget()
        
        for i in range(columns):
            self.scrollable_frame.grid_columnconfigure(i, weight=1)

        self.scrollable_frame.update_idletasks()
        self.canvas.yview_moveto(0)

    def _create_card_widgets(self, poste):
        """Crée la structure d'une carte (UNE SEULE FOIS) avec le design de télé amélioré."""
        card_outer = tk.Frame(self.scrollable_frame, bg="#FFFFFF", highlightthickness=1, highlightbackground="lightgray", bd=0)
        
        # --- Nom du poste (au-dessus de la télé) ---
        title_lbl = tk.Label(card_outer, text=poste['nom'], font=("Arial", 10, "bold"), bg="#FFFFFF", fg="#2C3E50")
        title_lbl.pack(pady=(4, 2))

        # --- Représentation visuelle de la Télé ---
        tv_container_frame = tk.Frame(card_outer, bg="#FFFFFF")
        tv_container_frame.pack(pady=(2, 4))

        # Écran de la télé (rectangle foncé) - taille fixe
        tv_screen_frame = tk.Frame(tv_container_frame, bg=TV_SCREEN_OFF_COLOR, bd=2, relief="solid", highlightbackground=TV_BEZEL_COLOR)
        tv_screen_frame.pack(padx=8, pady=0)
        tv_screen_frame.pack_propagate(False)
        tv_screen_frame.configure(width=120, height=80) # Hauteur légèrement augmentée à 80px
        
        # Conteneur pour les infos au centre de l'écran (pour un meilleur centrage)
        screen_info_container = tk.Frame(tv_screen_frame, bg=TV_SCREEN_OFF_COLOR)
        screen_info_container.pack(expand=True, fill=tk.BOTH, padx=2, pady=4)

        # Labels pour les infos sur l'écran
        screen_client_lbl = tk.Label(screen_info_container, text="", font=("Arial", 9, "bold"), bg=TV_SCREEN_OFF_COLOR, fg="white")
        screen_client_lbl.pack(pady=(0,2))
        screen_time_lbl = tk.Label(screen_info_container, text="", font=("Arial", 14, "bold"), bg=TV_SCREEN_OFF_COLOR, fg="white")
        screen_time_lbl.pack()
        screen_pay_lbl = tk.Label(screen_info_container, text="", font=("Arial", 8), bg=TV_SCREEN_OFF_COLOR, fg="white")
        screen_pay_lbl.pack(pady=(2,0))

        # Pied de la télé (rectangle plus clair et plus fin)
        tv_stand_frame = tk.Frame(tv_container_frame, bg=TV_STAND_COLOR, height=6, width=60)
        tv_stand_frame.pack(pady=(2,0))
        tv_stand_frame.pack_propagate(False)

        # --- Section inférieure: Informations et Boutons ---
        bottom_area_frame = tk.Frame(card_outer, bg="#FFFFFF")
        bottom_area_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        # Bouton d'action unique
        btn_area = tk.Frame(bottom_area_frame, bg="#FFFFFF")
        btn_area.pack(fill=tk.X, pady=(4, 0))
        
        def create_styled_button(parent, text, bg_color, command):
            btn = tk.Button(parent, text=text, command=command, font=("Arial", 9, "bold"),
                            bg=bg_color, fg="white",
                            relief="flat", bd=0, 
                            activebackground=bg_color, cursor="hand2",
                            padx=4, pady=5)
            btn._original_bg = bg_color
            btn.bind("<Enter>", self._on_button_enter)
            btn.bind("<Leave>", self._on_button_leave)
            return btn

        main_action_btn = create_styled_button(btn_area, "...", "#3498DB", lambda: None)
        main_action_btn.pack(fill=tk.X)

        wdict = {
            "outer": card_outer,
            "title": title_lbl,
            "tv_screen_frame": tv_screen_frame,
            "tv_stand_frame": tv_stand_frame,
            "screen_info_container": screen_info_container,
            "screen_client_lbl": screen_client_lbl,
            "screen_time_lbl": screen_time_lbl,
            "screen_pay_lbl": screen_pay_lbl,
            "btn_area": btn_area,
            "main_action_btn": main_action_btn,
        }
        self._update_card_widgets(poste, wdict)
        return wdict

    def _update_card_widgets(self, poste, wdict):
        """Met à jour uniquement le contenu d'une carte existante (pas de recréation)."""
        
        # Couleurs dynamiques de la bordure de la carte
        if poste["statut"] == "libre":
            border_color = "#27AE60" # Vert
        elif poste["statut"] == "maintenance":
            border_color = "#F39C12" # Orange
        elif poste["temps_restant"] <= 120: # Temps critique
            border_color = "#E74C3C" # Rouge
        else: # Occupé (temps normal)
            border_color = "#3498DB" # Bleu
        
        wdict["outer"].config(highlightbackground=border_color)

        # Mise à jour de l'écran de la télé
        tv_screen_frame = wdict["tv_screen_frame"]
        screen_client_lbl = wdict["screen_client_lbl"]
        screen_time_lbl = wdict["screen_time_lbl"]
        screen_pay_lbl = wdict["screen_pay_lbl"]
        screen_info_container = wdict["screen_info_container"]

        if poste["statut"] == "occupe":
            tv_screen_frame.config(bg=TV_SCREEN_ON_COLOR, highlightbackground=TV_BEZEL_COLOR)
            screen_info_container.config(bg=TV_SCREEN_ON_COLOR)
            screen_client_lbl.config(bg=TV_SCREEN_ON_COLOR, fg="white", text=f"👤 {poste['client_nom']}")
            minutes = poste["temps_restant"] // 60
            seconds = poste["temps_restant"] % 60
            screen_time_lbl.config(bg=TV_SCREEN_ON_COLOR, fg="white", text=f"{minutes:02d}:{seconds:02d}")
            screen_pay_lbl.config(bg=TV_SCREEN_ON_COLOR, fg="white", text=f"💰 {poste['montant_paye']} FCFA")
            
            screen_client_lbl.pack(pady=(0,2))
            screen_time_lbl.pack()
            screen_pay_lbl.pack(pady=(2,0))
        else:
            tv_screen_frame.config(bg=TV_SCREEN_OFF_COLOR, highlightbackground=TV_BEZEL_COLOR)
            screen_info_container.config(bg=TV_SCREEN_OFF_COLOR)
            
            screen_client_lbl.pack_forget()
            screen_time_lbl.pack_forget()
            screen_pay_lbl.pack_forget()

        # Mise à jour du bouton d'action unique
        main_action_btn = wdict["main_action_btn"]
        btn_area = wdict["btn_area"]

        for child in btn_area.winfo_children():
            child.pack_forget()

        if poste["statut"] == "libre":
            main_action_btn.config(text="▶️ DÉMARRER", bg="#27AE60", command=lambda p=poste: self.start_session(p))
            main_action_btn.pack(fill=tk.X)
        elif poste["statut"] == "maintenance":
            main_action_btn.config(text="🔧 RÉPARER", bg="#F39C12", command=lambda p=poste: self.repair_poste(p))
            main_action_btn.pack(fill=tk.X)
        else: # Occupé
            main_action_btn.config(text="⚙️ GÉRER", bg="#3498DB", command=lambda p=poste: self.manage_session(p))
            main_action_btn.pack(fill=tk.X)


    def get_filtered_postes(self):
        """Retourne les postes filtrés en comparant en MAJUSCULES et en enlevant les espaces."""
        sel_raw = (self.selected_console_filter.get() or "").strip()
        sel = normalize_console_name(sel_raw) if sel_raw else ""
        if DEBUG:
            print("DEBUG FILTER SEL_RAW:", repr(sel_raw), "-> SEL:", sel)
            print("DEBUG available types:", [p.get("type_console") for p in self.postes_data.values()])
        if sel in ("TOUT", "ALL", ""):
            return self.postes_data
        result = {}
        for pid, poste in self.postes_data.items():
            try:
                tc = normalize_console_name(poste.get("type_console") or "")
                if tc == sel:
                    result[pid] = poste
            except Exception:
                continue
        return result

    def update_stats(self):
        """Met à jour les statistiques affichées."""
        libres = sum(1 for p in self.postes_data.values() if p["statut"] == "libre")
        occupes = sum(1 for p in self.postes_data.values() if p["statut"] == "occupe")
        maintenance = sum(1 for p in self.postes_data.values() if p["statut"] == "maintenance")
        recette = sum(p["montant_paye"] for p in self.postes_data.values())
        try:
            self.stats_labels["Postes Libres"].config(text=str(libres))
            self.stats_labels["Postes Occupés"].config(text=str(occupes))
            self.stats_labels["En Maintenance"].config(text=str(maintenance))
            if self.recette_visible:
                self.stats_labels["Recette du Jour"].config(text=f"{recette} F")
            else:
                self.stats_labels["Recette du Jour"].config(text="••••")
        except Exception:
            pass

    def update_time(self):
        """Met à jour l'heure affichée dans l'en-tête."""
        current_time = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
        self.time_label.config(text=current_time)
        self.root.after(1000, self.update_time)

    def add_alert(self, message):
        """Ajoute un message à la zone d'alertes."""
        current_time = datetime.now().strftime("%H:%M")
        alert_message = f"[{current_time}] {message}\n"
        self.root.after(0, lambda: (self.alert_text.insert(tk.END, alert_message), self.alert_text.see(tk.END)))
        def trim():
            lines = self.alert_text.get("1.0", tk.END).split('\n')
            if len(lines) > 100:
                self.alert_text.delete("1.0", "2.0")
        self.root.after(50, trim)

    def start_timer(self):
        """Démarre un thread séparé pour mettre à jour les timers des postes."""
        def update_timer():
            while self.running:
                changed = False
                for poste in list(self.postes_data.values()):
                    if poste["statut"] == "occupe" and poste["temps_restant"] > 0:
                        poste["temps_restant"] -= 1
                        changed = True
                        if poste["temps_restant"] == 120:
                            self.add_alert(f"⚠️ {poste['nom']} - Plus que 2 minutes !")
                        elif poste["temps_restant"] == 0:
                            poste["statut"] = "libre"
                            poste["client_nom"] = ""
                            poste["montant_paye"] = 0
                            self.add_alert(f"🔴 {poste['nom']} - Session terminée")
                
                if changed:
                    self.root.after(0, lambda: (self._refresh_existing_cards(), self.update_stats()))
                
                if int(time.time()) % 5 == 0:
                    self.root.after(0, self.update_stats)
                
                time.sleep(1)
        
        threading.Thread(target=update_timer, daemon=True).start()

    def _refresh_existing_cards(self):
        """Met à jour uniquement le contenu des cartes déjà créées sans les recréer."""
        for pid, wdict in self.card_widgets.items():
            poste = self.postes_data.get(pid)
            if poste:
                self._update_card_widgets(poste, wdict)

    def filter_postes(self):
        """Applique le filtre sélectionné et met à jour l'affichage des postes."""
        val = (self.selected_console_filter.get() or "").strip()
        self.selected_console_filter.set(val.upper())
        if DEBUG:
            print("DEBUG filter_postes called. selected_console_filter:", repr(self.selected_console_filter.get()))
        self.update_postes_display(columns=COLUMNS)
        self.add_alert(f"🔍 Filtre appliqué: {self.selected_console_filter.get()}")

    def start_session(self, poste):
        """Démarre une nouvelle session sur un poste."""
        dialog = SessionDialog(self.root, poste)
        if dialog.result:
            success = self.trigger_hdmi_switch(poste)
            if success:
                self.add_alert(f"🔌 Switch HDMI activé pour {poste['nom']}")
            else:
                self.add_alert(f"❗ Echec switch HDMI (stub) pour {poste['nom']}")
            
            poste["statut"] = "occupe"
            poste["client_nom"] = dialog.result["client_nom"]
            poste["temps_restant"] = dialog.result["duree"] * 60
            poste["montant_paye"] = dialog.result["montant"]
            self.add_alert(f"▶️ Session démarrée - {poste['nom']} - {dialog.result['client_nom']}")
            self.update_postes_display(columns=COLUMNS)
            self.update_stats()

    def trigger_hdmi_switch(self, poste):
        """Simule l'activation d'un interrupteur HDMI."""
        try:
            print(f"[HDMI STUB] Activation HDMI pour {poste['nom']}")
            return True
        except Exception as e:
            print("[HDMI STUB] Erreur:", e)
            return False

    def manage_session(self, poste):
        """Gère une session en cours via un dialogue d'options."""
        options_dialog = tk.Toplevel(self.root)
        options_dialog.title(f"Options pour {poste['nom']}")
        options_dialog.geometry("300x150")
        options_dialog.resizable(False, False)
        options_dialog.transient(self.root)
        options_dialog.grab_set()

        frame = ttk.Frame(options_dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"Session de {poste['client_nom']}", font=("Arial", 11, "bold")).pack(pady=(0, 10))
        ttk.Label(frame, text=f"Temps restant: {poste['temps_restant']//60}:{poste['temps_restant']%60:02d}").pack(pady=(0, 15))

        btn_prolonger = tk.Button(frame, text="⏰ Prolonger la session", bg="#9B59B6", fg="white",
                                      font=("Arial", 9, "bold"), relief="flat", bd=0, padx=10, pady=5,
                                      command=lambda: self._close_options_and_action(options_dialog, self.extend_session, poste))
        btn_prolonger._original_bg = "#9B59B6"
        btn_prolonger.bind("<Enter>", self._on_button_enter)
        btn_prolonger.bind("<Leave>", self._on_button_leave)
        btn_prolonger.pack(fill=tk.X, pady=5)

        btn_arreter = tk.Button(frame, text="⏹️ Arrêter la session", bg="#E74C3C", fg="white",
                                    font=("Arial", 9, "bold"), relief="flat", bd=0, padx=10, pady=5,
                                    command=lambda: self._close_options_and_action(options_dialog, self._stop_session, poste))
        btn_arreter._original_bg = "#E74C3C"
        btn_arreter.bind("<Enter>", self._on_button_enter)
        btn_arreter.bind("<Leave>", self._on_button_leave)
        btn_arreter.pack(fill=tk.X, pady=5)
        
        options_dialog.wait_window(options_dialog)

    def _close_options_and_action(self, dialog, action_func, poste):
        """Ferme le dialogue d'options et exécute l'action choisie."""
        dialog.destroy()
        action_func(poste)

    def _stop_session(self, poste):
        """Logique pour arrêter une session."""
        if messagebox.askyesno("Arrêter Session", f"Êtes-vous sûr de vouloir arrêter la session de {poste['client_nom']} sur {poste['nom']} ?"):
            poste["statut"] = "libre"
            poste["client_nom"] = ""
            poste["temps_restant"] = 0
            poste["montant_paye"] = 0
            self.add_alert(f"⏹️ Session arrêtée - {poste['nom']}")
            self.update_postes_display(columns=COLUMNS)
            self.update_stats()

    def extend_session(self, poste):
        """Prolonge une session existante."""
        result = simpledialog.askstring("Prolonger Session", "Minutes à ajouter:")
        if result:
            try:
                minutes = int(result)
                if minutes <= 0:
                    raise ValueError("Doit être > 0")
                poste["temps_restant"] += minutes * 60
                self.add_alert(f"⏰ {poste['nom']} prolongé de {minutes} minutes")
                self.update_postes_display(columns=COLUMNS)
            except ValueError:
                messagebox.showerror("Erreur", "Valeur invalide. Veuillez entrer un nombre entier positif.")

    def repair_poste(self, poste):
        """Marque un poste en maintenance comme réparé et disponible."""
        if messagebox.askyesno("Réparation", f"Marquer {poste['nom']} comme réparé et disponible ?"):
            poste["statut"] = "libre"
            self.add_alert(f"✅ {poste['nom']} réparé et disponible")
            self.update_postes_display(columns=COLUMNS)
            self.update_stats()

    def handle_bottom_button(self, button_text):
        """Gère les actions des boutons du bas de la sidebar."""
        if "Déconnexion" in button_text:
            if messagebox.askyesno("Déconnexion", "Êtes-vous sûr de vouloir vous déconnecter ?"):
                self.on_closing()
                try:
                    from interfaces.login import LoginWindow
                    LoginWindow().run()
                except Exception as e:
                    print(f"Erreur lors de la reconnexion: {e}")
        elif "Accueil" in button_text:
            self.selected_console_filter.set("TOUT")
            self.update_postes_display(columns=COLUMNS)
            self.add_alert("🏠 Retour à l'accueil")
        else:
            self.add_alert(f"⚙️ {button_text} - Fonctionnalité en développement")

    def on_closing(self):
        """Gère la fermeture propre de l'application."""
        self.running = False
        try:
            self.root.destroy()
        except:
            pass

    def run(self):
        """Lance la boucle principale de Tkinter."""
        self.root.mainloop()


# ----------------- SessionDialog (Dialogue pour démarrer une session) -----------------
class SessionDialog:
    def __init__(self, parent, poste):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"Démarrer Session sur {poste['nom']}")
        self.dialog.geometry("420x450")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        main_frame = ttk.Frame(self.dialog, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text=f"🎮 Nouvelle Session sur {poste['nom']}", font=("Arial", 13, "bold")).pack(pady=(0, 8))

        ttk.Label(main_frame, text="Nom du client:").pack(anchor=tk.W)
        self.client_entry = ttk.Entry(main_frame, font=("Arial", 11))
        self.client_entry.pack(fill=tk.X, pady=(4, 8))

        ttk.Label(main_frame, text="Montant payé (FCFA):").pack(anchor=tk.W)
        self.montant_entry = ttk.Entry(main_frame, font=("Arial", 11))
        self.montant_entry.pack(fill=tk.X, pady=(4, 8))

        ttk.Label(main_frame, text="Tarification:").pack(anchor=tk.W)
        self.tariffs = [
            {"key": "standard", "label": "Standard - 50 FCFA = 6 min", "mpf": 6 / 50},
            {"key": "promo", "label": "Promo - 100 FCFA = 15 min", "mpf": 15 / 100},
            {"key": "custom", "label": "Custom - définir X FCFA = Y min", "mpf": None}
        ]
        self.tariff_names = [t["label"] for t in self.tariffs]
        self.tariff_var = tk.StringVar(value=self.tariff_names[0])
        self.tariff_combo = ttk.Combobox(main_frame, values=self.tariff_names, state="readonly",
                                         textvariable=self.tariff_var)
        self.tariff_combo.pack(fill=tk.X, pady=(4, 8))
        self.tariff_combo.bind("<<ComboboxSelected>>", self._on_tariff_change)

        self.custom_frame = ttk.Frame(main_frame)
        ttk.Label(self.custom_frame, text="X FCFA =").grid(row=0, column=0, sticky=tk.W, padx=(0,4))
        self.custom_fcfa = ttk.Entry(self.custom_frame, width=8, font=("Arial", 11))
        self.custom_fcfa.grid(row=0, column=1, padx=(6, 12))
        ttk.Label(self.custom_frame, text="Y minutes").grid(row=0, column=2, sticky=tk.W, padx=(0,4))
        self.custom_minutes = ttk.Entry(self.custom_frame, width=8, font=("Arial", 11))
        self.custom_minutes.grid(row=0, column=3)
        self.custom_frame.pack_forget()

        ttk.Label(main_frame, text="Durée (minutes):").pack(anchor=tk.W)
        self.duree_entry = ttk.Entry(main_frame, font=("Arial", 11))
        self.duree_entry.pack(fill=tk.X, pady=(4, 8))

        calc_frame = ttk.Frame(main_frame)
        calc_frame.pack(fill=tk.X, pady=(0, 8))
        calc_btn = tk.Button(calc_frame, text="Calculer durée depuis montant", font=("Arial", 9, "bold"),
                             bg="#3498DB", fg="white", relief="flat", bd=0, padx=10, pady=5,
                             command=self.calculate_duration)
        calc_btn._original_bg = "#3498DB"
        calc_btn.bind("<Enter>", self._on_button_enter)
        calc_btn.bind("<Leave>", self._on_button_leave)
        calc_btn.pack(side=tk.LEFT)
        hint_label = ttk.Label(calc_frame, text=" (si montant renseigné)", font=("Arial", 8))
        hint_label.pack(side=tk.LEFT, padx=(6, 0))

        bonus_frame = ttk.Frame(main_frame)
        bonus_frame.pack(fill=tk.X, pady=(6, 8))
        self.use_bonus_var = tk.BooleanVar(value=False)
        self.bonus_check = ttk.Checkbutton(bonus_frame, text="Utiliser un bonus (minutes)", variable=self.use_bonus_var,
                                           command=self._toggle_bonus)
        self.bonus_check.pack(side=tk.LEFT)
        self.bonus_minutes_entry = ttk.Entry(bonus_frame, width=8, state="disabled", font=("Arial", 11))
        self.bonus_minutes_entry.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(bonus_frame, text="min").pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(main_frame,
                  text="Ex: montant=200, durée calculée automatiquement selon la grille",
                  font=("Arial", 8)).pack(anchor=tk.W, pady=(4, 8))

        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(8, 0))

        ok_btn = tk.Button(buttons_frame, text="Valider", bg="#27AE60", fg="white",
                           font=("Arial", 9, "bold"), relief="flat", bd=0, padx=10, pady=5,
                           command=self.on_ok)
        ok_btn._original_bg = "#27AE60"
        ok_btn.bind("<Enter>", self._on_button_enter)
        ok_btn.bind("<Leave>", self._on_button_leave)
        ok_btn.pack(side=tk.RIGHT, padx=(6, 0))

        cancel_btn = tk.Button(buttons_frame, text="Annuler", bg="#E74C3C", fg="white",
                               font=("Arial", 9, "bold"), relief="flat", bd=0, padx=10, pady=5,
                               command=self.on_cancel)
        cancel_btn._original_bg = "#E74C3C"
        cancel_btn.bind("<Enter>", self._on_button_enter)
        cancel_btn.bind("<Leave>", self._on_button_leave)
        cancel_btn.pack(side=tk.RIGHT)

        self.dialog.bind("<Return>", lambda e: self.on_ok())
        self.dialog.bind("<Escape>", lambda e: self.on_cancel())

        self.client_entry.focus_set()
        parent.wait_window(self.dialog)

    def _on_tariff_change(self, event=None):
        sel = self.tariff_var.get()
        if sel == self.tariff_names[-1]:
            self.custom_frame.pack(fill=tk.X, pady=(0, 8))
        else:
            self.custom_frame.pack_forget()

    def _toggle_bonus(self):
        if self.use_bonus_var.get():
            self.bonus_minutes_entry.config(state="normal")
            self.bonus_minutes_entry.delete(0, tk.END)
            self.bonus_minutes_entry.insert(0, "0")
        else:
            self.bonus_minutes_entry.delete(0, tk.END)
            self.bonus_minutes_entry.config(state="disabled")

    def calculate_duration(self):
        montant_txt = self.montant_entry.get().strip()
        if not montant_txt:
            messagebox.showinfo("Info", "Veuillez entrer un montant pour calculer la durée.")
            return
        try:
            montant = int(montant_txt)
            if montant <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Erreur", "Montant invalide. Entrez un entier (FCFA).")
            return
        sel = self.tariff_var.get()
        tariff = next((t for t in self.tariffs if t["label"] == sel), None)
        minutes = 0
        if tariff is None:
            messagebox.showerror("Erreur", "Tarif inconnu")
            return
        if tariff["mpf"] is not None:
            minutes = int(montant * tariff["mpf"])
        else:
            x_txt = self.custom_fcfa.get().strip()
            y_txt = self.custom_minutes.get().strip()
            try:
                x = int(x_txt); y = int(y_txt)
                if x <= 0 or y <= 0:
                    raise ValueError()
                mpf = y / x
                minutes = int(montant * mpf)
            except ValueError:
                messagebox.showerror("Erreur", "Valeurs custom invalides. Exemple: X=50, Y=6")
                return
        if minutes <= 0 and montant > 0:
            minutes = 1
        bonus = 0
        if self.use_bonus_var.get():
            try:
                bonus_txt = self.bonus_minutes_entry.get().strip()
                bonus = int(bonus_txt) if bonus_txt else 0
                if bonus < 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Erreur", "Minutes bonus invalides.")
                return
        total = minutes + bonus
        self.duree_entry.delete(0, tk.END)
        self.duree_entry.insert(0, str(total))
        messagebox.showinfo("Durée calculée", f"Durée: {minutes} min + bonus {bonus} min = {total} min")

    def on_ok(self):
        client_nom = self.client_entry.get().strip()
        montant_txt = self.montant_entry.get().strip()
        duree_txt = self.duree_entry.get().strip()
        if not client_nom:
            messagebox.showerror("Erreur", "Veuillez entrer le nom du client.")
            return
        try:
            montant = int(montant_txt)
            if montant < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Erreur", "Montant invalide. Entrez un nombre entier (FCFA).")
            return
        if not duree_txt:
            self.calculate_duration()
            duree_txt = self.duree_entry.get().strip()
        try:
            duree = int(duree_txt)
            if duree <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Erreur", "Durée invalide. Entrez un nombre entier de minutes (>0).")
            return
        bonus_minutes = 0
        if self.use_bonus_var.get():
            try:
                bonus_txt = self.bonus_minutes_entry.get().strip()
                bonus_minutes = int(bonus_txt) if bonus_txt else 0
                if bonus_minutes < 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Erreur", "Minutes bonus invalides.")
                return
        self.result = {"client_nom": client_nom, "montant": montant, "duree": duree}
        self.dialog.destroy()

    def on_cancel(self):
        self.result = None
        self.dialog.destroy()


if __name__ == "__main__":
    ui = ManagerInterface(user_id=1)
    ui.run()

