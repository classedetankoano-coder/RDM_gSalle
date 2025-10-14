# check_bonus_db.py
from app.bonus_simple import BonusManager

bm = BonusManager()
# affiche quelques configs utiles
print("bonus_enabled:", bm._get_config("bonus_enabled"))
print("bonus_fcfa_per_minute:", bm._get_config("bonus_fcfa_per_minute"))
print("welcome_bonus_minutes:", bm._get_config("welcome_bonus_minutes"))

# lister 5 dernières transactions (aucune au départ)
hist = bm.list_bonus_history(limit=5)
print("transactions (dernieres):", hist)
