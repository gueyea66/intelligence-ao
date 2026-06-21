import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.nlp_engine import analyze_message

# Messages réels du commerce informel Afrique de l'Ouest
test_messages = [
    "Samsung A54 disponible, etat neuf, prix 185 000 FCFA. Livraison Dakar. Contactez 77 123 45 67",
    "Arnaque total, j'ai envoyé 50000 CFA mais jamais recu ma commande. Escroc. Fuyez ce vendeur!",
    "Rupture de stock sur le riz Thai. Quelqu'un sait ou trouver du 25kg pas trop cher?",
    "Tissu wax holland 6 yards pour 25 000F. Disponible en plusieurs coloris. Qualite certifiee.",
    "Le probleme avec les livraisons c'est que ca prend trop de temps. Impossible de respecter les delais.",
    "Waaw deedeet man def lii, prix bi dafa tang trop.",  # Wolof mix
]

for msg in test_messages:
    result = analyze_message(msg)
    print(f"\nMSG: {msg[:60]}...")
    print(f"  Langue: {result['langue']}")
    print(f"  Sentiment: {result['sentiment']} ({result['score_sentiment']})")
    print(f"  Topics: {result['topics']}")
    print(f"  Type: {result['type_message']}")
    if result['prix_mentionnes']:
        print(f"  Prix: {result['prix_mentionnes']}")
    if result['pain_points']:
        print(f"  Pain points: {result['pain_points'][:1]}")
    print(f"  Contact: {result['contient_contact']}")
