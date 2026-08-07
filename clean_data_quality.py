"""
Nettoyage qualite des donnees — idempotent, lance chaque jour par run_daily.bat.

1. appels_offres : ANSD = publications statistiques, pas des AO -> statut 'hors_scope'
2. appels_offres : doublons (source+objet) -> statut 'doublon' (on garde le plus ancien)
3. appels_offres : normalisation des categories (IT/tech -> Informatique, etc.)
4. appels_offres : recategorisation par mots-cles des 'Autre'
5. appels_offres : extraction budget depuis objet/donnees_brutes (best effort)
6. annonces_informel : categorie_std depuis le slug notes_terrain
7. discussions_sociales : marquage spam (crypto/trading/arnaques)

Aucune suppression : tout passe par des statuts/flags reversibles.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, '.')
with open('config/.env', encoding='utf-8-sig') as f:
    for l in f:
        l = l.strip()
        if l and not l.startswith('#') and '=' in l:
            k, v = l.split('=', 1); os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'], connect_args={'sslmode': 'require'})

# ── mappings ──────────────────────────────────────────────────────────────────

CAT_SYNONYMES = {
    'IT': 'Informatique', 'tech': 'Informatique', 'informatique': 'Informatique',
    'travaux': 'Travaux BTP', 'Construction': 'Travaux BTP', 'construction': 'Travaux BTP',
    'conseil': 'Conseil', 'divers': 'Autre', 'Général': 'Autre', 'General': 'Autre',
    'agriculture': 'Agriculture', 'energie': 'Énergie', 'Sante': 'Santé', 'sante': 'Santé',
}

# ordre = priorite (premier match gagne)
CAT_KEYWORDS = [
    ('Travaux BTP', r'travaux|construction|rehabilitation|réhabilitation|batiment|bâtiment|route|autoroute|pont|voirie|pavage|genie civil|génie civil|amenagement|aménagement'),
    ('Informatique', r'informatique|logiciel|ordinateur|serveur|digitalisation|numerique|numérique|reseau informatique|licence|datacenter|application'),
    ('Conseil', r'consultant|consultance|etude|étude|audit|supervision|controle et surveillance|contrôle et surveillance|assistance technique|maitrise d.oeuvre|maîtrise d.œuvre|recrutement d.un cabinet'),
    ('Hydraulique', r'forage|hydraulique|adduction d.eau|chateau d.eau|château d.eau|assainissement|eau potable'),
    ('Énergie', r'solaire|photovoltaique|photovoltaïque|electrification|électrification|energie|énergie|groupe electrogene|groupe électrogène'),
    ('Santé', r'sante|santé|medical|médical|hopital|hôpital|pharmaceutique|medicament|médicament|vaccin'),
    ('Transport', r'vehicule|véhicule|transport|ambulance|camion|moto'),
    ('Formation', r'formation|renforcement de capacite|renforcement de capacité'),
    ('Sécurité & Entretien', r'gardiennage|securite|sécurité|nettoyage|entretien des locaux'),
    ('Fournitures & Équipements', r'fourniture|acquisition|equipement|équipement|materiel|matériel|mobilier|livraison'),
]

# budget : "500 000 000 FCFA", "1,2 milliards", "250 millions XOF"...
RE_MONTANT = re.compile(
    r'(\d{1,3}(?:[ ., ]\d{3}){1,4}|\d+(?:[.,]\d+)?)\s*'
    r'(milliards?|millions?|fcfa|f\s*cfa|cfa|xof)',
    re.IGNORECASE,
)

SPAM_PATTERNS = (
    r'crypto|bitcoin|usdt|forex|trading|invest(ment)?|earn(ing)?s?\s|profit|'
    r'financial freedom|sign[- ]?up|bonus|jackpot|casino|loan offer|'
    r'gagn[ée]z? de l.argent|revenu passif|₹|\$\d+.{0,15}(week|day|jour|semaine)'
)


def parse_montant(txt):
    """Retourne le montant en FCFA ou None."""
    if not txt:
        return None
    best = None
    for m in RE_MONTANT.finditer(txt):
        raw, unite = m.group(1), m.group(2).lower()
        try:
            val = float(re.sub(r'[ ., ]', '', raw)) if re.search(r'[ ., ]\d{3}', raw) \
                else float(raw.replace(',', '.'))
        except ValueError:
            continue
        if unite.startswith('milliard'):
            val *= 1_000_000_000
        elif unite.startswith('million'):
            val *= 1_000_000
        # borne de vraisemblance : 100k a 500 milliards FCFA
        if 100_000 <= val <= 500_000_000_000:
            best = max(best or 0, val)
    return best


INFORMEL_CAT = {
    'informatique': 'Informatique', 'telephones-tablettes': 'Téléphonie',
    'electromenager': 'Électroménager', 'vehicules': 'Véhicules',
    'immobilier': 'Immobilier', 'alimentation': 'Alimentation',
    'jardinage-bricolage': 'Bricolage & Jardin',
    'decoration-linge-de-maison': 'Maison & Déco',
    'emploi-conseil-strategie': 'Services & Emploi',
    'vetements-homme': 'Mode & Vêtements', 'vetements-femme': 'Mode & Vêtements',
}

with engine.connect() as conn:
    stats = {}

    # ── 1. ANSD hors scope ────────────────────────────────────────────────────
    r = conn.execute(text("""
        UPDATE appels_offres SET statut = 'hors_scope'
        WHERE source = 'ANSD' AND statut IN ('actif', 'nouveau', 'historique')
    """))
    stats['ansd_hors_scope'] = r.rowcount

    # ── 2. Doublons (source + objet) : on garde le plus ancien ────────────────
    r = conn.execute(text("""
        UPDATE appels_offres SET statut = 'doublon'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY source, objet ORDER BY date_collecte ASC, id ASC
                ) AS rn
                FROM appels_offres
                WHERE statut = 'actif'
            ) t WHERE t.rn > 1
        )
    """))
    stats['doublons_marques'] = r.rowcount

    # ── 2b. Scories de scraping : liens de navigation, compteurs, pages legales
    r = conn.execute(text(r"""
        UPDATE appels_offres SET statut = 'hors_scope'
        WHERE statut = 'actif'
          AND (
            objet ~* '^\s*(appels? d.offres?|avis d.attribution|avis g[ée]n[ée]raux|plans? de passation|demandes? de renseignement)\s*\(?\s*\d*\s*\)?\s*$'
            OR objet ~* '^\s*(code des march[ée]s|arr[êe]t[ée]|d[ée]cret|loi n)'
            OR objet ~ '^\s*\d+\s*$'
            OR length(trim(objet)) < 15
          )
    """))
    stats['scories_hors_scope'] = r.rowcount

    # ── 3. Normalisation categories ───────────────────────────────────────────
    total_norm = 0
    for old, new in CAT_SYNONYMES.items():
        rr = conn.execute(
            text("UPDATE appels_offres SET categorie = :new WHERE categorie = :old"),
            {'new': new, 'old': old})
        total_norm += rr.rowcount
    stats['categories_normalisees'] = total_norm

    # ── 4. Recategorisation par mots-cles ─────────────────────────────────────
    total_recat = 0
    for cat, pattern in CAT_KEYWORDS:
        rr = conn.execute(text("""
            UPDATE appels_offres SET categorie = :cat
            WHERE (categorie IS NULL OR categorie IN ('Autre', ''))
              AND statut = 'actif'
              AND objet ~* :pat
        """), {'cat': cat, 'pat': pattern})
        total_recat += rr.rowcount
    stats['recategorises'] = total_recat

    # ── 5. Extraction budgets ─────────────────────────────────────────────────
    rows = conn.execute(text("""
        SELECT id, objet, donnees_brutes::text
        FROM appels_offres
        WHERE statut = 'actif' AND (budget_estime IS NULL OR budget_estime = 0)
    """)).fetchall()
    nb_budget = 0
    for _id, objet, brut in rows:
        montant = parse_montant(objet) or parse_montant(brut)
        if montant:
            conn.execute(text(
                "UPDATE appels_offres SET budget_estime = :m, devise = 'XOF' WHERE id = :i"),
                {'m': montant, 'i': _id})
            nb_budget += 1
    stats['budgets_extraits'] = nb_budget

    # ── 6. annonces_informel : categorie_std depuis notes_terrain ─────────────
    total_inf = 0
    for slug, cat in INFORMEL_CAT.items():
        rr = conn.execute(text("""
            UPDATE annonces_informel SET categorie_std = :cat
            WHERE (categorie_std IS NULL OR categorie_std = '')
              AND notes_terrain = :slug
        """), {'cat': cat, 'slug': slug})
        total_inf += rr.rowcount
    stats['informel_categorises'] = total_inf

    # ── 7. discussions_sociales : spam ────────────────────────────────────────
    r = conn.execute(text("""
        UPDATE discussions_sociales SET est_spam = TRUE
        WHERE (est_spam IS NULL OR est_spam = FALSE)
          AND texte_brut ~* :pat
    """), {'pat': SPAM_PATTERNS})
    stats['spam_marques'] = r.rowcount

    conn.commit()

    print("=== Nettoyage qualite ===")
    for k, v in stats.items():
        print(f"  {k:28} {v}")

    # ── verification finale ───────────────────────────────────────────────────
    r = conn.execute(text("""
        SELECT
            count(*) FILTER (WHERE statut = 'actif'),
            count(*) FILTER (WHERE statut = 'doublon'),
            count(*) FILTER (WHERE statut = 'hors_scope'),
            count(*) FILTER (WHERE statut = 'actif' AND budget_estime > 0),
            count(*) FILTER (WHERE statut = 'actif' AND categorie NOT IN ('Autre', '') AND categorie IS NOT NULL)
        FROM appels_offres
    """)).fetchone()
    print()
    print(f"AO actifs: {r[0]} | doublons: {r[1]} | hors_scope: {r[2]} | "
          f"avec budget: {r[3]} | categorises: {r[4]}")
    r = conn.execute(text("""
        SELECT count(*) FILTER (WHERE categorie_std IS NOT NULL AND categorie_std != ''), count(*)
        FROM annonces_informel
    """)).fetchone()
    print(f"Informel categorise: {r[0]}/{r[1]}")
    r = conn.execute(text(
        "SELECT count(*) FILTER (WHERE est_spam), count(*) FROM discussions_sociales")).fetchone()
    print(f"Discussions spam: {r[0]}/{r[1]}")
