"""
Schéma SQLAlchemy — Intelligence Commerciale Afrique de l'Ouest
Supporte SQLite (MVP) et PostgreSQL (production) via config.yaml.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Produit(Base):
    """Produits collectés depuis les sources e-commerce et catalogues."""
    __tablename__ = "produits"

    id                = Column(String(36), primary_key=True, default=_uuid)
    source            = Column(String(100), nullable=False, index=True)
    date_collecte     = Column(DateTime, default=datetime.utcnow, index=True)
    categorie_1       = Column(String(100), index=True)
    categorie_2       = Column(String(100))
    marque            = Column(String(100), index=True)
    modele            = Column(String(200))
    description       = Column(Text)
    prix_actuel       = Column(Float)
    prix_barre        = Column(Float)
    promotion         = Column(Boolean, default=False)
    devise            = Column(String(10), default="XOF")
    pays              = Column(String(50), index=True)
    url_source        = Column(Text)
    disponibilite     = Column(String(50))
    donnees_brutes    = Column(Text)   # JSON raw pour audit

    def __repr__(self) -> str:
        return f"<Produit {self.marque} {self.modele} @ {self.prix_actuel} {self.devise}>"


class AppelOffre(Base):
    """Appels d'offres publics et institutionnels."""
    __tablename__ = "appels_offres"

    id               = Column(String(36), primary_key=True, default=_uuid)
    source           = Column(String(100), nullable=False, index=True)
    date_publication = Column(DateTime, index=True)
    date_limite      = Column(DateTime, index=True)
    jours_restants   = Column(Integer)
    reference        = Column(String(200), unique=True, index=True)
    objet            = Column(Text)
    entite           = Column(String(200))
    pays             = Column(String(50), index=True)
    ville            = Column(String(100))
    budget_estime    = Column(Float)
    devise           = Column(String(10), default="XOF")
    categorie        = Column(String(100), index=True)
    url_source       = Column(Text)
    score            = Column(Float)
    statut           = Column(String(30), default="nouveau", index=True)  # nouveau|traite|archive
    positionnement   = Column(String(50))
    detail_scores    = Column(Text)  # JSON des scores détaillés
    date_collecte    = Column(DateTime, default=datetime.utcnow)
    donnees_brutes   = Column(Text)

    def __repr__(self) -> str:
        return f"<AO {self.reference} — {self.objet[:60] if self.objet else ''}>"


class AnnoncInformel(Base):
    """Annonces issues de l'économie informelle (Marketplace, petites annonces)."""
    __tablename__ = "annonces_informel"

    id                  = Column(String(36), primary_key=True, default=_uuid)
    source              = Column(String(100), nullable=False, index=True)
    date_collecte       = Column(DateTime, default=datetime.utcnow, index=True)
    type                = Column(String(20), index=True)  # offre|demande
    produit             = Column(String(200), index=True)
    marque              = Column(String(100))
    quantite_disponible = Column(Integer)
    prix_unitaire       = Column(Float)
    devise              = Column(String(10), default="XOF")
    vendeur_zone        = Column(String(100), index=True)
    contact_disponible  = Column(Boolean, default=False)
    url_annonce         = Column(Text)
    notes_terrain       = Column(Text)
    categorie_detectee  = Column(String(100), index=True)
    donnees_brutes      = Column(Text)

    def __repr__(self) -> str:
        return f"<Informel {self.type} {self.produit} @ {self.vendeur_zone}>"


class Entreprise(Base):
    """Acteurs commerciaux identifiés (fournisseurs, distributeurs, etc.)."""
    __tablename__ = "entreprises"

    id              = Column(String(36), primary_key=True, default=_uuid)
    nom             = Column(String(200), nullable=False, index=True)
    secteur         = Column(String(100), index=True)
    pays            = Column(String(50), index=True)
    ville           = Column(String(100))
    type            = Column(String(50))   # fournisseur|distributeur|importateur|exportateur
    taille_estimee  = Column(String(30))   # petite|moyenne|grande|très grande
    source          = Column(String(100))
    date_collecte   = Column(DateTime, default=datetime.utcnow)
    contact         = Column(String(200))
    notes           = Column(Text)

    def __repr__(self) -> str:
        return f"<Entreprise {self.nom} ({self.type}, {self.pays})>"


class LogCollecte(Base):
    """Journal de toutes les collectes (pour audit et planification)."""
    __tablename__ = "log_collecte"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    date_debut     = Column(DateTime, default=datetime.utcnow, index=True)
    date_fin       = Column(DateTime)
    source_nom     = Column(String(100), index=True)
    source_type    = Column(String(30))   # ecommerce|ao|informel|macro
    statut         = Column(String(20))   # succes|erreur|partiel
    nb_items       = Column(Integer, default=0)
    erreur_detail  = Column(Text)

    def __repr__(self) -> str:
        return f"<Log {self.source_nom} {self.statut} — {self.nb_items} items>"


class DonneeMacro(Base):
    """Indicateurs économiques macro (World Bank, BCEAO, ANSD)."""
    __tablename__ = "donnees_macro"

    id            = Column(String(36), primary_key=True, default=_uuid)
    source        = Column(String(100), nullable=False, index=True)
    date_collecte = Column(DateTime, default=datetime.utcnow)
    pays          = Column(String(100), index=True)
    indicateur    = Column(String(200), index=True)
    code_wdi      = Column(String(50))   # code World Bank (ex: NY.GDP.MKTP.CD)
    annee         = Column(Integer, index=True)
    valeur        = Column(Float)
    unite         = Column(String(50))
    categorie     = Column(String(100))  # PIB, Inflation, Commerce, Emploi, etc.
    url_source    = Column(String(500))
    notes         = Column(Text)


class EtudeConjoncture(Base):
    """Rapports et études économiques scrapées (BCEAO, ANSD, IMF, BM)."""
    __tablename__ = "etudes_conjoncture"

    id            = Column(String(36), primary_key=True, default=_uuid)
    source        = Column(String(100), nullable=False)
    date_collecte = Column(DateTime, default=datetime.utcnow)
    date_publication = Column(DateTime)
    titre         = Column(String(500))
    resume        = Column(Text)
    pays          = Column(String(200))
    themes        = Column(String(500))   # JSON list
    url_source    = Column(String(500))
    url_pdf       = Column(String(500))
    langue        = Column(String(20), default="fr")


def get_engine(config: dict):
    """Crée le moteur SQLAlchemy selon la config (sqlite ou postgresql).
    DATABASE_URL env var a toujours priorité (GitHub Actions, Streamlit Cloud)."""
    import os
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url and env_url.startswith("postgres"):
        return create_engine(
            env_url, echo=False, poolclass=NullPool,
            connect_args={"connect_timeout": 10, "sslmode": "require"},
        )

    db_config = config.get("database", {})
    db_type = db_config.get("type", "sqlite")

    if db_type == "postgresql":
        url = db_config["postgresql_url"]
        return create_engine(url, echo=False, poolclass=NullPool)
    else:
        path = db_config.get("sqlite_path", "./data/intelligence.db")
        url = f"sqlite:///{path}"
        return create_engine(url, echo=False)


def init_db(config: dict) -> None:
    """Crée toutes les tables si elles n'existent pas."""
    engine = get_engine(config)
    Base.metadata.create_all(engine)


def get_session(config: dict) -> Session:
    """Retourne une session SQLAlchemy."""
    from sqlalchemy.orm import sessionmaker
    engine = get_engine(config)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
