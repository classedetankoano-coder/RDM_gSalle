# run_migrations_tickets.py
from app.tickets_fidelite import TicketsManager

if __name__ == "__main__":
    tm = TicketsManager()
    try:
        tm.run_migrations()
        print("Migrations tickets de fidélité exécutées ✅")
    except Exception as e:
        print("Erreur lors des migrations :", e)
