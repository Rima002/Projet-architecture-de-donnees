-- =====================================================================
-- Entrepôt de données PubMed : schéma en étoile avec tables pont
-- SGBD : PostgreSQL (base entrepot_pubmed)
-- Grain de la table de faits : 1 ligne = 1 article (PMID)
-- Ce script est exécuté par chargement.py ; il recrée toutes les tables.
-- =====================================================================

DROP TABLE IF EXISTS pont_financement, pont_type_pub, pont_mot_cle, pont_mesh, pont_auteur,
    fait_publication, dim_financeur, dim_type_pub, dim_mot_cle, dim_qualificatif, dim_mesh,
    dim_auteur, dim_pays, dim_statut, dim_langue, dim_revue, dim_temps, dim_article CASCADE;

-- ------------------------------------------------------------ dimensions

-- Temps, grain jour. Hiérarchie : jour -> mois -> année.
-- Calendrier complet des années couvertes, plus des membres pour les dates
-- incomplètes (PubMed ne donne parfois que le mois, ou que l'année) :
--   id_temps = AAAAMMJJ   jour connu            (niveau 'Jour')
--   id_temps = AAAAMM00   jour inconnu          (niveau 'Mois')
--   id_temps = AAAA0000   mois et jour inconnus (niveau 'Année')
--   id_temps = 0          date inconnue
-- Ainsi, chaque article remonte correctement au mois et à l'année.
CREATE TABLE dim_temps (
    id_temps        INTEGER PRIMARY KEY,
    jour            DATE,                    -- niveau jour : date complète, NULL si jour inconnu
    mois            CHAR(7),                 -- niveau mois : 'AAAA-MM' (mois + année), NULL si inconnu
    annee           SMALLINT NOT NULL,       -- niveau année ; 0 si inconnue
    libelle_jour    VARCHAR(40) NOT NULL,    -- '14/03/2015', 'Mars 2015 (jour inconnu)'
    libelle_mois    VARCHAR(40) NOT NULL,    -- 'Mars 2015', '2015 (mois inconnu)'
    niveau_precision VARCHAR(10) NOT NULL    -- Jour, Mois, Année, Inconnue
);

-- Revue. Hiérarchie : revue -> pays -> continent (dénormalisée).
CREATE TABLE dim_revue (
    id_revue        INTEGER PRIMARY KEY,
    nlm_id          VARCHAR(20) NOT NULL UNIQUE,  -- clé naturelle NlmUniqueID
    titre           TEXT NOT NULL,
    abreviation     TEXT,
    issn            VARCHAR(9),
    pays            VARCHAR(60) NOT NULL,         -- 'Inconnu' si non déductible
    continent       VARCHAR(30) NOT NULL
);

CREATE TABLE dim_langue (
    id_langue       INTEGER PRIMARY KEY,
    code            VARCHAR(3) NOT NULL UNIQUE,   -- ISO 639-2 (eng, fre…)
    libelle         VARCHAR(40) NOT NULL
);

-- Dimension « fourre-tout » (junk) : indicateurs de faible cardinalité.
CREATE TABLE dim_statut (
    id_statut           INTEGER PRIMARY KEY,
    statut_citation     VARCHAR(30) NOT NULL,  -- MEDLINE, In-Process, Publisher…
    est_indexe_medline  VARCHAR(3)  NOT NULL,  -- Oui / Non
    modele_publication  VARCHAR(30) NOT NULL,  -- Print, Electronic…
    statut_publication  VARCHAR(30) NOT NULL,  -- ppublish, epublish…
    UNIQUE (statut_citation, modele_publication, statut_publication)
);

-- Pays (1er auteur et affiliations). Hiérarchie : pays -> continent.
CREATE TABLE dim_pays (
    id_pays         INTEGER PRIMARY KEY,
    pays            VARCHAR(60) NOT NULL UNIQUE,
    continent       VARCHAR(30) NOT NULL
);

-- Auteur. Clé naturelle : nom + prénom normalisés (accents, casse, points).
CREATE TABLE dim_auteur (
    id_auteur       INTEGER PRIMARY KEY,
    cle_naturelle   TEXT NOT NULL UNIQUE,
    nom             TEXT NOT NULL,
    prenom          TEXT,
    initiales       VARCHAR(20),
    orcid           VARCHAR(60),
    est_collectif   SMALLINT NOT NULL DEFAULT 0  -- 1 = groupe (CollectiveName)
);

-- Descripteur MeSH (vocabulaire contrôlé de la NLM).
CREATE TABLE dim_mesh (
    id_mesh         INTEGER PRIMARY KEY,
    ui              VARCHAR(12) NOT NULL UNIQUE,  -- ex. D011471
    libelle         TEXT NOT NULL,
    est_check_tag   SMALLINT NOT NULL DEFAULT 0   -- Humans, Male, Aged… (population)
);

CREATE TABLE dim_qualificatif (
    id_qualificatif INTEGER PRIMARY KEY,
    libelle         TEXT NOT NULL UNIQUE          -- '(aucun)' si pas de qualificatif
);

CREATE TABLE dim_mot_cle (
    id_mot_cle      INTEGER PRIMARY KEY,
    libelle         TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_type_pub (
    id_type_pub     INTEGER PRIMARY KEY,
    libelle         TEXT NOT NULL UNIQUE,
    categorie       VARCHAR(30) NOT NULL  -- Recherche originale, Synthèse, Essai clinique, Financement, Autre
);

-- Financeur. Hiérarchie : agence -> pays.
CREATE TABLE dim_financeur (
    id_financeur    INTEGER PRIMARY KEY,
    agence          TEXT NOT NULL,
    pays            VARCHAR(60) NOT NULL,
    UNIQUE (agence, pays)
);

-- Informations descriptives de l'article (texte, non agrégeable).
CREATE TABLE dim_article (
    id_article      INTEGER PRIMARY KEY,
    pmid            INTEGER NOT NULL UNIQUE,
    titre           TEXT NOT NULL,
    doi             TEXT,
    pmc             VARCHAR(20),
    fichier_source  VARCHAR(20) NOT NULL
);

-- ------------------------------------------------------------ table de faits

CREATE TABLE fait_publication (
    id_article              INTEGER PRIMARY KEY REFERENCES dim_article(id_article),
    id_temps_publication    INTEGER NOT NULL REFERENCES dim_temps(id_temps),
    id_temps_creation       INTEGER NOT NULL REFERENCES dim_temps(id_temps),
    id_revue                INTEGER NOT NULL REFERENCES dim_revue(id_revue),
    id_langue               INTEGER NOT NULL REFERENCES dim_langue(id_langue),
    id_statut               INTEGER NOT NULL REFERENCES dim_statut(id_statut),
    -- pays du 1er auteur : avant 2014, PubMed ne donne souvent que son affiliation
    id_pays_premier_auteur  INTEGER NOT NULL REFERENCES dim_pays(id_pays),
    -- mesures additives
    nb_publication          SMALLINT NOT NULL DEFAULT 1,
    nb_auteurs              INTEGER NOT NULL,
    nb_pays_affiliation     INTEGER NOT NULL,   -- collaboration internationale si > 1
    nb_mesh                 INTEGER NOT NULL,
    nb_mots_cles            INTEGER NOT NULL,
    nb_references_citees    INTEGER NOT NULL,   -- CommentsCorrections RefType='Cites'
    nb_financements         INTEGER NOT NULL,
    avec_resume             SMALLINT NOT NULL,  -- 0/1 (somme = nb d'articles avec résumé)
    -- mesures non additives (à moyenner) ; NULL si dates absentes
    delai_acceptation_jours INTEGER,            -- accepted - received
    delai_indexation_jours  INTEGER             -- DateCompleted - DateCreated
);

-- ------------------------------------------------------------ tables pont
-- poids = 1 / nombre de membres pour l'article : SUM(poids) = nb d'articles.

CREATE TABLE pont_auteur (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_auteur       INTEGER NOT NULL REFERENCES dim_auteur(id_auteur),
    rang            INTEGER NOT NULL,           -- 1 = premier auteur
    est_premier     SMALLINT NOT NULL,
    est_dernier     SMALLINT NOT NULL,          -- souvent le chef d'équipe
    id_pays         INTEGER NOT NULL REFERENCES dim_pays(id_pays),  -- pays d'affiliation
    poids           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id_article, rang)
);

CREATE TABLE pont_mesh (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_mesh         INTEGER NOT NULL REFERENCES dim_mesh(id_mesh),
    id_qualificatif INTEGER NOT NULL REFERENCES dim_qualificatif(id_qualificatif),
    sujet_majeur    SMALLINT NOT NULL,          -- MajorTopicYN = Y
    poids           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id_article, id_mesh, id_qualificatif)
);

CREATE TABLE pont_mot_cle (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_mot_cle      INTEGER NOT NULL REFERENCES dim_mot_cle(id_mot_cle),
    poids           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id_article, id_mot_cle)
);

