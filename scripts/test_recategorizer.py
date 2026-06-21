import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_quality.recategorizer import categorize_product, CATEGORY_RULES

# Test sur les exemples réels
samples = [
    ("Sivoderm Gamme anti-Acné -anti imperfection", "", "Sivoderm"),
    ("Chaussons mule ZG style coréen pour femmes, port extérieur", "", "ZG"),
    ("Lot De 2 T-Shirt En Coton à Manches Courtes Pour Hommes", "De 2 T-Shirt En Coton", "Lot"),
    ("6 paires de boucles d'oreilles à poussoir style vintage pour femmes", "", "6"),
    ("STY Sacs à Chaîne pour Femmes, Petit Sac Tressé Bandoulière", "Sacs à Chaîne pour Femmes", "STY"),
    ("Mateamoda 2 PCS Sacs à Main Pour Femmes", "2 PCS Sacs à Main", "Mateamoda"),
    ("Malette De Boîte A Outils - 16 En 1 - Multicolore", "De Boîte A Outils - 16 En 1", "Malette"),
    ("Binatone Refroidisseur D'Air BAC-201 - 20L Tactile-120 Watts", "Refroidisseur D'Air BAC-201", "Binatone"),
    ("Kipsta Ballon de football light ball taille 5", "Ballon de football light ball taille 5", "Kipsta"),
]

print("=== TEST RECATEGORIZER ===")
matched = 0
for desc, modele, marque in samples:
    cat = categorize_product(desc, modele, marque)
    ok = "OK" if cat != "Divers" else "XX"
    if cat != "Divers":
        matched += 1
    print(f"{ok} {cat:35s} | {desc[:55]}")

print(f"\nMatch: {matched}/{len(samples)} ({100*matched//len(samples)}%)")
