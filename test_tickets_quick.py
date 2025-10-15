# test_tickets_quick.py
from app.tickets_fidelite import TicketsManager

tm = TicketsManager()
tm.run_migrations()

# Utilisateur test (ID 1)
user_id = 1

print("Ajout ticket manuel pour aujourd'hui (admin_add_ticket)...")
from datetime import date
today = date.today().isoformat()
tid = tm.admin_add_ticket(user_id, today, notes="test rapide")
print("Ticket ajouté id:", tid)

print("Progression (7/14/30):", tm.get_user_progress(user_id))
print("Historique tickets (dernieres lignes):")
tickets = tm.list_tickets(user_id, limit=10)
for t in tickets:
    print(t)

print("Historique grants (récompenses):")
grants = tm.list_grants(user_id, limit=10)
for g in grants:
    print(g)
