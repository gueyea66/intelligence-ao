import re
import unicodedata


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' ' + text + ' '  # padding pour word-boundary matching


# Catégories canoniques — UN seul nom par catégorie
CATEGORY_RULES = {
    "Téléphones & Tablettes": [
        "iphone", "samsung galaxy", "xiaomi", "oppo", "tecno", "infinix", "itel",
        "huawei", "realme", "oneplus", "nokia", "smartphone", "telephone portable",
        "tablette", "tablet", "ipad", "redmi", "poco", "vivo", "motorola", "itel",
        "telephone android", "telephone tactile"
    ],
    "Ordinateurs & Accessoires": [
        "laptop", "ordinateur", "pc portable", "macbook", "dell", "lenovo thinkpad",
        "asus laptop", "acer laptop", "hp laptop", "toshiba laptop", "clavier",
        "souris", "imprimante", "disque dur", "ssd", "webcam", "ram ", "processeur",
        "ecran pc", "moniteur pc"
    ],
    "Électronique & Audio": [
        "airpods", "ecouteur", "casque audio", "casque bluetooth", "enceinte",
        "speaker", "home cinema", "amplificateur", "sono ", "microphone",
        "appareil photo", "drone", "gopro", "montre connectee", "smartwatch",
        "bracelet connecte", "camera", "batterie externe"
    ],
    "TV & Multimédia": [
        "television", "televiseur", "smart tv", "led tv", "oled ", "4k tv",
        "decodeur", "box tv", "projecteur", "videoprojecteur", "tv led",
        "ecran tv", "android tv"
    ],
    "Électroménager": [
        "refrigerateur", "frigo", "congelateur", "machine a laver", "lave-linge",
        "climatiseur", "clim ", "ventilateur", "fer a repasser", "aspirateur",
        "micro-onde", "micro onde", "four ", "cuisiniere", "gaziniere", "chauffe-eau",
        "mixeur", "blender", "cafetiere", "grille-pain", "batterie de cuisine",
        "robot cuisine", "centrifugeuse", "friteuse", "bouilloire", "sterilisateur",
        "refroidisseur", "humidificateur", "purificateur air", "hotte cuisine"
    ],
    "Mode & Vêtements": [
        " robe ", "chemise ", "pantalon", " jean ", " veste ", "manteau",
        " pull ", "t-shirt", "tshirt", " polo ", " short ", " jupe ",
        "pyjama", "sous-vetement", "lingerie", "jogging", "survetement",
        "boubou", "bazin", "wax afric", "kaftan", "dashiki", "agbada",
        "tunique", "combinaison", "ensemble tenue", "vetement", "habit ",
        "manche courte", "manche longue", "col rond", "col v", "oversize",
        "streetwear", "sweat", "hoodie", "bomber", "cardigan", "gilet "
    ],
    "Chaussures": [
        "chaussure", "basket", "sneaker", "nike ", "adidas ", "puma ",
        "reebok", "sandale", " tong ", "botte ", "mocassin", "escarpin",
        "talon haut", "chausson", "mule ", "sabot ", "ballerine",
        "bottine", "derby ", "loafer"
    ],
    "Sacs & Maroquinerie": [
        "sac a main", "sacs a main", "sac dos", "sac bandouliere",
        "sac tresse", "sac chaine", "sac femme", "sacs femme",
        "portefeuille", "valise", "trolley", "bagage", "porte-monnaie",
        "sac cuir", "sac toile", "mini sac", "tote bag"
    ],
    "Bijoux & Accessoires": [
        "boucle d oreille", "boucles d oreille", "collier ", "bracelet ",
        "bague ", "montre ", "bijou", "parure ", "pendentif", "alliance", "broche",
        "chapeau", "casquette", "foulard", "echarpe", "lunettes",
        "ceinture ", "gants", "mitaines"
    ],
    "Beauté & Parfums": [
        "parfum ", "eau de toilette", "deodorant", "creme ", "lotion ",
        "serum ", "mascara", "rouge a levres", "fond de teint", "maquillage",
        "vernis a ongle", "shampoing", "coloration cheveux", "soin cheveux",
        "gel coiffant", "lisseur", "seche-cheveux", "epilateur",
        "brosse visage", "tondeuse", "rasoir", "anti-acne", "anti acne",
        "anti imperfection", "soin peau", "traitement peau", "exfoliant",
        "huile corps", "beurre karite", "hydratant", "eclaircissant"
    ],
    "Santé & Bien-être": [
        "vitamine", "complement alimentaire", "proteine", "whey",
        "thermometre", "tensiometre", "glucometre", "masque chirurgical",
        "gel hydroalcoolique", "desinfectant", "bandage", "pansement",
        "pilulier", "test de grossesse", "soin medical"
    ],
    "Alimentation & Boissons": [
        " riz ", "huile alimentaire", " sucre ", "farine", " lait ",
        " cafe ", "jus ", "eau minerale", " biere ", "chocolat",
        "biscuit", "conserve", "sardine", "thon", "epice",
        " sauce ", "condiment", "vinaigre", "concentre tomate",
        "cube maggi", "arachide", "noix de cajou"
    ],
    "Maison & Décoration": [
        "canape", " sofa ", "fauteuil", " chaise ", "table basse",
        "table a manger", "bureau meuble", "armoire", "commode",
        "matelas", "couette", "rideau", " tapis ", "luminaire",
        " lampe ", "miroir", "etagere", "vase ", "tableau deco",
        "bougie", "coussin", "plaid", "drap", "housse"
    ],
    "Outillage & Bricolage": [
        "boite a outils", "tournevis", "cle a molette", "marteau",
        "perceuse", "scie ", "niveau ", "pince ", "ruban mesure",
        "outillage", "outil ", "maletoute", "malette outils",
        "visseuse", "ponceuse", "meuleuse"
    ],
    "Matériaux & Construction": [
        "ciment", "fer a beton", " tole ", " brique ", "carrelage",
        "parquet", "peinture mur", "cable electrique", "robinet",
        "tuyau pvc", "porte blindee", "fenetre aluminium", "serrure",
        "dalle beton", "plafond"
    ],
    "Auto & Moto": [
        "voiture", " moto ", "scooter", "piece auto", "piece detachee auto",
        " pneu ", "batterie voiture", "huile moteur", "filtre a huile",
        "phare voiture", "autoradio", "gps voiture", "siege auto",
        "retroviseur", "carrosserie", "amortisseur"
    ],
    "Sport & Fitness": [
        "haltere", "musculation", "tapis roulant", "ballon de foot",
        "ballon football", "ballon basket", " ballon ", "raquette tennis",
        "velo fitness", "equipement sport", "gants boxe", "tente camping",
        "ski ", "surf ", "natation", "cyclisme", "joggeur"
    ],
    "Bébé & Enfant": [
        "poussette", "siege bebe", "couche bebe", "biberon", " jouet ",
        "lego ", "poupee", "cartable", "sac ecole", "hochet",
        "tour de lit", "baignoire bebe", "parc bebe", "trottinette enfant"
    ],
    "Énergie & Solaire": [
        "panneau solaire", "batterie solaire", "onduleur",
        "groupe electrogene", "generateur electrique", "lampe solaire",
        "chargeur solaire", "energie solaire", "kit solaire"
    ],
    "Informatique & Logiciels": [
        "logiciel", "antivirus", "licence microsoft", "windows 10",
        "microsoft office", "adobe ", "formation informatique"
    ],
    "Fournitures & Bureau": [
        "stylo", "crayon", "cahier", "classeur", "agrafeuse",
        "calculatrice", "papier a4", "enveloppe", "tampon", "cartouche encre"
    ],
}

