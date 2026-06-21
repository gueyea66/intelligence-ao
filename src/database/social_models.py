"""
Modèle DB pour les discussions sociales collectées depuis Telegram/Facebook.
Table: discussions_sociales
"""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class DiscussionSociale(Base):
    __tablename__ = "discussions_sociales"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source
    plateforme = Column(String(50))       # "telegram", "facebook", "whatsapp"
    canal = Column(String(255))           # nom du groupe/canal
    canal_id = Column(String(255))        # ID technique du canal
    message_id = Column(String(255))      # ID du message (pour dédup)

    # Contenu brut
    texte_brut = Column(Text)
    langue = Column(String(10))           # "fr", "wo", "en", "ar"
    date_publication = Column(DateTime)
    date_collecte = Column(DateTime, default=datetime.utcnow)

    # Auteur (anonymisé)
    auteur_hash = Column(String(64))      # hash SHA256 de l'ID auteur

    # Analyse NLP
    sentiment = Column(String(20))        # "positif", "negatif", "neutre"
    score_sentiment = Column(Float)       # -1.0 à +1.0
    topics = Column(JSON)                 # ["commerce", "prix", "transport"]
    pain_points = Column(JSON)            # phrases de douleur détectées
    prix_mentionnes = Column(JSON)        # [{montant, devise, produit}]
    entites = Column(JSON)               # lieux, produits, personnes cités
    mots_cles = Column(JSON)             # TF-IDF top keywords

    # Classification
    type_message = Column(String(50))    # "annonce", "discussion", "plainte", "question", "info"
    categorie_produit = Column(String(100))  # catégorie détectée

    # Flags
    contient_prix = Column(Boolean, default=False)
    contient_contact = Column(Boolean, default=False)
    est_spam = Column(Boolean, default=False)
    traite = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "plateforme": self.plateforme,
            "canal": self.canal,
            "texte_brut": self.texte_brut,
            "langue": self.langue,
            "date_publication": self.date_publication.isoformat() if self.date_publication else None,
            "sentiment": self.sentiment,
            "score_sentiment": self.score_sentiment,
            "topics": self.topics,
            "pain_points": self.pain_points,
            "prix_mentionnes": self.prix_mentionnes,
            "type_message": self.type_message,
            "categorie_produit": self.categorie_produit,
        }


SQL_CREATE = """
CREATE TABLE IF NOT EXISTS discussions_sociales (
    id SERIAL PRIMARY KEY,
    plateforme VARCHAR(50),
    canal VARCHAR(255),
    canal_id VARCHAR(255),
    message_id VARCHAR(255),
    texte_brut TEXT,
    langue VARCHAR(10),
    date_publication TIMESTAMP,
    date_collecte TIMESTAMP DEFAULT NOW(),
    auteur_hash VARCHAR(64),
    sentiment VARCHAR(20),
    score_sentiment FLOAT,
    topics JSONB,
    pain_points JSONB,
    prix_mentionnes JSONB,
    entites JSONB,
    mots_cles JSONB,
    type_message VARCHAR(50),
    categorie_produit VARCHAR(100),
    contient_prix BOOLEAN DEFAULT FALSE,
    contient_contact BOOLEAN DEFAULT FALSE,
    est_spam BOOLEAN DEFAULT FALSE,
    traite BOOLEAN DEFAULT FALSE,
    UNIQUE(plateforme, canal_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_disc_date ON discussions_sociales(date_publication);
CREATE INDEX IF NOT EXISTS idx_disc_plateforme ON discussions_sociales(plateforme);
CREATE INDEX IF NOT EXISTS idx_disc_sentiment ON discussions_sociales(sentiment);
CREATE INDEX IF NOT EXISTS idx_disc_topics ON discussions_sociales USING GIN(topics);
"""
