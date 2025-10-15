# interfaces/admin_interface.py

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from models.database import DatabaseManager
from config.settings import DATABASE_PATH
import os
import bcrypt
import json
import sys
import glob
import platform
import sqlite3
import math

# Bonus manager (optionnel — protège l'import si le fichier n'existe pas)
try:
    from app.bonus_simple import BonusManager
except Exception:
    BonusManager = None


class AdminInterface:
    def __init__(self, user_id):
        self.user_id = user_id
        self.root = tk.Tk()
        self.root.title("RDM gSalle - Interface Administrateur")
        try:
            self.root.state('zoomed')
        except Exception:
            pass

        self.db = DatabaseManager(DATABASE_PATH)
        self.current_user_info = self.get_user_info()

        self.setup_styles()
        self.settings_entries = {}
        self.tariff_sub_sections_map = {}

        # lists stockées en config
        self.currencies = []
        self.serial_ports = []

        # placeholders
        self.console_groups_tree = None
        self.tariffs_tree = None
        self.physical_postes_tree = None
        self.poste_console_groups_listbox = None

        # Bonus manager (si disponible)
        try:
            if BonusManager:
                # on passe l'instance de DatabaseManager pour réutiliser la même connexion/config
                self.bonus_manager = BonusManager(self.db)
                try:
                    # tenter d'exécuter la migration (idempotent)
                    self.bonus_manager.run_migrations()
                except Exception:
                    pass
            else:
                self.bonus_manager = None
        except Exception:
            self.bonus_manager = None

        self.create_widgets()
        self.load_users()

        self._ensure_config_table()
        self._load_lists_from_config()

        # migration / ensure schema for physical_postes supports outputs field
        self._ensure_physical_postes_schema()

        # detect serial ports & merge
        detected = self.detect_serial_ports()
        for p in detected:
            if p not in self.serial_ports:
                self.serial_ports.append(p)
        self._set_config_json("serial_ports", self.serial_ports)

        # ensure UI comboboxes updated
        self._refresh_currency_combobox()
        self._refresh_serialport_combobox()

        # initial load settings
        self.load_settings_for_current_section()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ---------------- Styles ----------------
    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure("Light.TFrame", background="#F0F2F5")
        style.configure("Light.TLabel", background="#F0F2F5", foreground="#2C3E50")
        try:
            style.element_create("Light.TLabelFrame.border", "from", "clam", "LabelFrame.border")
            style.element_create("Light.TLabelFrame.padding", "from", "clam", "LabelFrame.padding")
            style.element_create("Light.TLabelFrame.label", "from", "clam", "LabelFrame.label")
            style.layout("Light.TLabelFrame",
                         [("Light.TLabelFrame.border", {"sticky": "nswe", "border": "1", "children":
                           [("Light.TLabelFrame.padding", {"sticky": "nswe", "children":
                             [("Light.TLabelFrame.label", {"sticky": "nw"})]})]})])
        except Exception:
            pass
        style.configure("Light.TLabelFrame", background="#F0F2F5", foreground="#2C3E50")
        style.configure("SectionTitle.TLabel", font=("Arial", 11, "bold"), background="#F0F2F5", foreground="#2C3E50")
        style.configure("SettingsMenu.TButton", font=("Arial", 10, "bold"), background="#4A698A", foreground="white",
                        relief="flat", bd=0, pady=8, anchor="w", justify="left")
        style.map("SettingsMenu.TButton", background=[('active', '#6A8CAE')], foreground=[('active', 'white')])
        style.configure("TariffSubMenu.TButton", font=("Arial", 9), background="#6A8CAE", foreground="white",
                        relief="flat", bd=0, padx=8, pady=6, anchor="w", justify="left")
        style.map("TariffSubMenu.TButton", background=[('active', '#8BAECF')], foreground=[('active', 'white')])
        style.configure("White.Treeview",
                        background="white",
                        fieldbackground="white",
                        foreground="#2C3E50",
                        rowheight=22)

    # ---------------- DB helpers ----------------
    def _ensure_config_table(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS config (cle TEXT PRIMARY KEY, valeur TEXT)")
                conn.commit()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de garantir la table config: {e}")

    def _get_config(self, key, default=None):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT valeur FROM config WHERE cle = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            print(f"[DEBUG] Erreur lecture config {key}: {e}")
            return default

    def _set_config(self, key, value):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (key, value))
                conn.commit()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'enregistrer la configuration {key}: {e}")

    def _get_config_json(self, key, default=None):
        raw = self._get_config(key, None)
        if raw is None:
            return default if default is not None else []
        try:
            return json.loads(raw)
        except Exception:
            return default if default is not None else []

    def _set_config_json(self, key, obj):
        try:
            self._set_config(key, json.dumps(obj))
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'enregistrer la configuration {key}: {e}")

    # ---------------- Serial port detection ----------------
    def detect_serial_ports(self):
        ports = []
        try:
            import serial.tools.list_ports as list_ports
            for p in list_ports.comports():
                ports.append(p.device)
            seen = []
            res = []
            for p in ports:
                if p not in seen:
                    seen.append(p)
                    res.append(p)
            return res
        except Exception:
            pass
        system = platform.system().lower()
        if system == "windows":
            return [f"COM{i}" for i in range(1, 13)]
        else:
            patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*", "/dev/cu.*"]
            found = []
            for pat in patterns:
                found.extend(glob.glob(pat))
            if found:
                seen = []
                res = []
                for p in found:
                    if p not in seen:
                        seen.append(p)
                        res.append(p)
                return res
            if system == "darwin":
                return ["/dev/cu.usbserial", "/dev/cu.usbmodem"]
            return ["/dev/ttyUSB0", "/dev/ttyACM0"]

    # ---------------- Ensure physical_postes schema (migration/support outputs) ----------------
    def _ensure_physical_postes_schema(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS physical_postes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        numero INTEGER UNIQUE NOT NULL,
                        nom TEXT NOT NULL,
                        console_group_ids TEXT,
                        switch_port INTEGER,
                        outputs TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            print("[DEBUG] _ensure_physical_postes_schema error:", e)

    # ---------------- Export / Import ----------------
    def export_config_to_file(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT cle, valeur FROM config")
                data = {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de lire la configuration: {e}")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")], title="Exporter la configuration")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Exporté", f"Configuration exportée vers :\n{path}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'écrire le fichier : {e}")

    def import_config_from_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")], title="Importer configuration JSON")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le fichier : {e}")
            return
        preview = tk.Toplevel(self.root)
        preview.title("Prévisualisation import - Confirmer")
        preview.geometry("600x400")
        preview.transient(self.root)
        frm = ttk.Frame(preview, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Prévisualisation des clés chargées (cliquez sur 'Confirmer' pour importer) :", style="Light.TLabel").pack(anchor=tk.W)
        text = tk.Text(frm, wrap=tk.NONE)
        text.pack(fill=tk.BOTH, expand=True, pady=(6,6))
        for k, v in data.items():
            display = v
            if isinstance(display, (list, dict)):
                display = json.dumps(display)
            if len(display) > 350:
                display = display[:350] + " ... (truncated)"
            text.insert(tk.END, f"{k} : {display}\n\n")

        def do_import():
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    for k, v in data.items():
                        val = v
                        if isinstance(v, (list, dict)):
                            val = json.dumps(v)
                        cursor.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (k, str(val)))
                    conn.commit()
                messagebox.showinfo("Importé", "Configuration importée avec succès.")
                self._load_lists_from_config()
                self._refresh_currency_combobox()
                self._refresh_serialport_combobox()
                self.load_settings_for_current_section()
                preview.destroy()
            except Exception as e:
                messagebox.showerror("Erreur BD", f"Impossible d'importer la configuration : {e}")

        btn_frame = ttk.Frame(frm)
        btn_frame.pack(fill=tk.X, pady=(6,0))
        ttk.Button(btn_frame, text="Confirmer Import", command=do_import).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btn_frame, text="Annuler", command=preview.destroy).pack(side=tk.RIGHT)

    # ---------------- User info ----------------
    def get_user_info(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)")
                cursor.execute("SELECT username, role FROM users WHERE id = ?", (self.user_id,))
                result = cursor.fetchone()
                if result:
                    return {"username": result[0], "role": result[1]}
        except Exception as e:
            print(f"Erreur get_user_info: {e}")
        return {"username": "Admin", "role": "admin"}

    # ---------------- Main UI ----------------
    def create_widgets(self):
        main_container = ttk.Frame(self.root, style="Light.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True)

        header_frame = tk.Frame(main_container, bg="#34495E", height=60)
        header_frame.pack(fill=tk.X, pady=(0,10))
        header_frame.pack_propagate(False)
        title_label = tk.Label(header_frame, text="👑 RDM gSalle - Administration", font=("Arial", 20, "bold"), bg="#34495E", fg="white")
        title_label.pack(side=tk.LEFT, padx=20, pady=10)
        user_label = tk.Label(header_frame, text=f"Admin: {self.current_user_info['username']}", font=("Arial", 12), bg="#34495E", fg="#BDC3C7")
        user_label.pack(side=tk.RIGHT, padx=20, pady=10)

        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        reports_tab = ttk.Frame(self.notebook, style="Light.TFrame")
        self.notebook.add(reports_tab, text="📊 Rapports")
        ttk.Label(reports_tab, text="Section Rapports (en développement)", font=("Arial", 14), style="Light.TLabel").pack(pady=50)

        settings_main_tab = ttk.Frame(self.notebook, style="Light.TFrame")
        self.notebook.add(settings_main_tab, text="⚙️ Paramètres Généraux")
        self.create_settings_main_tab(settings_main_tab)

        users_tab = ttk.Frame(self.notebook, style="Light.TFrame")
        self.notebook.add(users_tab, text="👥 Gestion des Utilisateurs")
        self.create_users_tab(users_tab)

        status_bar = tk.Frame(self.root, bg="#34495E", height=24)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        status_bar.pack_propagate(False)
        self.status_label = tk.Label(status_bar, text="✅ Interface Administrateur chargée", font=("Arial", 9), bg="#34495E", fg="#27AE60")
        self.status_label.pack(side=tk.LEFT, padx=15, pady=2)
        logout_btn = tk.Button(status_bar, text="🚪 Déconnexion", command=self.logout, font=("Arial", 9, "bold"), bg="#E74C3C", fg="white", relief="flat", bd=0, padx=10, pady=2)
        logout_btn.pack(side=tk.RIGHT, padx=15, pady=2)

    # ---------------- Users tab ----------------
    def create_users_tab(self, parent_tab):
        form_frame = ttk.LabelFrame(parent_tab, text="Ajouter / Modifier Utilisateur", style="Light.TLabelFrame")
        form_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10, ipadx=5, ipady=5)
        ttk.Label(form_frame, text="Nom d'utilisateur:", style="Light.TLabel").pack(anchor=tk.W, pady=(0,5))
        self.username_entry = ttk.Entry(form_frame, width=30)
        self.username_entry.pack(fill=tk.X, pady=(0,10))
        ttk.Label(form_frame, text="Mot de passe:", style="Light.TLabel").pack(anchor=tk.W, pady=(0,5))
        self.password_entry = ttk.Entry(form_frame, width=30, show="*")
        self.password_entry.pack(fill=tk.X, pady=(0,10))
        ttk.Label(form_frame, text="Rôle:", style="Light.TLabel").pack(anchor=tk.W, pady=(0,5))
        self.role_var = tk.StringVar(value="manager")
        self.role_combo = ttk.Combobox(form_frame, textvariable=self.role_var, state="readonly", values=["manager", "co_admin", "admin"], width=28)
        self.role_combo.pack(fill=tk.X, pady=(0,10))
        btn_frame = ttk.Frame(form_frame, style="Light.TFrame")
        btn_frame.pack(fill=tk.X, pady=(10,0))
        ttk.Button(btn_frame, text="➕ Ajouter", command=self.add_user).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(btn_frame, text="💾 Modifier", command=self.update_user).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(btn_frame, text="🗑️ Supprimer", command=self.delete_user).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(btn_frame, text="✖️ Annuler", command=self.clear_user_form).pack(side=tk.LEFT)
        list_frame = ttk.LabelFrame(parent_tab, text="Liste des Utilisateurs", style="Light.TLabelFrame")
        list_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.users_tree = ttk.Treeview(list_frame, columns=("ID", "Nom d'utilisateur", "Rôle"), show="headings")
        self.users_tree.heading("ID", text="ID")
        self.users_tree.heading("Nom d'utilisateur", text="Nom d'utilisateur")
        self.users_tree.heading("Rôle", text="Rôle")
        self.users_tree.column("ID", width=50, stretch=tk.NO)
        self.users_tree.column("Nom d'utilisateur", width=150, stretch=tk.YES)
        self.users_tree.column("Rôle", width=100, stretch=tk.NO)
        self.users_tree.pack(fill=tk.BOTH, expand=True)
        self.users_tree.bind("<<TreeviewSelect>>", self.on_user_select)

    # ---------------- Settings main tab ----------------
    def create_settings_main_tab(self, parent_tab):
        self.settings_sidebar_frame = ttk.Frame(parent_tab, style="Light.TFrame", width=240)
        self.settings_sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10,0), pady=10)
        self.settings_sidebar_frame.pack_propagate(False)
        self.settings_content_frame = ttk.Frame(parent_tab, style="Light.TFrame")
        self.settings_content_frame.pack(fill=tk.BOTH, expand=True, padx=(0,10), pady=10)
        self.settings_sections_map = {
            "Tarification": "create_tarification_menu",
            "Bonus Simples": "create_bonus_simples_section",
            "Ticket de fidélité": "create_tickets_section",
            "Titres de Joueur": "create_titres_section",
            "Bonus Spéciaux": "create_bonus_speciaux_section",
            "Abonnements": "create_abonnements_section",
        }
        menu_items = [
            ("💰", "Tarification"),
            ("🎁", "Bonus Simples"),
            ("🎫", "Ticket de fidélité"),
            ("🏆", "Titres de Joueur"),
            ("✨", "Bonus Spéciaux"),
            ("📦", "Abonnements"),
        ]
        for icon, text_content in menu_items:
            btn = ttk.Button(self.settings_sidebar_frame, text=f"{icon} {text_content}", style="SettingsMenu.TButton",
                             command=lambda t=text_content: self.show_settings_section(t))
            btn.pack(fill=tk.X, pady=2, padx=(5,5))
        save_btn = ttk.Button(self.settings_sidebar_frame, text="💾 Sauvegarder TOUS", style="SettingsMenu.TButton", command=self.save_general_settings)
        save_btn.pack(fill=tk.X, pady=(12,5), padx=5)
        export_btn = ttk.Button(self.settings_sidebar_frame, text="⬇️ Exporter Config", style="SettingsMenu.TButton", command=self.export_config_to_file)
        export_btn.pack(fill=tk.X, pady=(6,5), padx=5)
        import_btn = ttk.Button(self.settings_sidebar_frame, text="⬆️ Importer Config", style="SettingsMenu.TButton", command=self.import_config_from_file)
        import_btn.pack(fill=tk.X, pady=(0,10), padx=5)
        if self.settings_sections_map:
            first_section_name = list(self.settings_sections_map.keys())[0]
            self.show_settings_section(first_section_name)

    def show_settings_section(self, section_name):
        for widget in self.settings_content_frame.winfo_children():
            widget.destroy()
        self.settings_entries = {}
        create_section_func_name = self.settings_sections_map.get(section_name)
        if create_section_func_name:
            create_section_func = getattr(self, create_section_func_name)
            create_section_func(self.settings_content_frame)
            if section_name != "Tarification":
                self.load_settings_for_current_section()
        else:
            ttk.Label(self.settings_content_frame, text="Section non trouvée.", style="Light.TLabel").pack(pady=50)

    # ---------------- Tarification menu ----------------
    def create_tarification_menu(self, parent):
        tariff_main_container = ttk.Frame(parent, style="Light.TFrame")
        tariff_main_container.pack(fill=tk.BOTH, expand=True)
        tariff_menu_frame = ttk.Frame(tariff_main_container, style="Light.TFrame", width=300)
        tariff_menu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10,0), pady=10)
        tariff_menu_frame.pack_propagate(False)
        title_frame = ttk.LabelFrame(tariff_menu_frame, text="💰 Gestion de la Tarification", style="Light.TLabelFrame")
        title_frame.pack(fill=tk.X, pady=15, padx=5)
        self.tariff_sub_section_content_frame = ttk.Frame(tariff_main_container, style="Light.TFrame")
        self.tariff_sub_section_content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0,10), pady=10)
        self.tariff_sub_sections_map = {
            "Paramètres Généraux": "create_tarification_general_settings_section",
            "Groupes de Consoles & Tarifs": "create_console_groups_section",
            "Gestion des Postes Physiques": "create_physical_postes_section",
        }
        sub_menu_items = [
            ("⚙️", "Paramètres Généraux"),
            ("🎮", "Groupes de Consoles & Tarifs"),
            ("🖥️", "Gestion des Postes Physiques"),
        ]
        for icon, text_content in sub_menu_items:
            btn = ttk.Button(tariff_menu_frame, text=f"{icon} {text_content}", style="TariffSubMenu.TButton",
                             command=lambda t=text_content: self.show_tarification_sub_section(t))
            btn.pack(fill=tk.X, pady=2, padx=5)
        if sub_menu_items:
            self.show_tarification_sub_section(sub_menu_items[0][1])

    def show_tarification_sub_section(self, sub_section_name):
        for widget in self.tariff_sub_section_content_frame.winfo_children():
            widget.destroy()
        self.settings_entries = {}
        create_sub_section_func_name = self.tariff_sub_sections_map.get(sub_section_name)
        if create_sub_section_func_name:
            create_sub_section_func = getattr(self, create_sub_section_func_name)
            create_sub_section_func(self.tariff_sub_section_content_frame)
            # call load settings to populate the widgets that were created
            self.load_settings_for_current_section()
        else:
            ttk.Label(self.tariff_sub_section_content_frame, text="Sous-section non trouvée.", style="Light.TLabel").pack(pady=50)

    # ---------------- Tarification General ----------------
    def create_tarification_general_settings_section(self, parent):
        frame = ttk.LabelFrame(parent, text="", style="Light.TLabelFrame")
        frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(frame, text="⚙️ Paramètres Généraux de Tarification", font=("Arial", 12, "bold"), style="Light.TLabel").pack(anchor=tk.W, pady=(0,10))
        # Currency
        row_frame = ttk.Frame(frame)
        row_frame.pack(fill=tk.X, pady=(0,8))
        ttk.Label(row_frame, text="Devise active:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,6))
        self.devise_var = tk.StringVar()
        self.devise_combo = ttk.Combobox(row_frame, textvariable=self.devise_var, state="readonly", width=12)
        self.devise_combo.pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(row_frame, text="Gérer Devises", command=self.open_currency_manager).pack(side=tk.LEFT)
        self.settings_entries['devise'] = self.devise_combo
        ttk.Label(frame, text="(Ajouter / gérer les devises via 'Gérer Devises')", style="Light.TLabel").pack(anchor=tk.W, pady=(0,6))
        # Serial port
        row_frame2 = ttk.Frame(frame)
        row_frame2.pack(fill=tk.X, pady=(6,8))
        ttk.Label(row_frame2, text="Port Série actif:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,6))
        self.serial_port_var = tk.StringVar()
        self.serial_port_combo = ttk.Combobox(row_frame2, textvariable=self.serial_port_var, state="readonly", width=20)
        self.serial_port_combo.pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(row_frame2, text="Gérer Ports Série", command=self.open_serial_port_manager).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(row_frame2, text="Détecter", command=self._detect_and_refresh_ports).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(row_frame2, text="Scanner en fond", command=self.toggle_bg_scan).pack(side=tk.LEFT, padx=(6,0))
        self.settings_entries['serial_port_active'] = self.serial_port_combo
        ttk.Label(frame, text="(Ports définis manuellement par l'admin, ou détectés)", style="Light.TLabel").pack(anchor=tk.W, pady=(0,6))
        # Baud
        ttk.Label(frame, text="Vitesse (Baud Rate):", style="Light.TLabel").pack(anchor=tk.W, pady=(6,4))
        self.baud_rate_var = tk.StringVar(value="9600")
        self.baud_rate_combo = ttk.Combobox(frame, textvariable=self.baud_rate_var, state="readonly",
                                            values=["9600", "19200", "38400", "57600", "115200"], width=18)
        self.baud_rate_combo.pack(fill=tk.X, pady=(0,10))
        self.settings_entries['baud_rate'] = self.baud_rate_combo
        # standard tariff
        ttk.Label(frame, text="Tarif Standard (FCFA pour 6 min):", style="Light.TLabel").pack(anchor=tk.W, pady=(0,5))
        self.standard_tariff_entry = ttk.Entry(frame, width=20)
        self.standard_tariff_entry.pack(fill=tk.X, pady=(0,10))
        self.settings_entries['standard_tariff_fcfa_per_6min'] = self.standard_tariff_entry
        ttk.Label(frame, text="Les paramètres ci-dessus sont utilisés comme valeurs par défaut.", style="Light.TLabel").pack(anchor=tk.W, pady=(6,0))
        self._refresh_currency_combobox()
        self._refresh_serialport_combobox()

    def toggle_bg_scan(self):
        messagebox.showinfo("Scanner", "Fonction de scan de ports en fond (prototype).")

    def _detect_and_refresh_ports(self):
        new_ports = self.detect_serial_ports()
        added = 0
        for p in new_ports:
            if p not in self.serial_ports:
                self.serial_ports.append(p)
                added += 1
        if added:
            self._set_config_json("serial_ports", self.serial_ports)
        self._refresh_serialport_combobox()
        messagebox.showinfo("Détection terminée", f"{len(new_ports)} ports détectés, {added} ajoutés à la liste.")

    # ---------------- Currency manager ----------------
    def open_currency_manager(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Gérer Devises")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("360x320")
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Devises disponibles:", style="Light.TLabel").pack(anchor=tk.W)
        listbox = tk.Listbox(frm, height=8)
        listbox.pack(fill=tk.BOTH, expand=True, pady=(6,6))
        for c in self.currencies:
            listbox.insert(tk.END, c)
        input_frame = ttk.Frame(frm)
        input_frame.pack(fill=tk.X, pady=(6,4))
        ttk.Label(input_frame, text="Nouvelle devise:", style="Light.TLabel").pack(side=tk.LEFT)
        new_entry = ttk.Entry(input_frame, width=10)
        new_entry.pack(side=tk.LEFT, padx=(6,6))

        def add_currency():
            val = new_entry.get().strip()
            if not val:
                messagebox.showerror("Erreur", "Entrez une devise.")
                return
            if val in self.currencies:
                messagebox.showerror("Erreur", "Cette devise existe déjà.")
                return
            self.currencies.append(val)
            listbox.insert(tk.END, val)
            new_entry.delete(0, tk.END)
            self._set_config_json("currencies", self.currencies)
            self._refresh_currency_combobox()

        def remove_currency():
            sel = listbox.curselection()
            if not sel:
                messagebox.showerror("Erreur", "Sélectionnez une devise à supprimer.")
                return
            idx = sel[0]
            val = listbox.get(idx)
            if messagebox.askyesno("Confirmer", f"Supprimer la devise '{val}' ?"):
                listbox.delete(idx)
                try:
                    self.currencies.remove(val)
                except:
                    pass
                active = self.devise_var.get()
                if active == val:
                    new_active = self.currencies[0] if self.currencies else ""
                    self.devise_var.set(new_active)
                    self._set_config("devise", new_active)
                self._set_config_json("currencies", self.currencies)
                self._refresh_currency_combobox()

        btns_frame = ttk.Frame(frm)
        btns_frame.pack(fill=tk.X, pady=(6,0))
        ttk.Button(btns_frame, text="➕ Ajouter", command=add_currency).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(btns_frame, text="🗑️ Supprimer", command=remove_currency).pack(side=tk.LEFT)
        ttk.Button(btns_frame, text="Fermer", command=dlg.destroy).pack(side=tk.RIGHT)

    def _refresh_currency_combobox(self):
        try:
            if not self.currencies:
                self.currencies = ["FCFA"]
                self._set_config_json("currencies", self.currencies)
            if getattr(self, "devise_combo", None):
                self.devise_combo['values'] = self.currencies
                active = self._get_config("devise", None)
                if active and active in self.currencies:
                    self.devise_var.set(active)
                elif self.currencies:
                    self.devise_var.set(self.currencies[0])
                    self._set_config("devise", self.currencies[0])
        except Exception:
            pass

    # ---------------- Serial port manager ----------------
    def open_serial_port_manager(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Gérer Ports Série")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("420x360")
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Ports série définis:", style="Light.TLabel").pack(anchor=tk.W)
        listbox = tk.Listbox(frm, height=8)
        listbox.pack(fill=tk.BOTH, expand=True, pady=(6,6))
        for p in self.serial_ports:
            listbox.insert(tk.END, p)
        input_frame = ttk.Frame(frm)
        input_frame.pack(fill=tk.X, pady=(6,4))
        ttk.Label(input_frame, text="Nouveau port:", style="Light.TLabel").pack(side=tk.LEFT)
        new_entry = ttk.Entry(input_frame, width=18)
        new_entry.pack(side=tk.LEFT, padx=(6,6))

        def add_port():
            val = new_entry.get().strip()
            if not val:
                messagebox.showerror("Erreur", "Entrez un port (ex: COM3 ou /dev/ttyUSB0).")
                return
            if val in self.serial_ports:
                messagebox.showerror("Erreur", "Ce port existe déjà.")
                return
            self.serial_ports.append(val)
            listbox.insert(tk.END, val)
            new_entry.delete(0, tk.END)
            self._set_config_json("serial_ports", self.serial_ports)
            self._refresh_serialport_combobox()

        def remove_port():
            sel = listbox.curselection()
            if not sel:
                messagebox.showerror("Erreur", "Sélectionnez un port à supprimer.")
                return
            idx = sel[0]
            val = listbox.get(idx)
            if messagebox.askyesno("Confirmer", f"Supprimer le port '{val}' ?"):
                listbox.delete(idx)
                try:
                    self.serial_ports.remove(val)
                except:
                    pass
                active = self.serial_port_var.get()
                if active == val:
                    new_active = self.serial_ports[0] if self.serial_ports else ""
                    self.serial_port_var.set(new_active)
                    self._set_config("serial_port_active", new_active)
                self._set_config_json("serial_ports", self.serial_ports)
                self._refresh_serialport_combobox()

        btns_frame = ttk.Frame(frm)
        btns_frame.pack(fill=tk.X, pady=(6,0))
        ttk.Button(btns_frame, text="➕ Ajouter", command=add_port).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(btns_frame, text="🗑️ Supprimer", command=remove_port).pack(side=tk.LEFT)
        ttk.Button(btns_frame, text="Détecter", command=lambda: (listbox.delete(0, tk.END), self._do_detect_fill_listbox(listbox))).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(btns_frame, text="Fermer", command=dlg.destroy).pack(side=tk.RIGHT)

    def _do_detect_fill_listbox(self, listbox_widget):
        new_ports = self.detect_serial_ports()
        added = 0
        for p in new_ports:
            if p not in self.serial_ports:
                self.serial_ports.append(p)
                added += 1
        self._set_config_json("serial_ports", self.serial_ports)
        listbox_widget.delete(0, tk.END)
        for p in self.serial_ports:
            listbox_widget.insert(tk.END, p)
        self._refresh_serialport_combobox()
        messagebox.showinfo("Détecter", f"{len(new_ports)} détectés, {added} nouveaux ajoutés.")

    def _refresh_serialport_combobox(self):
        try:
            if not self.serial_ports:
                detected = self.detect_serial_ports()
                if detected:
                    self.serial_ports = detected
                else:
                    if platform.system().lower() == "windows":
                        self.serial_ports = [f"COM{i}" for i in range(1,9)]
                    else:
                        self.serial_ports = ["/dev/ttyUSB0", "/dev/ttyACM0"]
                self._set_config_json("serial_ports", self.serial_ports)
            if getattr(self, "serial_port_combo", None):
                self.serial_port_combo['values'] = self.serial_ports
                active = self._get_config("serial_port_active", None)
                if active and active in self.serial_ports:
                    self.serial_port_var.set(active)
                elif self.serial_ports:
                    candidate = self.serial_ports[0]
                    self.serial_port_var.set(candidate)
                    self._set_config("serial_port_active", candidate)
        except Exception:
            pass

    # ---------------- Console Groups & Tariffs ----------------
    def create_console_groups_section(self, parent):
        frame = ttk.LabelFrame(parent, text="🎮 Groupes de Consoles & Tarifs", style="Light.TLabelFrame")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === FORMULAIRE GROUPE (sur 2 lignes pour éviter débordement) ===
        group_form_frame = ttk.Frame(frame, style="Light.TFrame")
        group_form_frame.pack(fill=tk.X, pady=(0,6))

        # Ligne 1: Nom + Icône combobox
        row1 = ttk.Frame(group_form_frame, style="Light.TFrame")
        row1.pack(fill=tk.X, pady=(0,4))

        ttk.Label(row1, text="Nom du Groupe:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.group_name_entry = ttk.Entry(row1, width=25)
        self.group_name_entry.pack(side=tk.LEFT, padx=(0,15))
        self.settings_entries['current_group_name'] = self.group_name_entry

        ttk.Label(row1, text="Icône:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.group_icon_var = tk.StringVar()
        default_icons = ["🎮", "🕹️", "📺", "🔷", "🔶", "🟦", "🟪", "🟩", "PS2", "PS3", "PS4", "PS5", "XBOX"]
        self.group_icon_combo = ttk.Combobox(row1, textvariable=self.group_icon_var, values=default_icons, width=8)
        self.group_icon_combo.pack(side=tk.LEFT, padx=(0,6))

        # Ligne 2: Icône personnalisée
        row2 = ttk.Frame(group_form_frame, style="Light.TFrame")
        row2.pack(fill=tk.X)

        ttk.Label(row2, text="Ou icône personnalisée:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.group_icon_custom_entry = ttk.Entry(row2, width=8)
        self.group_icon_custom_entry.pack(side=tk.LEFT, padx=(0,6))
        ttk.Label(row2, text="(Laisser vide pour utiliser la combobox)", style="Light.TLabel", foreground="#7F8C8D").pack(side=tk.LEFT)

        # === BOUTONS D'ACTION (ligne dédiée, bien visible) ===
        group_buttons_frame = ttk.Frame(frame, style="Light.TFrame")
        group_buttons_frame.pack(fill=tk.X, pady=(8,8))

        self.add_group_btn = ttk.Button(group_buttons_frame, text="➕ Ajouter Groupe", command=self.add_console_group, width=18)
        self.add_group_btn.pack(side=tk.LEFT, padx=(0,6))
        self.edit_group_btn = ttk.Button(group_buttons_frame, text="💾 Modifier Groupe", command=self.update_console_group, width=18)
        self.edit_group_btn.pack(side=tk.LEFT, padx=(0,6))
        self.delete_group_btn = ttk.Button(group_buttons_frame, text="🗑️ Supprimer Groupe", command=self.delete_console_group, width=18)
        self.delete_group_btn.pack(side=tk.LEFT)

        # === LISTE DES GROUPES (fond blanc) ===
        grp_list_frame = tk.Frame(frame, bg="white")
        grp_list_frame.pack(fill=tk.BOTH, expand=False, pady=(6,10))
        grp_list_scroll = ttk.Scrollbar(grp_list_frame, orient="vertical")
        grp_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.console_groups_tree = ttk.Treeview(grp_list_frame, columns=("ID","Nom","Icône"), show="headings", selectmode="browse", height=8, style="White.Treeview")
        self.console_groups_tree.heading("ID", text="ID", anchor=tk.W)
        self.console_groups_tree.heading("Nom", text="Nom du Groupe", anchor=tk.W)
        self.console_groups_tree.heading("Icône", text="Icône", anchor=tk.W)
        self.console_groups_tree.column("ID", width=40, stretch=tk.NO)
        self.console_groups_tree.column("Nom", width=150, stretch=tk.YES)
        self.console_groups_tree.column("Icône", width=80, stretch=tk.NO)
        self.console_groups_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.console_groups_tree.config(yscrollcommand=grp_list_scroll.set)
        grp_list_scroll.config(command=self.console_groups_tree.yview)

        self.console_groups_tree.bind("<<TreeviewSelect>>", self.on_console_group_select)

        # === SECTION TARIFS (SANS titre dupliqué) ===
        tariff_grid_frame = ttk.LabelFrame(frame, text="📋 Grille Tarifaire du Groupe Sélectionné", style="Light.TLabelFrame")
        tariff_grid_frame.pack(fill=tk.BOTH, expand=True, pady=(10,0))

        tariff_btn_frame = ttk.Frame(tariff_grid_frame, style="Light.TFrame")
        tariff_btn_frame.pack(fill=tk.X, pady=(6,6), padx=4)

        self.add_tariff_btn = ttk.Button(tariff_btn_frame, text="➕ Ajouter Tarif", command=self.add_tariff_entry, width=16)
        self.add_tariff_btn.pack(side=tk.LEFT, padx=(0,6))
        self.edit_tariff_btn = ttk.Button(tariff_btn_frame, text="💾 Modifier Tarif", command=self.update_tariff_entry, width=16)
        self.edit_tariff_btn.pack(side=tk.LEFT, padx=(0,6))
        self.delete_tariff_btn = ttk.Button(tariff_btn_frame, text="🗑️ Supprimer Tarif", command=self.delete_tariff_entry, width=16)
        self.delete_tariff_btn.pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(tariff_btn_frame, text="🔃 Réordonner", command=self.reorder_tariffs_current_group, width=14).pack(side=tk.LEFT, padx=(6,0))

        tariffs_frame = ttk.Frame(tariff_grid_frame, style="Light.TFrame")
        tariffs_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0,6))

        self.tariffs_tree = ttk.Treeview(tariffs_frame, columns=("Montant","Minutes"), show="headings", selectmode="browse", style="White.Treeview")
        self.tariffs_tree.heading("Montant", text="Montant (FCFA)", anchor=tk.W)
        self.tariffs_tree.heading("Minutes", text="Minutes", anchor=tk.W)
        self.tariffs_tree.column("Montant", width=140, stretch=tk.YES)
        self.tariffs_tree.column("Minutes", width=120, stretch=tk.YES)

        tariffs_scroll = ttk.Scrollbar(tariffs_frame, orient="vertical", command=self.tariffs_tree.yview)
        tariffs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tariffs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tariffs_tree.config(yscrollcommand=tariffs_scroll.set)

        self.tariffs_tree.bind("<<TreeviewSelect>>", self.on_tariff_select)

        # Chargement des données
        self.load_console_groups()

    def load_console_groups(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS console_groups "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, icon TEXT, tariffs TEXT)"
                )
                cursor.execute("SELECT id, name, icon, tariffs FROM console_groups ORDER BY name")
                rows = cursor.fetchall()

                if self.console_groups_tree and self.console_groups_tree.winfo_exists():
                    for item in self.console_groups_tree.get_children():
                        self.console_groups_tree.delete(item)

                for row in rows:
                    raw_tariffs = row[3]
                    if raw_tariffs is None:
                        tariffs_text = json.dumps([])
                    elif isinstance(raw_tariffs, str):
                        try:
                            json.loads(raw_tariffs)
                            tariffs_text = raw_tariffs
                        except Exception:
                            tariffs_text = json.dumps([])
                    else:
                        try:
                            tariffs_text = json.dumps(raw_tariffs)
                        except Exception:
                            tariffs_text = json.dumps([])

                    icon_text = row[2] if row[2] is not None else ""
                    if self.console_groups_tree and self.console_groups_tree.winfo_exists():
                        self.console_groups_tree.insert("", tk.END, values=(row[0], row[1], icon_text), tags=(tariffs_text,))

                # auto-select first item (if any)
                if self.console_groups_tree and self.console_groups_tree.get_children():
                    first = self.console_groups_tree.get_children()[0]
                    try:
                        self.console_groups_tree.selection_set(first)
                        self.console_groups_tree.focus(first)
                        self.on_console_group_select(None)
                    except Exception as e:
                        print(f"[DEBUG] error auto-selecting first console group: {e}")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de charger les groupes de consoles: {e}")
            print("[DEBUG] load_console_groups exception:", e)

    def add_console_group(self):
        name = self.group_name_entry.get().strip()
        icon = self._get_group_icon_value()
        if not name:
            messagebox.showerror("Erreur", "Le nom du groupe est requis.")
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM console_groups WHERE LOWER(name) = ?", (name.lower(),))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", f"Le groupe '{name}' existe déjà.")
                    return
                cursor.execute(
                    "INSERT INTO console_groups (name, icon, tariffs) VALUES (?, ?, ?)",
                    (name, icon, json.dumps([]))
                )
                conn.commit()
            messagebox.showinfo("Succès", f"Groupe '{name}' ajouté.")
            self.load_console_groups()
            self.clear_console_group_form()
            self.load_console_group_names_for_combo()
        except sqlite3.IntegrityError:
            messagebox.showerror("Erreur BD", f"Impossible d'ajouter le groupe '{name}' : nom déjà existant (contrainte UNIQUE).")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'ajouter le groupe: {e}")
            print("[DEBUG] add_console_group exception:", e)

    def update_console_group(self):
        try:
            sel = self.console_groups_tree.selection()
        except Exception:
            sel = []
        if not sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un groupe à modifier.")
            return
        selected_item = sel[0]
        group_id = self.console_groups_tree.item(selected_item, 'values')[0]
        name = self.group_name_entry.get().strip()
        icon = self._get_group_icon_value()
        if not name:
            messagebox.showerror("Erreur", "Le nom du groupe est requis.")
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM console_groups WHERE LOWER(name) = ?", (name.lower(),))
                row = cursor.fetchone()
                if row and str(row[0]) != str(group_id):
                    messagebox.showerror("Erreur", f"Impossible de renommer : le nom '{name}' est déjà utilisé par un autre groupe.")
                    return
                cursor.execute("UPDATE console_groups SET name = ?, icon = ? WHERE id = ?", (name, icon, group_id))
                conn.commit()
            messagebox.showinfo("Succès", f"Groupe '{name}' modifié.")
            self.load_console_groups()
            # reselect same id if present
            for iid in self.console_groups_tree.get_children():
                vals = self.console_groups_tree.item(iid, 'values')
                if str(vals[0]) == str(group_id):
                    try:
                        self.console_groups_tree.selection_set(iid)
                        self.console_groups_tree.focus(iid)
                        self.on_console_group_select(None)
                    except:
                        pass
                    break
            self.clear_console_group_form()
            self.load_console_group_names_for_combo()
        except sqlite3.IntegrityError:
            messagebox.showerror("Erreur BD", "Impossible de modifier le groupe : conflit de nom (contrainte UNIQUE).")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de modifier le groupe: {e}")
            print("[DEBUG] update_console_group exception:", e)

    def delete_console_group(self):
        try:
            sel = self.console_groups_tree.selection()
        except Exception:
            sel = []
        if not sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un groupe à supprimer.")
            return
        selected_item = sel[0]
        group_id = self.console_groups_tree.item(selected_item, 'values')[0]
        group_name = self.console_groups_tree.item(selected_item, 'values')[1]
        if messagebox.askyesno("Confirmer Suppression", f"Êtes-vous sûr de vouloir supprimer le groupe '{group_name}' ?"):
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    # remove group references from physical_postes.outputs if present
                    cursor.execute("SELECT id, outputs FROM physical_postes")
                    physicals = cursor.fetchall()
                    for p in physicals:
                        pid = p[0]
                        outs_raw = p[1]
                        if not outs_raw:
                            continue
                        try:
                            outs = json.loads(outs_raw)
                        except Exception:
                            outs = []
                        modified = False
                        for o in outs:
                            if o.get('group_id') == int(group_id):
                                o['group_id'] = None
                                modified = True
                        if modified:
                            cursor.execute("UPDATE physical_postes SET outputs = ? WHERE id = ?", (json.dumps(outs), pid))
                    cursor.execute("DELETE FROM console_groups WHERE id = ?", (group_id,))
                    conn.commit()
                    messagebox.showinfo("Succès", f"Groupe '{group_name}' supprimé.")
                    self.load_console_groups()
                    self.clear_console_group_form()
                    self.load_console_group_names_for_combo()
            except Exception as e:
                messagebox.showerror("Erreur BD", f"Impossible de supprimer le groupe: {e}")
                print("[DEBUG] delete_console_group exception:", e)

    def _get_group_icon_value(self):
        try:
            custom = self.group_icon_custom_entry.get().strip()
        except Exception:
            custom = ""
        try:
            combo = self.group_icon_combo.get().strip()
        except Exception:
            combo = ""
        return custom if custom else combo

    def on_console_group_select(self, event):
        try:
            sel = []
            try:
                sel = self.console_groups_tree.selection()
            except Exception:
                sel = []
            if sel:
                selected_item = sel[0]
                values = self.console_groups_tree.item(selected_item, 'values')
                self.selected_group_id = values[0]
                self.group_name_entry.delete(0, tk.END)
                self.group_name_entry.insert(0, values[1])
                icon_value = values[2] if len(values) > 2 else ""
                try:
                    if icon_value:
                        if icon_value in self.group_icon_combo['values']:
                            self.group_icon_combo.set(icon_value)
                            self.group_icon_custom_entry.delete(0, tk.END)
                        else:
                            self.group_icon_combo.set("")
                            self.group_icon_custom_entry.delete(0, tk.END)
                            self.group_icon_custom_entry.insert(0, icon_value)
                except Exception:
                    pass
                tariffs_json = None
                try:
                    tags = self.console_groups_tree.item(selected_item, 'tags')
                    tariffs_json = tags[0] if tags else None
                except Exception:
                    tariffs_json = None
                if hasattr(self, 'tariffs_tree') and self.tariffs_tree and self.tariffs_tree.winfo_exists():
                    self.load_tariffs_for_group(tariffs_json)
                else:
                    self.root.after(50, lambda: self._safe_load_tariffs_after_widget_ready(tariffs_json))
            else:
                self.clear_console_group_form()
                self.clear_tariffs_tree()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur sélection groupe: {e}")
            print("[DEBUG] on_console_group_select exception:", e)

    def _safe_load_tariffs_after_widget_ready(self, tariffs_json):
        try:
            if hasattr(self, 'tariffs_tree') and self.tariffs_tree and self.tariffs_tree.winfo_exists():
                self.load_tariffs_for_group(tariffs_json)
            else:
                print("[DEBUG] tariffs_tree not ready yet in _safe_load_tariffs_after_widget_ready")
        except Exception as e:
            print("[DEBUG] _safe_load_tariffs_after_widget_ready exception:", e)

    def clear_console_group_form(self):
        try:
            self.group_name_entry.delete(0, tk.END)
        except:
            pass
        try:
            self.group_icon_combo.set("")
        except:
            pass
        try:
            self.group_icon_custom_entry.delete(0, tk.END)
        except:
            pass
        if hasattr(self, 'selected_group_id'):
            del self.selected_group_id
        self.clear_tariffs_tree()

    def load_tariffs_for_group(self, tariffs_json):
        self.clear_tariffs_tree()
        try:
            tariffs = []
            if tariffs_json is None:
                tariffs = []
            elif isinstance(tariffs_json, list):
                tariffs = tariffs_json
            elif isinstance(tariffs_json, str):
                try:
                    tariffs = json.loads(tariffs_json)
                    if not isinstance(tariffs, list):
                        tariffs = []
                except Exception:
                    tariffs = []
            else:
                try:
                    tariffs = json.loads(json.dumps(tariffs_json))
                    if not isinstance(tariffs, list):
                        tariffs = []
                except Exception:
                    tariffs = []
            tariffs_sorted = sorted(tariffs, key=lambda x: x.get('montant', 0) if isinstance(x, dict) else 0)
            for tariff in tariffs_sorted:
                montant = tariff.get('montant', 0) if isinstance(tariff, dict) else 0
                minutes = tariff.get('minutes', 0) if isinstance(tariff, dict) else 0
                if hasattr(self, 'tariffs_tree') and self.tariffs_tree and self.tariffs_tree.winfo_exists():
                    self.tariffs_tree.insert("", tk.END, values=(montant, minutes))
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur chargement tarifs: {e}")
            print("[DEBUG] load_tariffs_for_group exception:", e)

    def add_tariff_entry(self):
        try:
            sel = self.console_groups_tree.selection()
        except Exception:
            sel = []
        if not sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un groupe de consoles d'abord.")
            return
        selected_item = sel[0]
        montant = simpledialog.askinteger("Ajouter Tarif", "Montant (FCFA):", parent=self.root)
        if montant is None:
            return
        minutes = simpledialog.askinteger("Ajouter Tarif", "Minutes correspondantes:", parent=self.root)
        if minutes is None:
            return
        if montant <= 0 or minutes <= 0:
            messagebox.showerror("Erreur", "Montant et minutes doivent être > 0.")
            return
        group_id = self.console_groups_tree.item(selected_item, 'values')[0]
        try:
            tags = self.console_groups_tree.item(selected_item, 'tags')
            tariffs_json = tags[0] if tags else json.dumps([])
        except Exception:
            tariffs_json = json.dumps([])
        try:
            tariffs = json.loads(tariffs_json) if tariffs_json else []
        except Exception:
            tariffs = []
        if any(isinstance(t, dict) and t.get('montant') == montant for t in tariffs):
            messagebox.showerror("Erreur", "Ce montant existe déjà dans la grille tarifaire.")
            return
        tariffs.append({"montant": montant, "minutes": minutes})
        tariffs.sort(key=lambda x: x['montant'])
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE console_groups SET tariffs = ? WHERE id = ?", (json.dumps(tariffs), group_id))
                conn.commit()
            self.console_groups_tree.item(selected_item, tags=(json.dumps(tariffs),))
            self.load_tariffs_for_group(json.dumps(tariffs))
            messagebox.showinfo("Succès", "Tarif ajouté.")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'ajouter le tarif: {e}")
            print("[DEBUG] add_tariff_entry exception:", e)

    def update_tariff_entry(self):
        try:
            group_sel = self.console_groups_tree.selection()
        except Exception:
            group_sel = []
        try:
            tariff_sel = self.tariffs_tree.selection()
        except Exception:
            tariff_sel = []
        if not group_sel or not tariff_sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un groupe ET un tarif à modifier.")
            return
        group_item = group_sel[0]
        tariff_item = tariff_sel[0]
        old_values = self.tariffs_tree.item(tariff_item, 'values')
        if not old_values:
            messagebox.showerror("Erreur", "Impossible de récupérer le tarif sélectionné.")
            return
        old_montant = old_values[0]
        try:
            new_montant = simpledialog.askinteger("Modifier Tarif", f"Nouveau Montant (FCFA) pour {old_montant} FCFA:", initialvalue=old_montant, parent=self.root)
            if new_montant is None:
                return
            new_minutes = simpledialog.askinteger("Modifier Tarif", f"Nouvelles Minutes pour {new_montant} FCFA:", initialvalue=old_values[1], parent=self.root)
            if new_minutes is None:
                return
        except Exception:
            messagebox.showerror("Erreur", "Entrée invalide.")
            return
        if new_montant <= 0 or new_minutes <= 0:
            messagebox.showerror("Erreur", "Montant et minutes doivent être > 0.")
            return
        group_id = self.console_groups_tree.item(group_item, 'values')[0]
        try:
            tags = self.console_groups_tree.item(group_item, 'tags')
            tariffs_json = tags[0] if tags else json.dumps([])
        except Exception:
            tariffs_json = json.dumps([])
        try:
            tariffs = json.loads(tariffs_json) if tariffs_json else []
        except Exception:
            tariffs = []
        tariffs = [t for t in tariffs if not (isinstance(t, dict) and t.get('montant') == old_montant)]
        if any(isinstance(t, dict) and t.get('montant') == new_montant for t in tariffs):
            messagebox.showerror("Erreur", "Le nouveau montant existe déjà dans la grille tarifaire.")
            return
        tariffs.append({"montant": new_montant, "minutes": new_minutes})
        tariffs.sort(key=lambda x: x['montant'])
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE console_groups SET tariffs = ? WHERE id = ?", (json.dumps(tariffs), group_id))
                conn.commit()
            self.console_groups_tree.item(group_item, tags=(json.dumps(tariffs),))
            self.load_tariffs_for_group(json.dumps(tariffs))
            messagebox.showinfo("Succès", "Tarif modifié.")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de modifier le tarif: {e}")
            print("[DEBUG] update_tariff_entry exception:", e)

    def delete_tariff_entry(self):
        try:
            group_sel = self.console_groups_tree.selection()
        except Exception:
            group_sel = []
        try:
            tariff_sel = self.tariffs_tree.selection()
        except Exception:
            tariff_sel = []
        if not group_sel or not tariff_sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un groupe ET un tarif à supprimer.")
            return
        group_item = group_sel[0]
        tariff_item = tariff_sel[0]
        montant_to_delete = self.tariffs_tree.item(tariff_item, 'values')[0]
        if messagebox.askyesno("Confirmer Suppression", f"Supprimer le tarif de {montant_to_delete} FCFA ?"):
            group_id = self.console_groups_tree.item(group_item, 'values')[0]
            try:
                tags = self.console_groups_tree.item(group_item, 'tags')
                tariffs_json = tags[0] if tags else json.dumps([])
            except Exception:
                tariffs_json = json.dumps([])
            try:
                tariffs = json.loads(tariffs_json) if tariffs_json else []
            except Exception:
                tariffs = []
            tariffs = [t for t in tariffs if not (isinstance(t, dict) and t.get('montant') == montant_to_delete)]
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE console_groups SET tariffs = ? WHERE id = ?", (json.dumps(tariffs), group_id))
                    conn.commit()
                self.console_groups_tree.item(group_item, tags=(json.dumps(tariffs),))
                self.load_tariffs_for_group(json.dumps(tariffs))
                messagebox.showinfo("Succès", "Tarif supprimé.")
            except Exception as e:
                messagebox.showerror("Erreur BD", f"Impossible de supprimer le tarif: {e}")
                print("[DEBUG] delete_tariff_entry exception:", e)

    def on_tariff_select(self, event):
        pass

    def clear_tariffs_tree(self):
        try:
            if self.tariffs_tree and self.tariffs_tree.winfo_exists():
                for item in self.tariffs_tree.get_children():
                    self.tariffs_tree.delete(item)
        except Exception as e:
            print("[DEBUG] clear_tariffs_tree exception:", e)

    def reorder_tariffs_current_group(self):
        try:
            sel = self.console_groups_tree.selection()
        except Exception:
            sel = []
        if not sel:
            messagebox.showerror("Erreur", "Sélectionnez un groupe d'abord.")
            return
        selected_item = sel[0]
        try:
            tags = self.console_groups_tree.item(selected_item, 'tags')
            tariffs_json = tags[0] if tags else json.dumps([])
        except Exception:
            tariffs_json = json.dumps([])
        try:
            tariffs = json.loads(tariffs_json) if tariffs_json else []
        except Exception:
            tariffs = []
        tariffs.sort(key=lambda x: x.get('montant', 0) if isinstance(x, dict) else 0)
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE console_groups SET tariffs = ? WHERE id = ?", (json.dumps(tariffs), self.console_groups_tree.item(selected_item, 'values')[0]))
                conn.commit()
            self.console_groups_tree.item(selected_item, tags=(json.dumps(tariffs),))
            self.load_tariffs_for_group(json.dumps(tariffs))
            messagebox.showinfo("Réordonné", "Tarifs réordonnés par montant.")
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de réordonner : {e}")
            print("[DEBUG] reorder_tariffs_current_group exception:", e)

    # ---------------- Physical postes ----------------
    def create_physical_postes_section(self, parent):
        frame = ttk.LabelFrame(parent, text="🖥️ Gestion des Postes Physiques", style="Light.TLabelFrame")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        poste_form_frame = ttk.Frame(frame, style="Light.TFrame")
        poste_form_frame.pack(fill=tk.X, pady=(0,10))

        # numéro
        ttk.Label(poste_form_frame, text="Numéro du Poste:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.poste_numero_entry = ttk.Entry(poste_form_frame, width=6)
        self.poste_numero_entry.pack(side=tk.LEFT, padx=(0,10))
        self.settings_entries['current_poste_numero'] = self.poste_numero_entry

        # nom
        ttk.Label(poste_form_frame, text="Nom du Poste:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.poste_nom_entry = ttk.Entry(poste_form_frame, width=18)
        self.poste_nom_entry.pack(side=tk.LEFT, padx=(0,10))
        self.settings_entries['current_poste_nom'] = self.poste_nom_entry

        # nombre de sorties
        ttk.Label(poste_form_frame, text="Nombre de sorties:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,5))
        self.poste_nb_sorties_var = tk.IntVar(value=1)
        self.poste_nb_sorties_combo = ttk.Combobox(poste_form_frame, textvariable=self.poste_nb_sorties_var, values=[1,2], width=3, state="readonly")
        self.poste_nb_sorties_combo.pack(side=tk.LEFT, padx=(0,10))
        self.poste_nb_sorties_combo.bind("<<ComboboxSelected>>", lambda e: self._render_poste_outputs_ui())

        # outputs container
        self.outputs_container = ttk.Frame(frame)
        self.outputs_container.pack(fill=tk.X, pady=(6,8))
        # we'll dynamically create output frames for each output (1 or 2)
        self.output_widgets = {}  # indexed by output_index (1 or 2)
        self._render_poste_outputs_ui()

        # --- Boutons d'action du formulaire ---
        action_buttons_row = ttk.Frame(frame)
        action_buttons_row.pack(fill=tk.X, pady=(4,8))
        self.add_poste_btn = ttk.Button(action_buttons_row, text="➕ Ajouter Poste", command=self.add_physical_poste, width=18)
        self.add_poste_btn.pack(side=tk.LEFT, padx=(4,6))
        self.edit_poste_btn = ttk.Button(action_buttons_row, text="💾 Modifier Poste", command=self.update_physical_poste, width=18)
        self.edit_poste_btn.pack(side=tk.LEFT, padx=(4,6))
        self.delete_poste_btn = ttk.Button(action_buttons_row, text="🗑️ Supprimer Poste", command=self.delete_physical_poste, width=18)
        self.delete_poste_btn.pack(side=tk.LEFT, padx=(4,6))

        # Désactiver delete / edit tant qu'aucune sélection n'est faite
        self.delete_poste_btn.state(['disabled'])
        self.edit_poste_btn.state(['disabled'])

        ttk.Label(poste_form_frame, text="(sélectionnez groupes pour les sorties via les combos)", style="Light.TLabel").pack(side=tk.LEFT, padx=(10,0))

        # treeview for physical postes
        tree_container = ttk.Frame(frame)
        tree_container.pack(fill=tk.BOTH, expand=True, pady=(6,0))
        self.physical_postes_tree = ttk.Treeview(tree_container, columns=("ID","Numéro","Nom","Sorties"), show="headings", selectmode="browse")
        self.physical_postes_tree.heading("ID", text="ID", anchor=tk.W)
        self.physical_postes_tree.heading("Numéro", text="Numéro", anchor=tk.W)
        self.physical_postes_tree.heading("Nom", text="Nom", anchor=tk.W)
        self.physical_postes_tree.heading("Sorties", text="Sorties (détails)", anchor=tk.W)
        self.physical_postes_tree.column("ID", width=40, stretch=tk.NO)
        self.physical_postes_tree.column("Numéro", width=60, stretch=tk.NO)
        self.physical_postes_tree.column("Nom", width=150, stretch=tk.YES)
        self.physical_postes_tree.column("Sorties", width=350, stretch=tk.YES)
        self.physical_postes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.physical_postes_tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.physical_postes_tree.config(yscrollcommand=tree_scroll.set)

        # bind selection event to enable buttons
        self.physical_postes_tree.bind("<<TreeviewSelect>>", self._on_physical_tree_select_enable_buttons)
        # bind Delete key for convenience
        self.physical_postes_tree.bind("<Delete>", lambda e: self.delete_physical_poste())

        self.load_console_group_names_for_combo()
        self.load_physical_postes()

    def _render_poste_outputs_ui(self):
        for w in self.outputs_container.winfo_children():
            w.destroy()
        self.output_widgets = {}
        nb = int(self.poste_nb_sorties_var.get() if getattr(self, 'poste_nb_sorties_var', None) else 1)
        for idx in range(1, nb+1):
            sub = ttk.Frame(self.outputs_container)
            sub.pack(fill=tk.X, pady=(4,4))
            ttk.Label(sub, text=f"Sortie {idx} - Type:", style="Light.TLabel").pack(side=tk.LEFT, padx=(0,6))
            type_var = tk.StringVar(value="HDMI")
            type_combo = ttk.Combobox(sub, textvariable=type_var, values=["HDMI", "AV"], width=6, state="readonly")
            type_combo.pack(side=tk.LEFT, padx=(0,6))
            ttk.Label(sub, text="Port Switch:", style="Light.TLabel").pack(side=tk.LEFT, padx=(6,6))
            port_var = tk.StringVar()
            port_combo = ttk.Combobox(sub, textvariable=port_var, values=self.serial_ports, width=8)
            port_combo.pack(side=tk.LEFT, padx=(0,6))
            ttk.Label(sub, text="Groupe Console:", style="Light.TLabel").pack(side=tk.LEFT, padx=(6,6))
            group_var = tk.StringVar()
            group_combo = ttk.Combobox(sub, textvariable=group_var, values=[], width=14, state="readonly")
            group_combo.pack(side=tk.LEFT, padx=(0,6))
            self.output_widgets[idx] = {
                "type_var": type_var,
                "type_combo": type_combo,
                "port_var": port_var,
                "port_combo": port_combo,
                "group_var": group_var,
                "group_combo": group_combo
            }
        self.load_console_group_names_for_combo()
        self._refresh_serialport_combobox()
        for idx, w in self.output_widgets.items():
            try:
                w['port_combo']['values'] = self.serial_ports
            except Exception:
                pass

    def load_physical_postes(self, select_id=None):
        try:
            for item in self.physical_postes_tree.get_children():
                self.physical_postes_tree.delete(item)
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS physical_postes (id INTEGER PRIMARY KEY AUTOINCREMENT, numero INTEGER UNIQUE NOT NULL, nom TEXT NOT NULL, console_group_ids TEXT, switch_port INTEGER, outputs TEXT)")
                cursor.execute("SELECT id, numero, nom, outputs FROM physical_postes ORDER BY numero")
                rows = cursor.fetchall()
                for row in rows:
                    pid, numero, nom, outputs_raw = row
                    try:
                        outputs = json.loads(outputs_raw) if outputs_raw else []
                    except Exception:
                        outputs = []
                    out_strings = []
                    for o in outputs:
                        typ = o.get('type', '?')
                        sw = o.get('switch_port', '?')
                        gid = o.get('group_id', None)
                        gname = ''
                        if gid:
                            try:
                                cursor.execute("SELECT name FROM console_groups WHERE id = ?", (gid,))
                                r = cursor.fetchone()
                                gname = r[0] if r else ''
                            except Exception:
                                gname = ''
                        out_strings.append(f"[{typ} port:{sw} groupe:{gname}]")
                    if not out_strings:
                        out_strings = ["(aucune sortie configurée)"]
                    self.physical_postes_tree.insert("", tk.END, values=(pid, numero, nom, " ".join(out_strings)), tags=(outputs_raw if outputs_raw else json.dumps([]),))
            if select_id:
                for iid in self.physical_postes_tree.get_children():
                    vals = self.physical_postes_tree.item(iid, 'values')
                    if vals and str(vals[0]) == str(select_id):
                        self.physical_postes_tree.selection_set(iid)
                        self.physical_postes_tree.focus(iid)
                        try:
                            self.physical_postes_tree.see(iid)
                        except Exception:
                            pass
                        break
            # ensure delete/edit button disabled if nothing selected
            cur_sel = self.physical_postes_tree.selection()
            if not cur_sel:
                try:
                    self.delete_poste_btn.state(['disabled'])
                    self.edit_poste_btn.state(['disabled'])
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de charger les postes physiques: {e}")
            print("[DEBUG] load_physical_postes exception:", e)

    def _get_console_group_names_from_ids(self, group_ids):
        names = []
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                for gid in group_ids:
                    cursor.execute("SELECT name FROM console_groups WHERE id = ?", (gid,))
                    result = cursor.fetchone()
                    if result:
                        names.append(result[0])
        except Exception as e:
            print(f"Erreur récupération noms de groupes: {e}")
        return names

    def load_console_group_names_for_combo(self):
        group_names = []
        id_map = {}
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM console_groups ORDER BY name")
                pairs = cursor.fetchall()
                group_names = [r[1] for r in pairs]
                id_map = {r[1]: r[0] for r in pairs}
                self._console_group_id_name_pairs = id_map
        except Exception as e:
            print(f"Erreur chargement noms de groupes pour combobox: {e}")
            self._console_group_id_name_pairs = {}
            group_names = []
        try:
            for idx, w in self.output_widgets.items():
                try:
                    w['group_combo']['values'] = group_names
                except Exception:
                    pass
        except Exception:
            pass

    def add_physical_poste(self):
        numero_txt = self.poste_numero_entry.get().strip()
        nom = self.poste_nom_entry.get().strip()
        try:
            nb_sorties = int(self.poste_nb_sorties_var.get())
        except Exception:
            nb_sorties = 1
        outputs = []
        for idx in range(1, nb_sorties+1):
            w = self.output_widgets.get(idx)
            if not w:
                continue
            try:
                typ = w['type_var'].get()
                port = w['port_var'].get().strip()
                group_name = w['group_var'].get().strip()
            except Exception:
                typ, port, group_name = "HDMI", "", ""
            if not port or not group_name:
                messagebox.showerror("Erreur", f"Pour la sortie {idx}, indiquez le port switch ET le groupe.")
                return
            gid = self._console_group_id_name_pairs.get(group_name)
            if not gid:
                messagebox.showerror("Erreur", f"Groupe '{group_name}' introuvable.")
                return
            try:
                switch_port_num = int(port) if str(port).isdigit() else port
            except Exception:
                switch_port_num = port
            outputs.append({
                "output_index": idx,
                "type": typ,
                "switch_port": switch_port_num,
                "group_id": gid
            })
        if not numero_txt or not nom:
            messagebox.showerror("Erreur", "Numéro et nom du poste sont requis.")
            return
        try:
            numero = int(numero_txt)
        except ValueError:
            messagebox.showerror("Erreur", "Numéro du poste doit être un entier.")
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM physical_postes WHERE numero = ?", (numero,))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", f"Le poste numéro {numero} existe déjà.")
                    return
                cursor.execute("INSERT INTO physical_postes (numero, nom, console_group_ids, switch_port, outputs) VALUES (?, ?, ?, ?, ?)",
                               (numero, nom, json.dumps([]), None, json.dumps(outputs)))
                conn.commit()
                last_id = cursor.lastrowid
                messagebox.showinfo("Succès", f"Poste '{nom}' ajouté.")
                self.clear_physical_poste_form()
                self.load_physical_postes(select_id=last_id)
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'ajouter le poste: {e}")
            print("[DEBUG] add_physical_poste exception:", e)

    def update_physical_poste(self):
        sel = self.physical_postes_tree.selection()
        if not sel:
            messagebox.showerror("Erreur", "Veuillez sélectionner un poste à modifier.")
            return
        selected_item = sel[0]
        poste_id = self.physical_postes_tree.item(selected_item, 'values')[0]
        numero_txt = self.poste_numero_entry.get().strip()
        nom = self.poste_nom_entry.get().strip()
        try:
            nb_sorties = int(self.poste_nb_sorties_var.get())
        except Exception:
            nb_sorties = 1
        outputs = []
        for idx in range(1, nb_sorties+1):
            w = self.output_widgets.get(idx)
            if not w:
                continue
            try:
                typ = w['type_var'].get()
                port = w['port_var'].get().strip()
                group_name = w['group_var'].get().strip()
            except Exception:
                typ, port, group_name = "HDMI", "", ""
            if not port or not group_name:
                messagebox.showerror("Erreur", f"Pour la sortie {idx}, indiquez le port switch ET le groupe.")
                return
            gid = self._console_group_id_name_pairs.get(group_name)
            if not gid:
                messagebox.showerror("Erreur", f"Groupe '{group_name}' introuvable.")
                return
            try:
                switch_port_num = int(port) if str(port).isdigit() else port
            except Exception:
                switch_port_num = port
            outputs.append({
                "output_index": idx,
                "type": typ,
                "switch_port": switch_port_num,
                "group_id": gid
            })
        if not numero_txt or not nom:
            messagebox.showerror("Erreur", "Numéro et nom du poste sont requis.")
            return
        try:
            numero = int(numero_txt)
        except ValueError:
            messagebox.showerror("Erreur", "Numéro du poste doit être un entier.")
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM physical_postes WHERE numero = ? AND id != ?", (numero, poste_id))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", f"Le poste numéro {numero} existe déjà pour un autre ID.")
                    return
                cursor.execute("UPDATE physical_postes SET numero = ?, nom = ?, outputs = ? WHERE id = ?", (numero, nom, json.dumps(outputs), poste_id))
                conn.commit()
                messagebox.showinfo("Succès", f"Poste '{nom}' modifié.")
                self.clear_physical_poste_form()
                self.load_physical_postes(select_id=poste_id)
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de modifier le poste: {e}")
            print("[DEBUG] update_physical_poste exception:", e)

    def delete_physical_poste(self):
        """
        - vérifie la sélection
        - convertit proprement l'ID
        - exécute DELETE et teste cursor.rowcount
        - rafraîchit la vue et nettoie le formulaire
        """
        try:
            sel = self.physical_postes_tree.selection()
        except Exception:
            sel = []
        if not sel:
            # try fallback to focus
            focused = self.physical_postes_tree.focus()
            if not focused:
                messagebox.showerror("Erreur", "Veuillez sélectionner un poste à supprimer.")
                return
            sel = (focused,)

        selected_item = sel[0]
        try:
            vals = self.physical_postes_tree.item(selected_item, 'values')
            if not vals:
                messagebox.showerror("Erreur", "Impossible de récupérer les informations du poste sélectionné.")
                return
            poste_id_raw = vals[0]
        except Exception:
            messagebox.showerror("Erreur", "Impossible de récupérer l'ID du poste sélectionné.")
            return

        # try to coerce to int when possible
        try:
            poste_id = int(poste_id_raw)
        except Exception:
            try:
                poste_id = int(str(poste_id_raw))
            except Exception:
                poste_id = poste_id_raw  # keep as-is (string) as last resort

        poste_nom = ""
        try:
            poste_nom = self.physical_postes_tree.item(selected_item, 'values')[2]
        except Exception:
            poste_nom = str(poste_id)

        if not messagebox.askyesno("Confirmer Suppression", f"Êtes-vous sûr de vouloir supprimer le poste '{poste_nom}' ?"):
            return

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM physical_postes WHERE id = ?", (poste_id,))
                conn.commit()
                if cursor.rowcount == 0:
                    # nothing deleted => maybe id type mismatch, try string id
                    try:
                        cursor.execute("DELETE FROM physical_postes WHERE CAST(id AS TEXT) = ?", (str(poste_id),))
                        conn.commit()
                    except Exception:
                        pass
                messagebox.showinfo("Succès", f"Poste '{poste_nom}' supprimé.")
                # refresh
                self.clear_physical_poste_form()
                self.load_physical_postes()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de supprimer le poste: {e}")
            print("[DEBUG] delete_physical_poste exception:", e)

    def _on_physical_tree_select_enable_buttons(self, event):
        """
        Lorsqu'on sélectionne une ligne dans la Treeview des postes physiques,
        on active les boutons Modifier / Supprimer pour que l'utilisateur voie
        qu'ils sont disponibles.
        """
        sel = self.physical_postes_tree.selection()
        if sel:
            try:
                self.delete_poste_btn.state(['!disabled'])
                self.edit_poste_btn.state(['!disabled'])
            except Exception:
                pass
            # remplir le formulaire avec les données de la sélection
            self.on_physical_poste_select(event)
        else:
            try:
                self.delete_poste_btn.state(['disabled'])
                self.edit_poste_btn.state(['disabled'])
            except Exception:
                pass

    def on_physical_poste_select(self, event):
        sel = self.physical_postes_tree.selection()
        if sel:
            selected_item = sel[0]
            vals = self.physical_postes_tree.item(selected_item, 'values')
            pid = vals[0]
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT numero, nom, outputs FROM physical_postes WHERE id = ?", (pid,))
                    row = cursor.fetchone()
                    if row:
                        numero, nom, outputs_raw = row
                        self.poste_numero_entry.delete(0, tk.END); self.poste_numero_entry.insert(0, str(numero))
                        self.poste_nom_entry.delete(0, tk.END); self.poste_nom_entry.insert(0, nom)
                        outputs = []
                        try:
                            outputs = json.loads(outputs_raw) if outputs_raw else []
                        except Exception:
                            outputs = []
                        nb = max(1, len(outputs))
                        if nb > 2: nb = 2
                        try:
                            self.poste_nb_sorties_var.set(nb)
                            self.poste_nb_sorties_combo.set(nb)
                        except Exception:
                            pass
                        self._render_poste_outputs_ui()
                        for o in outputs:
                            idx = int(o.get('output_index', 1))
                            if idx in self.output_widgets:
                                w = self.output_widgets[idx]
                                try:
                                    w['type_var'].set(o.get('type', 'HDMI'))
                                except Exception:
                                    pass
                                try:
                                    w['port_var'].set(str(o.get('switch_port', '')))
                                except Exception:
                                    pass
                                try:
                                    gid = o.get('group_id', None)
                                    if gid:
                                        cursor.execute("SELECT name FROM console_groups WHERE id = ?", (gid,))
                                        r = cursor.fetchone()
                                        if r:
                                            w['group_var'].set(r[0])
                                except Exception:
                                    pass
            except Exception as e:
                messagebox.showerror("Erreur BD", f"Impossible de récupérer les détails du poste: {e}")
                print("[DEBUG] on_physical_poste_select exception:", e)

    # ---------------- User management functions ----------------
    def add_user(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        role = self.role_var.get().strip() or "manager"
        if not username:
            messagebox.showerror("Erreur", "Le nom d'utilisateur est requis.")
            return
        if not password:
            messagebox.showerror("Erreur", "Le mot de passe est requis.")
            return
        try:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        except Exception:
            # fallback si bcrypt indisponible pour une raison
            hashed = password
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)")
                cursor.execute("SELECT COUNT(*) FROM users WHERE LOWER(username) = ?", (username.lower(),))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", "Ce nom d'utilisateur existe déjà.")
                    return
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed, role))
                conn.commit()
            messagebox.showinfo("Succès", f"Utilisateur '{username}' créé.")
            self.clear_user_form()
            self.load_users()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible d'ajouter l'utilisateur: {e}")
            print("[DEBUG] add_user exception:", e)

    def update_user(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showerror("Erreur", "Sélectionnez un utilisateur à modifier.")
            return
        user_item = sel[0]
        vals = self.users_tree.item(user_item, 'values')
        if not vals:
            messagebox.showerror("Erreur", "Impossible de récupérer l'utilisateur sélectionné.")
            return
        user_id = vals[0]
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        role = self.role_var.get().strip() or "manager"
        if not username:
            messagebox.showerror("Erreur", "Le nom d'utilisateur est requis.")
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # check unique username
                cursor.execute("SELECT id FROM users WHERE LOWER(username) = ?", (username.lower(),))
                row = cursor.fetchone()
                if row and str(row[0]) != str(user_id):
                    messagebox.showerror("Erreur", "Ce nom d'utilisateur est déjà utilisé par un autre compte.")
                    return
                if password:
                    try:
                        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    except Exception:
                        hashed = password
                    cursor.execute("UPDATE users SET username = ?, password = ?, role = ? WHERE id = ?", (username, hashed, role, user_id))
                else:
                    cursor.execute("UPDATE users SET username = ?, role = ? WHERE id = ?", (username, role, user_id))
                conn.commit()
            messagebox.showinfo("Succès", "Utilisateur modifié.")
            self.clear_user_form()
            self.load_users()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de modifier l'utilisateur: {e}")
            print("[DEBUG] update_user exception:", e)

    def delete_user(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showerror("Erreur", "Sélectionnez un utilisateur à supprimer.")
            return
        user_item = sel[0]
        vals = self.users_tree.item(user_item, 'values')
        if not vals:
            messagebox.showerror("Erreur", "Impossible de récupérer l'utilisateur sélectionné.")
            return
        user_id = vals[0]
        username = vals[1] if len(vals) > 1 else str(user_id)
        if not messagebox.askyesno("Confirmer", f"Supprimer l'utilisateur '{username}' ?"):
            return
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
            messagebox.showinfo("Succès", f"Utilisateur '{username}' supprimé.")
            self.clear_user_form()
            self.load_users()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de supprimer l'utilisateur: {e}")
            print("[DEBUG] delete_user exception:", e)

    def load_users(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)")
                cursor.execute("SELECT id, username, role FROM users ORDER BY username")
                rows = cursor.fetchall()
            # clear tree
            if self.users_tree and self.users_tree.winfo_exists():
                for i in self.users_tree.get_children():
                    self.users_tree.delete(i)
                for r in rows:
                    self.users_tree.insert("", tk.END, values=(r[0], r[1], r[2]))
        except Exception as e:
            print("[DEBUG] load_users exception:", e)

    def clear_user_form(self):
        try:
            self.username_entry.delete(0, tk.END)
        except Exception:
            pass
        try:
            self.password_entry.delete(0, tk.END)
        except Exception:
            pass
        try:
            self.role_combo.set("manager")
        except Exception:
            pass
        try:
            # unselect tree selection
            self.users_tree.selection_remove(self.users_tree.selection())
        except Exception:
            pass

    def on_user_select(self, event):
        sel = self.users_tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.users_tree.item(item, 'values')
        if vals:
            try:
                self.username_entry.delete(0, tk.END)
                self.username_entry.insert(0, vals[1])
                self.role_combo.set(vals[2])
                # do not prefill password for security
                self.password_entry.delete(0, tk.END)
            except Exception:
                pass

    # ---------------- Settings load/save helpers ----------------
    def _load_lists_from_config(self):
        try:
            currencies = self._get_config_json("currencies", [])
            serials = self._get_config_json("serial_ports", [])
            if isinstance(currencies, list):
                self.currencies = currencies
            else:
                self.currencies = ["FCFA"]
            if isinstance(serials, list):
                self.serial_ports = serials
            else:
                self.serial_ports = []
        except Exception as e:
            print("[DEBUG] _load_lists_from_config exception:", e)
            self.currencies = ["FCFA"]
            self.serial_ports = []

    def load_settings_for_current_section(self):
        """
        Remplit les widgets de configuration visibles avec les valeurs stockées en base.
        Cette fonction est appelée chaque fois qu'une section/sous-section est affichée.
        """
        try:
            # generic: currency
            if getattr(self, "devise_var", None):
                cfg_devise = self._get_config("devise", None)
                if cfg_devise:
                    try:
                        self.devise_var.set(cfg_devise)
                    except Exception:
                        pass
                else:
                    if self.currencies:
                        try:
                            self.devise_var.set(self.currencies[0])
                            self._set_config("devise", self.currencies[0])
                        except Exception:
                            pass
            # serial port active
            if getattr(self, "serial_port_var", None):
                cfg_sp = self._get_config("serial_port_active", None)
                if cfg_sp:
                    try:
                        self.serial_port_var.set(cfg_sp)
                    except Exception:
                        pass
            # baud rate
            if getattr(self, "baud_rate_var", None):
                cfg_baud = self._get_config("baud_rate", None)
                if cfg_baud:
                    try:
                        self.baud_rate_var.set(cfg_baud)
                    except Exception:
                        pass
            # standard tariff
            if getattr(self, "standard_tariff_entry", None):
                cfg_std = self._get_config("standard_tariff_fcfa_per_6min", None)
                if cfg_std is not None:
                    try:
                        self.standard_tariff_entry.delete(0, tk.END)
                        self.standard_tariff_entry.insert(0, str(cfg_std))
                    except Exception:
                        pass
            # Bonus Simples widgets
            # bonus_enabled
            try:
                if getattr(self, "bonus_enabled_var", None) is not None:
                    be = self._get_config("bonus_enabled", "1")
                    try:
                        self.bonus_enabled_var.set(1 if str(be) != "0" else 0)
                    except Exception:
                        self.bonus_enabled_var.set(1)
            except Exception:
                pass
            # bonus_fcfa_per_minute
            try:
                if getattr(self, "bonus_fcfa_entry", None) is not None:
                    val = self._get_config("bonus_fcfa_per_minute", "50")
                    self.bonus_fcfa_entry.delete(0, tk.END)
                    self.bonus_fcfa_entry.insert(0, str(val))
            except Exception:
                pass
            # bonus_rounding
            try:
                if getattr(self, "bonus_rounding_combo", None) is not None:
                    val = self._get_config("bonus_rounding", "floor")
                    if val is None:
                        val = "floor"
                    self.bonus_rounding_combo.set(val)
            except Exception:
                pass
            # bonus_apply_on (json list)
            try:
                if getattr(self, "bonus_apply_achats_var", None) is not None:
                    apply_on = self._get_config_json("bonus_apply_on", ["achats", "prolongations", "recharges"])
                    self.bonus_apply_achats_var.set("achats" in apply_on)
                    self.bonus_apply_prolong_var.set("prolongations" in apply_on)
                    self.bonus_apply_recharge_var.set("recharges" in apply_on)
            except Exception:
                pass
            # welcome bonus
            try:
                if getattr(self, "welcome_enabled_var", None) is not None:
                    wbe = self._get_config("welcome_bonus_enabled", "1")
                    self.welcome_enabled_var.set(1 if str(wbe) != "0" else 0)
                if getattr(self, "welcome_minutes_entry", None) is not None:
                    wm = self._get_config("welcome_bonus_minutes", "15")
                    self.welcome_minutes_entry.delete(0, tk.END)
                    self.welcome_minutes_entry.insert(0, str(wm))
            except Exception:
                pass

            # ensure combobox lists up-to-date
            self._refresh_currency_combobox()
            self._refresh_serialport_combobox()
        except Exception as e:
            print("[DEBUG] load_settings_for_current_section exception:", e)

    # ---------------- Bonus Simples section ----------------
    def create_bonus_simples_section(self, parent):
        """
        UI pour la gestion des "Bonus Simples" (bonus de jeux & bonus de bienvenue).
        Ne modifie rien hors de cette section.
        """
        frame = ttk.Frame(parent, style="Light.TFrame")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Header
        header = ttk.Label(frame, text="🎁 Bonus Simples - Paramètres", style="SectionTitle.TLabel")
        header.pack(anchor=tk.W, pady=(0,6))

        # --- Block: Bonus de jeux ---
        games_frame = ttk.LabelFrame(frame, text="Bonus de jeux (automatique)", style="Light.TLabelFrame")
        games_frame.pack(fill=tk.X, pady=(6,10))

        # enabled
        self.bonus_enabled_var = tk.IntVar(value=1)
        enabled_cb = ttk.Checkbutton(games_frame, text="Activer Bonus de jeux (1 min pour X FCFA)", variable=self.bonus_enabled_var)
        enabled_cb.pack(anchor=tk.W, padx=8, pady=(6,2))

        # ratio
        ratio_frame = ttk.Frame(games_frame)
        ratio_frame.pack(fill=tk.X, padx=8, pady=(4,4))
        ttk.Label(ratio_frame, text="Valeur (FCFA par minute):", style="Light.TLabel").pack(side=tk.LEFT)
        self.bonus_fcfa_entry = ttk.Entry(ratio_frame, width=10)
        self.bonus_fcfa_entry.pack(side=tk.LEFT, padx=(6,8))
        ttk.Label(ratio_frame, text="(ex: 50 -> 1 minute pour 50 FCFA)", style="Light.TLabel").pack(side=tk.LEFT)

        # rounding
        rnd_frame = ttk.Frame(games_frame)
        rnd_frame.pack(fill=tk.X, padx=8, pady=(4,4))
        ttk.Label(rnd_frame, text="Arrondi:", style="Light.TLabel").pack(side=tk.LEFT)
        self.bonus_rounding_combo = ttk.Combobox(rnd_frame, values=["floor", "ceil", "none"], width=10, state="readonly")
        self.bonus_rounding_combo.pack(side=tk.LEFT, padx=(6,8))
        ttk.Label(rnd_frame, text="(floor: arrondir à l'inférieur)", style="Light.TLabel").pack(side=tk.LEFT)

        # apply on
        apply_frame = ttk.Frame(games_frame)
        apply_frame.pack(fill=tk.X, padx=8, pady=(4,6))
        ttk.Label(apply_frame, text="S'applique sur:", style="Light.TLabel").pack(side=tk.LEFT)
        self.bonus_apply_achats_var = tk.BooleanVar(value=True)
        self.bonus_apply_prolong_var = tk.BooleanVar(value=True)
        self.bonus_apply_recharge_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(apply_frame, text="Achats", variable=self.bonus_apply_achats_var).pack(side=tk.LEFT, padx=(8,4))
        ttk.Checkbutton(apply_frame, text="Prolongations", variable=self.bonus_apply_prolong_var).pack(side=tk.LEFT, padx=(6,4))
        ttk.Checkbutton(apply_frame, text="Recharges", variable=self.bonus_apply_recharge_var).pack(side=tk.LEFT, padx=(6,4))

        # example calc
        example_frame = ttk.Frame(games_frame)
        example_frame.pack(fill=tk.X, padx=8, pady=(8,8))
        ttk.Label(example_frame, text="Montant exemple (FCFA):", style="Light.TLabel").pack(side=tk.LEFT)
        self.bonus_example_amount = ttk.Entry(example_frame, width=12)
        self.bonus_example_amount.pack(side=tk.LEFT, padx=(6,6))
        ttk.Button(example_frame, text="Calculer exemple", command=self._calculate_example_bonus).pack(side=tk.LEFT, padx=(6,6))
        self.bonus_example_result_label = ttk.Label(example_frame, text="", style="Light.TLabel")
        self.bonus_example_result_label.pack(side=tk.LEFT, padx=(8,0))

        # history button
        hist_btn_frame = ttk.Frame(games_frame)
        hist_btn_frame.pack(fill=tk.X, padx=8, pady=(2,6))
        ttk.Button(hist_btn_frame, text="Voir historique global (Bonus)", command=self._open_bonus_history_view).pack(side=tk.LEFT)
        ttk.Button(hist_btn_frame, text="Exporter (CSV)", command=lambda: messagebox.showinfo("Exporter", "Fonction Export à implémenter si besoin.")).pack(side=tk.LEFT, padx=(6,0))

        # --- Block: Bonus de bienvenue ---
        welcome_frame = ttk.LabelFrame(frame, text="Bonus de bienvenue", style="Light.TLabelFrame")
        welcome_frame.pack(fill=tk.X, pady=(6,10))
        self.welcome_enabled_var = tk.IntVar(value=1)
        ttk.Checkbutton(welcome_frame, text="Activer bonus de bienvenue (à la 1ère inscription)", variable=self.welcome_enabled_var).pack(anchor=tk.W, padx=8, pady=(6,2))
        wm_frame = ttk.Frame(welcome_frame)
        wm_frame.pack(fill=tk.X, padx=8, pady=(4,6))
        ttk.Label(wm_frame, text="Minutes offertes:", style="Light.TLabel").pack(side=tk.LEFT)
        self.welcome_minutes_entry = ttk.Entry(wm_frame, width=8)
        self.welcome_minutes_entry.pack(side=tk.LEFT, padx=(6,8))
        ttk.Label(wm_frame, text="(ex: 15)", style="Light.TLabel").pack(side=tk.LEFT)

        welcome_btn_frame = ttk.Frame(welcome_frame)
        welcome_btn_frame.pack(fill=tk.X, padx=8, pady=(6,6))
        ttk.Button(welcome_btn_frame, text="Sauvegarder paramètres Bonus", command=self._save_bonus_simples_settings).pack(side=tk.LEFT)
        ttk.Button(welcome_btn_frame, text="Appliquer manuellement à un utilisateur", command=self._apply_welcome_to_user).pack(side=tk.LEFT, padx=(8,6))

        # info / disclaimer
        ttk.Label(frame, text="Les minutes bonus sont cumulables et (par défaut) n'expirent pas. Les crédits/débits manuels sont enregistrés dans l'historique.", style="Light.TLabel").pack(anchor=tk.W, pady=(6,4), padx=6)

        # load values from config into widgets
        self.load_settings_for_current_section()

    def _calculate_example_bonus(self):
        amt_txt = self.bonus_example_amount.get().strip() if getattr(self, "bonus_example_amount", None) else ""
        try:
            amt = int(amt_txt)
            if amt <= 0:
                raise ValueError()
        except Exception:
            messagebox.showerror("Erreur", "Entrez un montant FCFA valide (entier > 0) pour l'exemple.")
            return
        # try to use bonus_manager compute (if available)
        try:
            if self.bonus_manager:
                minutes = self.bonus_manager.compute_bonus_from_amount(amt)
            else:
                # fallback: compute using local config values
                fcfa_per_min = int(self._get_config("bonus_fcfa_per_minute", "50") or 50)
                rounding = self._get_config("bonus_rounding", "floor") or "floor"
                raw = amt / fcfa_per_min if fcfa_per_min > 0 else 0
                if rounding == "ceil":
                    minutes = int(math.ceil(raw))
                elif rounding == "none":
                    minutes = int(raw)
                else:
                    minutes = int(math.floor(raw))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de calculer l'exemple : {e}")
            return
        self.bonus_example_result_label.config(text=f"=> {minutes} minute(s)")

    def _open_bonus_history_view(self):
        if not self.bonus_manager:
            messagebox.showinfo("Historique", "Le gestionnaire de bonus n'est pas disponible (fichier app/bonus_simple.py manquant).")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Historique des bonus (global)")
        dlg.geometry("800x500")
        frm = ttk.Frame(dlg, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        # search / filter
        search_frame = ttk.Frame(frm)
        search_frame.pack(fill=tk.X, pady=(0,6))
        ttk.Label(search_frame, text="Utilisateur (ID) (optionnel):", style="Light.TLabel").pack(side=tk.LEFT)
        user_id_entry = ttk.Entry(search_frame, width=10)
        user_id_entry.pack(side=tk.LEFT, padx=(6,6))
        ttk.Label(search_frame, text="Limite:", style="Light.TLabel").pack(side=tk.LEFT, padx=(8,6))
        limit_var = tk.IntVar(value=200)
        limit_entry = ttk.Entry(search_frame, textvariable=limit_var, width=6)
        limit_entry.pack(side=tk.LEFT)
        def do_load_history():
            try:
                uid_txt = user_id_entry.get().strip()
                uid = int(uid_txt) if uid_txt else None
                limit = int(limit_entry.get())
            except Exception:
                messagebox.showerror("Erreur", "Paramètres invalides.")
                return
            try:
                rows = self.bonus_manager.list_bonus_history(user_id=uid, limit=limit, offset=0)
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de récupérer l'historique : {e}")
                return
            text.delete("1.0", tk.END)
            if not rows:
                text.insert(tk.END, "Aucune transaction trouvée.\n")
                return
            for r in rows:
                text.insert(tk.END, f"{r['created_at']} | user:{r['user_id']} | delta:{r['minutes_delta']} | source:{r['source']} | balance_after:{r.get('balance_after')} | ref:{r.get('reference')} | notes:{r.get('notes')}\n")
        ttk.Button(search_frame, text="Charger", command=do_load_history).pack(side=tk.LEFT, padx=(8,0))
        # text
        text = tk.Text(frm, wrap=tk.NONE)
        text.pack(fill=tk.BOTH, expand=True)
        vs = ttk.Scrollbar(frm, orient="vertical", command=text.yview)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        text.config(yscrollcommand=vs.set)

    def _save_bonus_simples_settings(self):
        try:
            # Bonus enabled
            be = 1 if getattr(self, "bonus_enabled_var", None) and self.bonus_enabled_var.get() else 0
            self._set_config("bonus_enabled", str(be))
            # fcfa per min
            if getattr(self, "bonus_fcfa_entry", None):
                val = self.bonus_fcfa_entry.get().strip()
                try:
                    ival = int(val)
                    self._set_config("bonus_fcfa_per_minute", str(ival))
                except Exception:
                    messagebox.showerror("Erreur", "Valeur FCFA par minute invalide (doit être un entier).")
                    return
            # rounding
            if getattr(self, "bonus_rounding_combo", None):
                r = self.bonus_rounding_combo.get().strip() or "floor"
                if r not in ("floor", "ceil", "none"):
                    r = "floor"
                self._set_config("bonus_rounding", r)
            # apply_on
            apply_on = []
            if getattr(self, "bonus_apply_achats_var", None) and self.bonus_apply_achats_var.get():
                apply_on.append("achats")
            if getattr(self, "bonus_apply_prolong_var", None) and self.bonus_apply_prolong_var.get():
                apply_on.append("prolongations")
            if getattr(self, "bonus_apply_recharge_var", None) and self.bonus_apply_recharge_var.get():
                apply_on.append("recharges")
            self._set_config_json("bonus_apply_on", apply_on)
            # welcome bonus
            we = 1 if getattr(self, "welcome_enabled_var", None) and self.welcome_enabled_var.get() else 0
            self._set_config("welcome_bonus_enabled", str(we))
            if getattr(self, "welcome_minutes_entry", None):
                try:
                    wm = int(self.welcome_minutes_entry.get().strip())
                    self._set_config("welcome_bonus_minutes", str(wm))
                except Exception:
                    messagebox.showerror("Erreur", "Minutes de bienvenue invalides (entier).")
                    return

            messagebox.showinfo("Succès", "Paramètres Bonus Simples sauvegardés.")
            # reload into manager if possible
            try:
                if self.bonus_manager:
                    # si nécessaire, on peut demander au manager d'actualiser quoique ce soit;
                    pass
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de sauvegarder les paramètres : {e}")
            print("[DEBUG] _save_bonus_simples_settings exception:", e)

    def _apply_welcome_to_user(self):
        if not self.bonus_manager:
            messagebox.showerror("Erreur", "Gestionnaire de bonus indisponible (app/bonus_simple.py manquant).")
            return
        try:
            user_id = simpledialog.askinteger("Appliquer welcome", "ID utilisateur :", parent=self.root)
            if not user_id:
                return
            minutes_added = self.bonus_manager.apply_welcome_bonus_on_registration(user_id, operator_id=self.user_id)
            if minutes_added > 0:
                messagebox.showinfo("Succès", f"{minutes_added} minutes de bienvenue ajoutées à l'utilisateur {user_id}.")
            else:
                messagebox.showinfo("Info", "Aucun bonus appliqué (déjà attribué ou désactivé).")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'appliquer le bonus : {e}")
            print("[DEBUG] _apply_welcome_to_user exception:", e)

    # ---------------- autres fonctions (utilisateurs, settings, save, logout, etc.) ----------------
    def save_general_settings(self):
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                def save_param(key, value):
                    cursor.execute("INSERT OR REPLACE INTO config (cle, valeur) VALUES (?, ?)", (key, value))
                self._set_config_json("currencies", self.currencies)
                self._set_config_json("serial_ports", self.serial_ports)
                for key, entry_widget in self.settings_entries.items():
                    if not entry_widget:
                        continue
                    if isinstance(entry_widget, ttk.Combobox):
                        value = entry_widget.get()
                    elif isinstance(entry_widget, tk.Listbox):
                        continue
                    else:
                        try:
                            value = entry_widget.get().strip()
                        except:
                            value = str(entry_widget)
                    if key == 'devise' and value and value not in self.currencies:
                        self.currencies.append(value)
                        self._set_config_json("currencies", self.currencies)
                    if key == 'serial_port_active' and value and value not in self.serial_ports:
                        self.serial_ports.append(value)
                        self._set_config_json("serial_ports", self.serial_ports)
                    save_param(key, value)
                baud = self.baud_rate_combo.get() if getattr(self, "baud_rate_combo", None) else None
                if baud:
                    save_param("baud_rate", baud)
                std = self.standard_tariff_entry.get() if getattr(self, "standard_tariff_entry", None) else None
                if std is not None:
                    save_param("standard_tariff_fcfa_per_6min", std)
                conn.commit()
                messagebox.showinfo("Succès", "Tous les paramètres ont été sauvegardés avec succès.")
                self.status_label.config(text="Paramètres généraux mis à jour.")
                self._refresh_currency_combobox()
                self._refresh_serialport_combobox()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Impossible de sauvegarder les paramètres: {e}")
            print("[DEBUG] save_general_settings exception:", e)

    def logout(self):
        if messagebox.askyesno("Déconnexion", "Êtes-vous sûr de vouloir vous déconnecter de l'administration ?"):
            self.on_closing()
            try:
                from interfaces.login import LoginWindow
                login_app = LoginWindow()
                login_app.run()
            except Exception:
                pass

    def on_closing(self):
        try:
            self.root.destroy()
        except:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AdminInterface(user_id=1)
    app.run()