# Normalisation des catégories existantes (fusionner les doublons)
CATEGORY_NORMALIZER = {
    "Autre": "Divers",
    "autres": "Divers",
    "other": "Divers",
    "Other": "Divers",
    "Non classe": "Divers",
    "Mode & Vetements": "Mode & Vêtements",
    "Mode & vetements": "Mode & Vêtements",
    "Electromenager": "Électroménager",
    "electromenager": "Électroménager",
    "Electronique": "Électronique & Audio",
    "TV & Multimedia": "TV & Multimédia",
    "Beaute & Parfums": "Beauté & Parfums",
    "Beaute & Sante": "Beauté & Parfums",
    "Sante": "Santé & Bien-être",
    "Alimentation": "Alimentation & Boissons",
    "Bebe & Enfant": "Bébé & Enfant",
    "Materiaux & Construction": "Matériaux & Construction",
    "Energie & Solaire": "Énergie & Solaire",
    "Telephones & Tablettes": "Téléphones & Tablettes",
    "Maison & Decoration": "Maison & Décoration",
    "Sport & Loisirs": "Sport & Fitness",
}


def categorize_product(nom: str = "", modele: str = "", marque: str = "") -> str:
    text = _normalize(f"{nom} {modele} {marque}")
    for categorie, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            kw_norm = _normalize(kw).strip()
            if kw_norm and kw_norm in text:
                return categorie
    return "Divers"


