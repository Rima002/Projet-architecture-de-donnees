-- =====================================================================
-- Entrepôt de données PubMed : schéma en étoile avec tables pont
-- Grain de la table de faits : 1 ligne = 1 article (PMID)
-- SQL standard (testé sous SQLite, compatible PostgreSQL)
-- =====================================================================

DROP TABLE IF EXISTS pont_financement;
DROP TABLE IF EXISTS pont_type_pub;
DROP TABLE IF EXISTS pont_mot_cle;
DROP TABLE IF EXISTS pont_mesh;
DROP TABLE IF EXISTS pont_auteur;
DROP TABLE IF EXISTS fait_publication;
DROP TABLE IF EXISTS dim_financeur;
DROP TABLE IF EXISTS dim_type_pub;
DROP TABLE IF EXISTS dim_mot_cle;
DROP TABLE IF EXISTS dim_qualificatif;
DROP TABLE IF EXISTS dim_mesh;
DROP TABLE IF EXISTS dim_auteur;
DROP TABLE IF EXISTS dim_pays;
DROP TABLE IF EXISTS dim_statut;
DROP TABLE IF EXISTS dim_langue;
DROP TABLE IF EXISTS dim_revue;
DROP TABLE IF EXISTS dim_temps;
DROP TABLE IF EXISTS dim_article;

-- ------------------------------------------------------------ dimensions

