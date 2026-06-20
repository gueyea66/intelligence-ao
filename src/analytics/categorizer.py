"""
Recatégorisation automatique des produits par NLP (règles + regex).
Transforme "Général" → catégories réelles extraites du titre produit.
"""
import re
import logging
from unidecode import unidecode

logger = logging.getLogger(__name__)

# Hiérarchie : cat_1 → [(cat_2, [mots-clés])]
CATEGORIES = {
    "Téléphones & Tablettes": [
        ("Smartphones",        ["iphone", "samsung galaxy", "smartphone", "android", "redmi", "xiaomi", "tecno", "infinix", "oppo", "vivo", "realme", "huawei", "honor"]),
        ("Tablettes",          ["ipad", "tablette", "tablet"]),
        ("Accessoires Téléphone", ["coque", "chargeur", "cable usb", "ecouteur", "airpod", "casque bluetooth", "powerbank", "batterie externe", "verre trempe"]),
        ("Téléphones Fixes",   ["telephone fixe", "dect"]),
    ],
    "Informatique": [
        ("Laptops & PC",       ["laptop", "ordinateur portable", "macbook", "notebook", "chromebook", "lenovo", "dell", "hp pavilion", "asus", "acer", "thinkpad"]),
        ("PC Bureau",          ["pc de bureau", "tour ordinateur", "desktop"]),
        ("Périphériques",      ["clavier", "souris", "moniteur", "ecran pc", "imprimante", "scanner", "webcam", "disque dur", "ssd", "cle usb", "memoire ram"]),
        ("Réseaux",            ["routeur", "wifi", "modem", "switch reseau", "cable ethernet"]),
    ],
    "Électronique": [
        ("TV & Audio",         ["television", "tv led", "tv oled", "smart tv", "samsung tv", "lg tv", "home cinema", "barre de son", "enceinte", "hifi", "ampli"]),
        ("Photo & Vidéo",      ["appareil photo", "camera", "gopro", "drone", "objectif", "trepied", "flash photo"]),
        ("Consoles & Jeux",    ["playstation", "ps4", "ps5", "xbox", "nintendo", "manette jeu", "jeu video"]),
        ("Éclairage",          ["ampoule led", "lampe", "luminaire", "spot led", "lampadaire", "panneau led"]),
    ],
    "Électroménager": [
        ("Cuisine",            ["mixeur", "blender", "robot cuiseur", "friteuse", "micro-onde", "four electrique", "grille pain", "cafetiere", "bouilloire", "machine a pain"]),
        ("Froid",              ["refrigerateur", "congelateur", "climatiseur", "ventilateur", "climatisation"]),
        ("Lavage",             ["machine a laver", "lave linge", "seche linge", "fer a repasser"]),
        ("Énergie",            ["groupe electrogene", "generateur", "panneau solaire", "onduleur", "stabilisateur"]),
    ],
    "Mode & Vêtements": [
        ("Vêtements Femme",    ["robe", "jupe", "blouse", "chemisier", "legging", "combinaison femme", "tailleur", "soutien gorge"]),
        ("Vêtements Homme",    ["chemise homme", "pantalon homme", "costume", "veste homme", "polo", "jean homme", "short homme"]),
        ("Chaussures",         ["chaussure", "basket", "sneaker", "sandal", "botte", "mocassin", "escarpin", "tong"]),
        ("Accessoires Mode",   ["sac a main", "sac dos", "ceinture", "montre", "bijou", "collier", "bracelet", "bague", "lunette"]),
        ("Sous-vêtements",     ["sous-vetement", "boxer", "slip", "culotte", "lingerie"]),
    ],
    "Maison & Décoration": [
        ("Meubles",            ["canape", "sofa", "lit", "matelas", "armoire", "commode", "bureau", "chaise", "table basse", "etagere", "meuble tv"]),
        ("Literie",            ["couette", "drap", "oreiller", "housse de couette", "protege matelas"]),
        ("Décoration",         ["tableau", "miroir", "vase", "bougie", "rideau", "coussin", "tapis", "plante artificielle"]),
        ("Cuisine & Table",    ["casserole", "poele", "ustensile", "assiette", "verre", "couverts", "robot culinaire"]),
    ],
    "Sport & Fitness": [
        ("Musculation",        ["haltere", "barre muscu", "banc de musculation", "kettlebell", "elastique fitness", "tapis de sport"]),
        ("Sports Collectifs",  ["ballon foot", "maillot foot", "ballon basket", "filet de foot"]),
        ("Vélos & Trottinettes",["velo", "trottinette", "scooter electrique", "casque velo"]),
        ("Fitness",            ["corde a sauter", "stepper", "velo elliptique", "rameur"]),
    ],
    "Beauté & Santé": [
        ("Soins Visage",       ["creme visage", "serum", "masque visage", "lotion", "tonique"]),
        ("Soins Corps",        ["creme corps", "huile corporelle", "gel douche", "savon", "deodorant"]),
        ("Cheveux",            ["shampoing", "apres-shampoing", "masque capillaire", "lisseur", "seche cheveux", "fer a friser", "perruque", "extension"]),
        ("Maquillage",         ["rouge a levres", "fond de teint", "mascara", "eyeliner", "palette", "blush", "correcteur"]),
        ("Parfum",             ["parfum", "eau de toilette", "deodorant parfum"]),
    ],
    "Bébé & Enfant": [
        ("Puériculture",       ["poussette", "lit bebe", "siege auto", "porte bebe", "couche", "biberon"]),
        ("Vêtements Enfant",   ["pyjama bebe", "body bebe", "vetement enfant", "chaussure enfant"]),
        ("Jouets",             ["jouet", "peluche", "poupee", "lego", "jeu d eveil"]),
    ],
    "Auto & Moto": [
        ("Accessoires Auto",   ["autoradio", "gps voiture", "dashcam", "volant", "tapis voiture", "housses siege"]),
        ("Pièces Auto",        ["filtre huile", "filtre air", "frein", "batterie voiture", "amortisseur"]),
        ("Motos",              ["moto", "scooter", "casque moto", "gants moto"]),
    ],
    "Matériaux & Construction": [
        ("Ciment & Gros Œuvre",["ciment", "beton", "parpaing", "brique", "sable", "gravier"]),
        ("Fer & Acier",        ["fer a beton", "barre fer", "tole", "acier", "tube acier"]),
        ("Peinture",           ["peinture mur", "enduit", "vernis", "primaire"]),
        ("Plomberie",          ["tuyau pvc", "robinet", "pompe eau", "fosse septique", "cumulus"]),
        ("Électricité",        ["cable electrique", "disjoncteur", "tableau electrique", "prise electrique", "interrupteur"]),
    ],
    "Alimentation": [
        ("Céréales & Farine",  ["riz", "mil", "farine", "mais", "sorgho", "couscous"]),
        ("Huiles & Graisses",  ["huile arachide", "huile palme", "margarine", "beurre"]),
        ("Sucre & Confiserie", ["sucre", "chocolat", "biscuit", "confiture"]),
        ("Boissons",           ["eau minerale", "jus de fruit", "lait", "the", "cafe"]),
    ],
}