def normalize_category(cat: str) -> str:
    """Normalise une catégorie existante vers le nom canonique."""
    if not cat:
        return "Divers"
    return CATEGORY_NORMALIZER.get(cat, cat)


def dry_run(session):
    from src.database.models import Produit
    from sqlalchemy import or_

    produits = session.query(Produit).filter(
        or_(
            Produit.categorie_1.in_(["Divers", "Autres", "divers", "autres", "other", "Other", "Autre"]),
            Produit.categorie_1.is_(None)
        )
    ).limit(5000).all()

    stats = {}
    recategorised = 0
    for p in produits:
        new_cat = categorize_product(
            p.description or "",
            p.modele or "",
            p.marque or ""
        )
        if new_cat != "Divers":
            recategorised += 1
        stats[new_cat] = stats.get(new_cat, 0) + 1

    print(f"Analyse: {len(produits)} produits")
    print(f"Recategorisables: {recategorised} ({100*recategorised//max(len(produits),1)}%)")
    for cat, count in sorted(stats.items(), key=lambda x: -x[1])[:20]:
        print(f"  {cat}: {count}")
    return stats


def run_migration(session):
    from src.database.models import Produit
    from sqlalchemy import or_

    # Étape 1 : normaliser les catégories existantes dupliquées
    print("Étape 1: Normalisation des catégories existantes...")
    all_prods = session.query(Produit).filter(
        Produit.categorie_1.in_(list(CATEGORY_NORMALIZER.keys()))
    ).limit(10000).all()
    normalized = 0
    for p in all_prods:
        new = normalize_category(p.categorie_1)
        if new != p.categorie_1:
            p.categorie_1 = new
            normalized += 1
    session.commit()
    print(f"  {normalized} catégories normalisées")

    # Étape 2 : recatégoriser les "Divers"
    print("Étape 2: Recatégorisation des Divers...")
    batch_size = 500
    offset = 0
    total_updated = 0

    while True:
        produits = session.query(Produit).filter(
            or_(
                Produit.categorie_1.in_(["Divers", "Autres", "divers", "autres", "other", "Other", "Autre"]),
                Produit.categorie_1.is_(None)
            )
        ).limit(batch_size).offset(offset).all()

        if not produits:
            break

        changed_in_batch = 0
        for p in produits:
            new_cat = categorize_product(
                p.description or "",
                p.modele or "",
                p.marque or ""
            )
            if new_cat != "Divers" or p.categorie_1 is None:
                p.categorie_1 = new_cat
                total_updated += 1
                changed_in_batch += 1

        session.commit()
        print(f"  Batch {offset//batch_size + 1}: {changed_in_batch} changements ({total_updated} total)")

        if changed_in_batch == 0:
            offset += batch_size
        # Si tous les produits du batch ont été changés (exit Divers), pas besoin d'avancer l'offset
        # car les prochains Divers remonteront automatiquement

        # Sécurité anti-boucle infinie
        if offset > 50000:
            break

    print(f"Migration terminée: {total_updated} produits recatégorisés")
    return total_updated
