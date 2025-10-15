import tkinter as tk
from tkinter import ttk, messagebox
import bcrypt
from models.database import DatabaseManager
from config.settings import DATABASE_PATH
import os

# --- Importation de l'interface Administrateur ---
from interfaces.admin_interface import AdminInterface
# --- Importation de l'interface Gérant ---
from interfaces.manager_interface import ManagerInterface


class LoginWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RDM gSalle - Connexion")
        self.root.geometry("600x690")  # Hauteur ajustée pour tout voir
        self.root.resizable(False, False)
        
        # Style
        self.setup_styles()
        
        # Centrer la fenêtre sur l'écran
        self.center_window_on_screen()
        
        # Base de données
        self.db = DatabaseManager(DATABASE_PATH)
        
        # Variables
        self.is_new_account = tk.BooleanVar(value=False)
        self.show_password = tk.BooleanVar(value=False)
        
        self.load_logo() # Charge le logo une fois
        self.create_widgets()
    
    def setup_styles(self):
        """Configure les styles personnalisés."""
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Arial", 24, "bold"))
        style.configure("Subtitle.TLabel", font=("Arial", 11), foreground="gray")
        style.configure("Big.TButton", font=("Arial", 12, "bold"))
        style.configure("Small.TButton", font=("Arial", 9))
    
    def center_window_on_screen(self):
        """Centre la fenêtre sur l'écran."""
        self.root.update_idletasks()
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        window_width = 600
        window_height = 690
        
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        y = max(50, y - 50) # Ajuste légèrement vers le haut
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def load_logo(self):
        """Charge votre logo PNG."""
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
            if os.path.exists(logo_path):
                from PIL import Image, ImageTk
                image = Image.open(logo_path)
                image = image.resize((80, 80), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(image)
            else:
                self.logo_image = None
        except Exception as e:
            print(f"Erreur chargement logo: {e}")
            self.logo_image = None
    
    def get_existing_users(self, role):
        """Récupère les utilisateurs existants pour un rôle donné."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM users WHERE role = ? ORDER BY username", (role,))
                users = [row[0] for row in cursor.fetchall()]
                return users
        except Exception as e:
            print(f"Erreur récupération utilisateurs: {e}")
            return []
    
    def create_widgets(self):
        """Crée tous les widgets de la fenêtre de connexion."""
        # Conteneur principal pour le centrage
        main_container = tk.Frame(self.root)
        main_container.pack(expand=True, fill=tk.BOTH)
        
        # Frame de contenu (sera centrée par main_container)
        content_frame = ttk.Frame(main_container, padding="30")
        content_frame.pack() # Utilise pack pour que content_frame se centre
        
        # En-tête avec votre logo
        self.create_header(content_frame)
        
        # Mode sélection (Connexion ou Nouveau compte)
        self.create_mode_selection(content_frame)
        
        # Formulaire
        self.create_form(content_frame)
        
        # Boutons
        self.create_action_buttons(content_frame)
        
        # Informations
        self.create_info_section(content_frame)
    
    def create_header(self, parent):
        """Crée l'en-tête avec votre logo."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        if self.logo_image:
            logo_label = ttk.Label(header_frame, image=self.logo_image)
            logo_label.image = self.logo_image # Garder référence
            logo_label.pack(pady=(0, 10))
        else:
            logo_label = ttk.Label(
                header_frame, 
                text="🎮", 
                font=("Arial", 48),
                foreground="#4A90E2"
            )
            logo_label.pack(pady=(0, 10))
        
        title_label = ttk.Label(header_frame, text="RDM gSalle", style="Title.TLabel")
        title_label.pack()
        
        subtitle_label = ttk.Label(
            header_frame, 
            text="Système de Gestion de Salle de Jeux", 
            style="Subtitle.TLabel"
        )
        subtitle_label.pack(pady=(5, 0))
    
    def create_mode_selection(self, parent):
        """Crée la sélection entre connexion et nouveau compte."""
        mode_frame = ttk.LabelFrame(parent, text="Mode", padding="12")
        mode_frame.pack(fill=tk.X, pady=(0, 15))
        
        existing_rb = ttk.Radiobutton(
            mode_frame, 
            text="🔐 Se connecter avec un compte existant", 
            variable=self.is_new_account, 
            value=False,
            command=self.toggle_mode
        )
        existing_rb.pack(anchor=tk.W, pady=2)
        
        new_rb = ttk.Radiobutton(
            mode_frame, 
            text="➕ Créer un nouveau compte", 
            variable=self.is_new_account, 
            value=True,
            command=self.toggle_mode
        )
        new_rb.pack(anchor=tk.W, pady=2)
    
    def create_form(self, parent):
        """Crée le formulaire principal."""
        self.form_frame = ttk.Frame(parent)
        self.form_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Type de compte
        type_frame = ttk.LabelFrame(self.form_frame, text="Type de compte", padding="12")
        type_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.account_type = ttk.Combobox(
            type_frame,
            values=["👤 Gérant", "👑 Administrateur", "🤝 Co-Administrateur"],
            state="readonly",
            font=("Arial", 12),
            width=40
        )
        self.account_type.pack(fill=tk.X)
        self.account_type.set("👤 Gérant")
        self.account_type.bind('<<ComboboxSelected>>', self.on_account_type_change_main)
        
        # Nom d'utilisateur avec dropdown intelligent
        self.create_username_field()
        
        # Mot de passe avec bouton afficher/masquer
        self.create_password_field()
        
        # Confirmation mot de passe (masqué initialement)
        self.confirm_frame = ttk.LabelFrame(self.form_frame, text="Confirmer le mot de passe", padding="12")
        self.confirm_entry = ttk.Entry(self.confirm_frame, show="*", font=("Arial", 12))
        self.confirm_entry.pack(fill=tk.X)
        
        # Mot de passe admin (masqué initialement)
        self.admin_frame = ttk.LabelFrame(self.form_frame, text="Mot de passe Administrateur", padding="12")
        self.admin_entry = ttk.Entry(self.admin_frame, show="*", font=("Arial", 12))
        self.admin_entry.pack(fill=tk.X)
        
        # Masquer initialement
        self.confirm_frame.pack_forget()
        self.admin_frame.pack_forget()
    
    def create_username_field(self):
        """Crée le champ nom d'utilisateur avec dropdown intelligent."""
        self.username_frame = ttk.LabelFrame(self.form_frame, text="Nom d'utilisateur", padding="12")
        self.username_frame.pack(fill=tk.X, pady=(0, 12))
        
        username_container = ttk.Frame(self.username_frame)
        username_container.pack(fill=tk.X)
        
        self.username_combo = ttk.Combobox(
            username_container,
            font=("Arial", 12),
            width=40
        )
        
        self.username_entry = ttk.Entry(username_container, font=("Arial", 12))
        
        self.username_entry.pack(fill=tk.X)
        self.current_username_widget = "entry"
    
    def create_password_field(self):
        """Crée le champ mot de passe avec bouton afficher/masquer."""
        password_frame = ttk.LabelFrame(self.form_frame, text="Mot de passe", padding="12")
        password_frame.pack(fill=tk.X, pady=(0, 12))
        
        password_container = ttk.Frame(password_frame)
        password_container.pack(fill=tk.X)
        
        self.password_entry = ttk.Entry(password_container, show="*", font=("Arial", 12))
        self.password_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.toggle_password_btn = ttk.Button(
            password_container,
            text="👁️",
            width=3,
            command=self.toggle_password_visibility,
            style="Small.TButton"
        )
        self.toggle_password_btn.pack(side=tk.RIGHT, padx=(5, 0))
    
    def toggle_password_visibility(self):
        """Bascule l'affichage du mot de passe."""
        if self.show_password.get():
            self.password_entry.config(show="*")
            self.toggle_password_btn.config(text="👁️")
            self.show_password.set(False)
        else:
            self.password_entry.config(show="")
            self.toggle_password_btn.config(text="🙈")
            self.show_password.set(True)
    
    def on_account_type_change_main(self, event=None):
        """Gère les changements de type de compte pour le champ username."""
        selected = self.account_type.get()
        
        if not self.is_new_account.get():  # Mode CONNEXION
            if "Administrateur" in selected and "Co-" not in selected:
                if self.current_username_widget != "entry":
                    self.username_combo.pack_forget()
                    self.username_entry.pack(fill=tk.X)
                    self.current_username_widget = "entry"
            else:
                if self.current_username_widget != "combo":
                    self.username_entry.pack_forget()
                    self.username_combo.pack(fill=tk.X)
                    self.current_username_widget = "combo"
                    
                    role = "manager" if "Gérant" in selected else "co_admin"
                    existing_users = self.get_existing_users(role)
                    self.username_combo['values'] = existing_users
                    self.username_combo['state'] = 'normal'
        else:  # Mode NOUVEAU COMPTE
            if self.current_username_widget != "entry":
                self.username_combo.pack_forget()
                self.username_entry.pack(fill=tk.X)
                self.current_username_widget = "entry"
    
    def get_username_value(self):
        """Récupère la valeur du nom d'utilisateur selon le widget actif."""
        if self.current_username_widget == "combo":
            return self.username_combo.get().strip()
        else:
            return self.username_entry.get().strip()
    
    def set_username_value(self, value):
        """Définit la valeur du nom d'utilisateur selon le widget actif."""
        if self.current_username_widget == "combo":
            self.username_combo.delete(0, tk.END)
            self.username_combo.insert(0, value)
        else:
            self.username_entry.delete(0, tk.END)
            self.username_entry.insert(0, value)
    
    def create_action_buttons(self, parent):
        """Crée les boutons d'action."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=(10, 15))
        
        self.main_button = ttk.Button(
            button_frame,
            text="🔐 Se connecter",
            command=self.handle_main_action,
            style="Big.TButton"
        )
        self.main_button.pack(pady=8, ipadx=20, ipady=8)
        
        self.back_button = ttk.Button(
            button_frame,
            text="← Retour à la connexion",
            command=self.back_to_login
        )
    
    def create_info_section(self, parent):
        """Crée la section d'informations."""
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X)
        
        separator = ttk.Separator(info_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=(0, 8))
        
        self.info_label = ttk.Label(
            info_frame,
            text="💡 Compte par défaut: admin / admin123 (Administrateur)",
            font=("Arial", 10),
            foreground="blue",
            justify=tk.CENTER
        )
        self.info_label.pack()
    
    def toggle_mode(self):
        """Bascule entre mode connexion et création de compte."""
        if self.is_new_account.get():
            self.main_button.config(text="➕ Créer le compte")
            self.confirm_frame.pack(fill=tk.X, pady=(0, 12))
            self.back_button.pack(pady=5)
            self.info_label.config(
                text="🔒 Pour créer un Co-Administrateur, le mot de passe Admin est requis",
                foreground="orange"
            )
            self.account_type.bind('<<ComboboxSelected>>', self.on_account_type_change)
            self.clear_form()
            self.on_account_type_change_main()
        else:
            self.main_button.config(text="🔐 Se connecter")
            self.confirm_frame.pack_forget()
            self.admin_frame.pack_forget()
            self.back_button.pack_forget()
            self.info_label.config(
                text="💡 Compte par défaut: admin / admin123 (Administrateur)",
                foreground="blue"
            )
            self.set_username_value("admin")
            self.password_entry.delete(0, tk.END)
            self.password_entry.insert(0, "admin123")
            self.account_type.set("👑 Administrateur")
            self.on_account_type_change_main()
    
    def on_account_type_change(self, event=None):
        """Gère les changements de type de compte en mode création."""
        if self.is_new_account.get():
            selected = self.account_type.get()
            if "Co-Administrateur" in selected:
                self.admin_frame.pack(fill=tk.X, pady=(0, 12))
            else:
                self.admin_frame.pack_forget()
        self.on_account_type_change_main(event)
    
    def back_to_login(self):
        """Retour au mode connexion."""
        self.is_new_account.set(False)
        self.toggle_mode()
    
    def clear_form(self):
        """Vide tous les champs."""
        self.set_username_value("")
        self.password_entry.delete(0, tk.END)
        self.confirm_entry.delete(0, tk.END)
        self.admin_entry.delete(0, tk.END)
    
    def handle_main_action(self):
        """Gère l'action principale."""
        if self.is_new_account.get():
            self.create_account()
        else:
            self.login()
    
    def get_role_from_selection(self):
        """Convertit la sélection en rôle."""
        selection = self.account_type.get()
        if "Gérant" in selection:
            return "manager"
        elif "Co-Administrateur" in selection:
            return "co_admin"
        else:
            return "admin"
    
    def create_account(self):
        """Crée un nouveau compte."""
        username = self.get_username_value()
        password = self.password_entry.get()
        confirm_password = self.confirm_entry.get()
        role = self.get_role_from_selection()
        
        if not username or not password:
            messagebox.showerror("Erreur", "Veuillez remplir tous les champs.")
            return
        
        if len(username) < 3:
            messagebox.showerror("Erreur", "Nom d'utilisateur trop court (min 3 caractères).")
            return
        
        if len(password) < 6:
            messagebox.showerror("Erreur", "Mot de passe trop court (min 6 caractères).")
            return
        
        if password != confirm_password:
            messagebox.showerror("Erreur", "Les mots de passe ne correspondent pas.")
            return
        
        if role == "co_admin":
            admin_password = self.admin_entry.get()
            if not admin_password:
                messagebox.showerror("Erreur", "Mot de passe administrateur requis.")
                return
            
            if not self.verify_admin_password(admin_password):
                messagebox.showerror("Erreur", "Mot de passe administrateur incorrect.")
                return
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", "Nom d'utilisateur déjà existant.")
                    return
                
                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, password_hash.decode(), role)
                )
                conn.commit()
                
                messagebox.showinfo("Succès", f"Compte créé avec succès !\n\nUtilisateur: {username}")
                self.back_to_login()
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur création compte:\n{str(e)}")
    
    def verify_admin_password(self, password):
        """Vérifie le mot de passe admin."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT password_hash FROM users WHERE role = 'admin' LIMIT 1")
                result = cursor.fetchone()
                if result:
                    return bcrypt.checkpw(password.encode(), result[0].encode())
            return False
        except Exception as e:
            print(f"Erreur vérification mot de passe admin: {e}")
            return False
    
    def login(self):
        """Connexion."""
        username = self.get_username_value()
        password = self.password_entry.get()
        role = self.get_role_from_selection()
        
        if not username or not password:
            messagebox.showerror("Erreur", "Champs obligatoires manquants.")
            return
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, password_hash, role FROM users WHERE username = ? AND role = ?",
                    (username, role)
                )
                user = cursor.fetchone()
                
                if user and bcrypt.checkpw(password.encode(), user[1].encode()):
                    messagebox.showinfo("Succès", f"Bienvenue {username}!")
                    self.root.destroy()
                    
                    if role in ["admin", "co_admin"]:
                        self.launch_admin_interface(user[0])
                    else:
                        self.launch_manager_interface(user[0])
                else:
                    messagebox.showerror("Erreur", "Identifiants incorrects.")
                    self.password_entry.delete(0, tk.END)
                    self.password_entry.focus()
        except Exception as e:
            messagebox.showerror("Erreur BD", f"Erreur de connexion: {e}")
    
    def launch_admin_interface(self, user_id):
        print(f"🔧 Lancement interface admin - utilisateur {user_id}")
        admin_app = AdminInterface(user_id) # ✅ Lance AdminInterface
        admin_app.run()
    
    def launch_manager_interface(self, user_id):
        print(f"🎮 Lancement interface gérant - utilisateur {user_id}")
        manager_app = ManagerInterface(user_id) # ✅ Lance ManagerInterface
        manager_app.run()
    
    def run(self):
        self.root.bind('<Return>', lambda e: self.handle_main_action())
        
        if self.current_username_widget == "combo":
            self.username_combo.focus()
        else:
            self.username_entry.focus()
        
        if not self.is_new_account.get():
            self.set_username_value("admin")
            self.password_entry.insert(0, "admin123")
            self.account_type.set("👑 Administrateur")
            self.on_account_type_change_main()
        
        self.root.mainloop()