def categoriser_produit(titre: str, description: str = "") -> tuple[str, str]:
    """
    Retourne (categorie_1, categorie_2) depuis le titre.
    """
    texte = unidecode((titre + " " + description).lower())
    texte = re.sub(r'[^\w\s-]', ' ', texte)

    best_cat1, best_cat2, best_score = "Divers", "Autre", 0

    for cat1, sous_cats in CATEGORIES.items():
        for cat2, keywords in sous_cats:
            score = 0
            for kw in keywords:
                kw_norm = unidecode(kw.lower())
                if kw_norm in texte:
                    # Bonus si le mot-clé est long (plus spécifique)
                    score += len(kw_norm.split())
            if score > best_score:
                best_score = score
                best_cat1 = cat1
                best_cat2 = cat2

    return best_cat1, best_cat2


def run_recategorisation(config: dict) -> dict:
    """
    Recatégorise tous les produits "Général" en base.
    Retourne stats de résultat.
    """
    from src.database.models import get_session, Produit
    session = get_session(config)

    produits = session.query(Produit).filter(
        (Produit.categorie_1 == "Général") | (Produit.categorie_1.is_(None))
    ).all()

    logger.info(f"Recatégorisation de {len(produits)} produits...")

    stats = {}
    batch_size = 500
    for i, p in enumerate(produits):
        titre = f"{p.marque or ''} {p.modele or ''} {p.description or ''}"
        cat1, cat2 = categoriser_produit(titre)
        p.categorie_1 = cat1
        p.categorie_2 = cat2
        stats[cat1] = stats.get(cat1, 0) + 1

        if i % batch_size == 0:
            session.commit()
            logger.info(f"  {i}/{len(produits)} traités...")

    session.commit()
    session.close()
    logger.info(f"Recatégorisation terminée : {stats}")
    return stats