CREATE TABLE pont_type_pub (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_type_pub     INTEGER NOT NULL REFERENCES dim_type_pub(id_type_pub),
    poids           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id_article, id_type_pub)
);

CREATE TABLE pont_financement (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_financeur    INTEGER NOT NULL REFERENCES dim_financeur(id_financeur),
    nb_subventions  INTEGER NOT NULL,           -- plusieurs GrantID d'une même agence
    poids           DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id_article, id_financeur)
);

-- ------------------------------------------------------------ index
CREATE INDEX ix_temps_mois  ON dim_temps(mois);
CREATE INDEX ix_temps_annee ON dim_temps(annee);
CREATE INDEX ix_fait_temps  ON fait_publication(id_temps_publication);
CREATE INDEX ix_fait_revue  ON fait_publication(id_revue);
CREATE INDEX ix_fait_pays   ON fait_publication(id_pays_premier_auteur);
CREATE INDEX ix_pa_auteur   ON pont_auteur(id_auteur);
CREATE INDEX ix_pa_pays     ON pont_auteur(id_pays);
CREATE INDEX ix_pm_mesh     ON pont_mesh(id_mesh);
CREATE INDEX ix_pk_mot_cle  ON pont_mot_cle(id_mot_cle);
CREATE INDEX ix_pt_type     ON pont_type_pub(id_type_pub);
CREATE INDEX ix_pf_fin      ON pont_financement(id_financeur);
