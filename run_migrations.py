# run_migrations.py
from app.bonus_simple import BonusManager

if __name__ == "__main__":
    bm = BonusManager()
    try:
        bm.run_migrations()
        print("Migrations exécutées avec succès ✅")
    except Exception as e:
        print("Erreur lors des migrations :", e)