-- Temps, grain mois. Hiérarchie : mois -> trimestre -> semestre -> année.
-- id_temps = AAAAMM ; AAAA00 = mois inconnu (seule l'année est connue).
CREATE TABLE dim_temps (
    id_temps        INTEGER PRIMARY KEY,
    annee           INTEGER NOT NULL,
    semestre        INTEGER,            -- 1, 2 ; NULL si mois inconnu
    trimestre       INTEGER,            -- 1..4
    mois            INTEGER,            -- 1..12
    libelle_mois    VARCHAR(20) NOT NULL,
    libelle_periode VARCHAR(20) NOT NULL -- ex. '2015-T3', '2015 (mois inconnu)'
);

-- Revue. Hiérarchie : revue -> pays -> continent (dénormalisée).
CREATE TABLE dim_revue (
    id_revue        INTEGER PRIMARY KEY,
    nlm_id          VARCHAR(20) NOT NULL UNIQUE,  -- clé naturelle NlmUniqueID
    titre           VARCHAR(400) NOT NULL,
    abreviation     VARCHAR(200),
    issn            VARCHAR(9),
    pays            VARCHAR(60) NOT NULL,         -- 'Inconnu' si non déductible
    continent       VARCHAR(30) NOT NULL
);

CREATE TABLE dim_langue (
    id_langue       INTEGER PRIMARY KEY,
    code            VARCHAR(3) NOT NULL UNIQUE,   -- ISO 639-2 (eng, fre…)
    libelle         VARCHAR(40) NOT NULL
);

-- Dimension « fourre-tout » (junk) : 3 indicateurs de faible cardinalité.
CREATE TABLE dim_statut (
    id_statut           INTEGER PRIMARY KEY,
    statut_citation     VARCHAR(30) NOT NULL,  -- MEDLINE, In-Process, Publisher…
    est_indexe_medline  VARCHAR(3)  NOT NULL,  -- Oui / Non
    modele_publication  VARCHAR(30) NOT NULL,  -- Print, Electronic…
    statut_publication  VARCHAR(30) NOT NULL,  -- ppublish, epublish…
    UNIQUE (statut_citation, modele_publication, statut_publication)
);

-- Pays (affiliation des auteurs). Hiérarchie : pays -> continent.
CREATE TABLE dim_pays (
    id_pays         INTEGER PRIMARY KEY,
    pays            VARCHAR(60) NOT NULL UNIQUE,
    continent       VARCHAR(30) NOT NULL
);

-- Auteur. Clé naturelle : nom + prénom normalisés (accents, casse, points).
CREATE TABLE dim_auteur (
    id_auteur       INTEGER PRIMARY KEY,
    cle_naturelle   VARCHAR(300) NOT NULL UNIQUE,
    nom             VARCHAR(150) NOT NULL,
    prenom          VARCHAR(150),
    initiales       VARCHAR(20),
    orcid           VARCHAR(60),
    est_collectif   INTEGER NOT NULL DEFAULT 0  -- 1 = groupe (CollectiveName)
);

-- Descripteur MeSH (vocabulaire contrôlé de la NLM).
CREATE TABLE dim_mesh (
    id_mesh         INTEGER PRIMARY KEY,
    ui              VARCHAR(12) NOT NULL UNIQUE,  -- ex. D011471
    libelle         VARCHAR(200) NOT NULL,
    est_check_tag   INTEGER NOT NULL DEFAULT 0    -- Humans, Male, Aged… (population)
);

CREATE TABLE dim_qualificatif (
    id_qualificatif INTEGER PRIMARY KEY,
    libelle         VARCHAR(100) NOT NULL UNIQUE  -- '(aucun)' si pas de qualificatif
);

CREATE TABLE dim_mot_cle (
    id_mot_cle      INTEGER PRIMARY KEY,
    libelle         VARCHAR(300) NOT NULL UNIQUE
);

CREATE TABLE dim_type_pub (
    id_type_pub     INTEGER PRIMARY KEY,
    libelle         VARCHAR(100) NOT NULL UNIQUE,
    categorie       VARCHAR(30) NOT NULL  -- Recherche originale, Synthèse, Essai clinique, Financement, Autre
);

-- Financeur. Hiérarchie : agence -> pays.
CREATE TABLE dim_financeur (
    id_financeur    INTEGER PRIMARY KEY,
    agence          VARCHAR(200) NOT NULL,
    pays            VARCHAR(60) NOT NULL,
    UNIQUE (agence, pays)
);

-- Informations descriptives de l'article (texte, non agrégeable).
CREATE TABLE dim_article (
    id_article      INTEGER PRIMARY KEY,
    pmid            INTEGER NOT NULL UNIQUE,
    titre           TEXT NOT NULL,
    doi             VARCHAR(200),
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
    nb_publication          INTEGER NOT NULL DEFAULT 1,
    nb_auteurs              INTEGER NOT NULL,
    nb_pays_affiliation     INTEGER NOT NULL,   -- collaboration internationale si > 1
    nb_mesh                 INTEGER NOT NULL,
    nb_mots_cles            INTEGER NOT NULL,
    nb_references_citees    INTEGER NOT NULL,   -- CommentsCorrections RefType='Cites'
    nb_financements         INTEGER NOT NULL,
    avec_resume             INTEGER NOT NULL,   -- 0/1 (somme = nb d'articles avec résumé)
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
    est_premier     INTEGER NOT NULL,
    est_dernier     INTEGER NOT NULL,           -- souvent le chef d'équipe
    id_pays         INTEGER NOT NULL REFERENCES dim_pays(id_pays),  -- pays d'affiliation
    poids           REAL NOT NULL,
    PRIMARY KEY (id_article, rang)
);

CREATE TABLE pont_mesh (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_mesh         INTEGER NOT NULL REFERENCES dim_mesh(id_mesh),
    id_qualificatif INTEGER NOT NULL REFERENCES dim_qualificatif(id_qualificatif),
    sujet_majeur    INTEGER NOT NULL,           -- MajorTopicYN = Y
    poids           REAL NOT NULL,
    PRIMARY KEY (id_article, id_mesh, id_qualificatif)
);

CREATE TABLE pont_mot_cle (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_mot_cle      INTEGER NOT NULL REFERENCES dim_mot_cle(id_mot_cle),
    poids           REAL NOT NULL,
    PRIMARY KEY (id_article, id_mot_cle)
);

CREATE TABLE pont_type_pub (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_type_pub     INTEGER NOT NULL REFERENCES dim_type_pub(id_type_pub),
    poids           REAL NOT NULL,
    PRIMARY KEY (id_article, id_type_pub)
);

CREATE TABLE pont_financement (
    id_article      INTEGER NOT NULL REFERENCES fait_publication(id_article),
    id_financeur    INTEGER NOT NULL REFERENCES dim_financeur(id_financeur),
    nb_subventions  INTEGER NOT NULL,           -- plusieurs GrantID d'une même agence
    poids           REAL NOT NULL,
    PRIMARY KEY (id_article, id_financeur)
);

-- ------------------------------------------------------------ index
CREATE INDEX ix_fait_temps  ON fait_publication(id_temps_publication);
CREATE INDEX ix_fait_revue  ON fait_publication(id_revue);
CREATE INDEX ix_fait_pays   ON fait_publication(id_pays_premier_auteur);
CREATE INDEX ix_pa_auteur   ON pont_auteur(id_auteur);
CREATE INDEX ix_pa_pays     ON pont_auteur(id_pays);
CREATE INDEX ix_pm_mesh     ON pont_mesh(id_mesh);
CREATE INDEX ix_pk_mot_cle  ON pont_mot_cle(id_mot_cle);
CREATE INDEX ix_pt_type     ON pont_type_pub(id_type_pub);
CREATE INDEX ix_pf_fin      ON pont_financement(id_financeur);
