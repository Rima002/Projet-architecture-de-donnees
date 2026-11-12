# Entrepôt de données PubMed — conception

Corpus : 4 036 fichiers XML PubMed (articles 2012-2016, principalement sur le cancer de la prostate).
Après nettoyage : **4 012 articles uniques**.

## Chaîne de traitement

| Étape | Script | Entrée → sortie |
|---|---|---|
| 2a. Nettoyage structurel | `nettoyage.py` | `pubmed doc/` → `pubmed_clean/` + `rapport_nettoyage.csv` |
| 2b. Nettoyage des valeurs | `nettoyage_valeurs.py` | `pubmed_clean/` → `pubmed_normalise/` + `rapport_valeurs.csv` |
| 6. Chargement (ETL) | `chargement.py` | `pubmed_normalise/` → `entrepot/entrepot_pubmed.db` + `entrepot/csv/` |
| 7. Exploitation | `analyse.py` | requêtes de `entrepot/requetes_analyse.sql` |

```
python nettoyage.py && python nettoyage_valeurs.py && python chargement.py && python analyse.py
```

---

## 1. Compréhension des données

Chaque fichier contient un `<PubmedArticleSet>` avec un ou plusieurs `<PubmedArticle>`, composés de :

- `MedlineCitation` : PMID, dates de création et d'indexation, article (revue, titre, résumé, auteurs, langue, types, financements), MeSH, mots-clés ;
- `PubmedData` : historique (reçu, accepté, en ligne…), statut de publication, identifiants (DOI, PMC).

| Champ | Taux de remplissage | Cardinalité par article |
|---|---|---|
| Titre, revue | 100 % | 1 |
| Résumé | 99 % | 1 |
| Auteurs | 99 % | 7,4 en moyenne (jusqu'à 180) |
| Affiliations | 97 % | 0 à n par auteur |
| MeSH | 66 % | 9 en moyenne |
| Mots-clés | 54 % | n |
| Financements | 22 % | n |

Constat principal : plusieurs relations sont de type **plusieurs-à-plusieurs** (auteurs, MeSH, mots-clés, types, financeurs). Ce constat guide le choix du modèle.

## 2. Nettoyage

**Structure** (`rapport_nettoyage.csv`) :

| Résultat | Nombre |
|---|---|
| Fichiers corrigés | 115 |
| Fichiers supprimés (PMID absent) | 23 |
| Fichiers supprimés (doublons strictement identiques) | 6 |
| Articles en double retirés au total | 31 |
| Articles avec des fragments collés au mauvais niveau, replacés | 5 |

**Valeurs** (`rapport_valeurs.csv`, 8 règles R1 à R8) :
- harmonisation de la casse (langue, types de publication, mots-clés) ;
- format des dates ;
- pays de la revue déduit des autres articles de la même revue, puis harmonisé ;
- extraction du pays des affiliations (98,5 % trouvés) ;
- suppression des adresses e-mail ;
- libellés MeSH vérifiés par leur identifiant UI.

Les 200 articles au statut `Publisher` (notices de l'éditeur, non encore indexées par la NLM) expliquent la plupart des anomalies de valeurs.

## 3. Choix du modèle

### Questions d'analyse

1. Évolution du nombre de publications dans le temps.
2. Revues et pays les plus productifs.
3. Sujets (MeSH) étudiés et leur évolution.
4. Auteurs les plus actifs, et leur rôle (premier ou dernier auteur).
5. Poids des financeurs (NIH…).
6. Collaboration internationale.
7. Délais éditoriaux (réception → acceptation, création → indexation).

### Comparaison des modèles

| Modèle | Avantage | Inconvénient pour ce corpus |
|---|---|---|
| Étoile simple | Requêtes simples et rapides | Impossible de représenter « un article a n auteurs » sans dupliquer les faits, ce qui fausse les comptages |
| Flocon | Hiérarchies normalisées | Jointures plus nombreuses ; ne résout pas le plusieurs-à-plusieurs |
| Constellation | Plusieurs faits partagent des dimensions | Plus lourd ; un second fait n'est justifié que pour un autre grain |
| **Étoile + tables pont** (retenu) | Un fait par article, comptages justes ; relations n-n dans des ponts pondérés | Il faut gérer le double comptage (`COUNT(DISTINCT)` ou poids) |

**Choix retenu** : schéma en étoile centré sur la publication, avec **5 tables pont**. Les hiérarchies (revue → pays → continent, temps) sont dénormalisées dans les dimensions, dans l'esprit de l'étoile.

## 4. Concepts multidimensionnels

**Fait** : la publication d'un article. **Grain** : 1 ligne = 1 article (PMID).

### Mesures

| Mesure | Type | Calcul |
|---|---|---|
| `nb_publication` | additive | 1 |
| `nb_auteurs`, `nb_mesh`, `nb_mots_cles`, `nb_financements` | additives | comptage dans l'article |
| `nb_references_citees` | additive | `CommentsCorrections` de type `Cites` |
| `nb_pays_affiliation` | semi-additive | nombre de pays distincts des auteurs (> 1 = collaboration internationale) |
| `avec_resume` | additive (0/1) | présence d'un résumé |
| `delai_acceptation_jours` | non additive (moyenne) | date d'acceptation − date de réception |
| `delai_indexation_jours` | non additive (moyenne) | `DateCompleted` − `DateCreated` |

### Dimensions et hiérarchies

| Dimension | Clé naturelle | Hiérarchie / attributs | Liaison |
|---|---|---|---|
| Temps (2 rôles : publication, création) | AAAAMM | mois → trimestre → semestre → année ; membre « mois inconnu » (800 articles) | directe |
| Revue | NlmUniqueID | revue → pays → continent | directe |
| Langue | code ISO 639-2 | code, libellé | directe |
| Statut (dimension *junk*) | combinaison | statut de citation, indexé MEDLINE, modèle de publication, statut de publication | directe |
| Pays | nom harmonisé | pays → continent | directe (pays du 1er auteur) + pont auteur |
| Auteur | nom + prénom normalisés | nom, prénom, initiales, ORCID, collectif | pont (rang, 1er, dernier, pays d'affiliation, poids) |
| MeSH + Qualificatif | UI MeSH | descripteur, « check tag » (population) ; qualificatif | pont (sujet majeur, poids) |
| Mot-clé | libellé harmonisé | – | pont |
| Type de publication | libellé | type → catégorie | pont |
| Financeur | agence + pays | agence → pays | pont (nb de subventions) |

Une dimension **Article** (PMID, titre, DOI, PMC) garde les informations descriptives, qui ne sont pas agrégeables.

**Membres inconnus** : `Inconnu` (id 0) pour le pays, et « mois inconnu » pour le temps. Aucun fait n'est perdu à cause d'une valeur manquante.

**Pondération des ponts** : `poids` = 1 / (nombre de membres liés à l'article). `SUM(poids)` redonne le nombre exact d'articles. C'est vérifié automatiquement au chargement.

## 5. Modèle multidimensionnel

```
                         DIM_TEMPS (x2 rôles)        DIM_LANGUE     DIM_STATUT
                                   \                    |            /
   DIM_REVUE ─────────────────── FAIT_PUBLICATION ─────────────────── DIM_PAYS
                                 /  |    |    |   \            (pays 1er auteur)
                     DIM_ARTICLE    |    |    |    \
                                    |    |    |     \
        PONT_AUTEUR ────────────────┘    |    |      └── PONT_FINANCEMENT ── DIM_FINANCEUR
        │  rang, 1er, dernier, poids     |    |
        ├── DIM_AUTEUR                   |    └── PONT_TYPE_PUB ── DIM_TYPE_PUB
        └── DIM_PAYS (affiliation)       |
                                         ├── PONT_MESH ── DIM_MESH
                                         │   sujet_majeur └─ DIM_QUALIFICATIF
                                         └── PONT_MOT_CLE ── DIM_MOT_CLE
```

DDL complet : `entrepot/schema.sql` (SQL standard ; testé sous SQLite, compatible PostgreSQL). Les clés de substitution sont des entiers ; les clés naturelles sont conservées en `UNIQUE`.

## 6. Chargement

1. **Extraction** : lecture de chaque article de `pubmed_normalise/`.
2. **Transformation** :
   - attribution des clés de substitution ;
   - calcul des mesures ;
   - normalisation des noms d'auteurs (sans accents, majuscules ni points) ;
   - choix du pays d'affiliation de chaque auteur (première affiliation qui a un pays).
3. **Chargement** dans cet ordre : dimensions → faits → ponts, avec les clés étrangères actives.
4. **Contrôles** (tous OK) :
   - 4 012 lignes de faits, une par article ;
   - PMID uniques ;
   - intégrité référentielle ;
   - `SUM(nb_auteurs)` = nombre de lignes de `pont_auteur` ;
   - somme des poids de chaque pont = nombre d'articles concernés.

| Table | Lignes | Table | Lignes |
|---|---|---|---|
| fait_publication | 4 012 | pont_auteur | 29 639 |
| dim_auteur | 23 502 | pont_mesh | 44 824 |
| dim_mesh | 3 951 | pont_mot_cle | 12 830 |
| dim_mot_cle | 6 612 | pont_type_pub | 7 955 |
| dim_revue | 1 075 | pont_financement | 1 387 |
| dim_pays | 88 | dim_temps | 49 |

## Limites et biais à connaître

- **Affiliations avant 2014** : PubMed ne donne souvent que l'affiliation du premier auteur (46 % des auteurs sans pays, mais seulement 5 % des premiers auteurs). L'analyse par pays utilise donc le **pays du premier auteur**. La hausse apparente de la collaboration internationale (0,1 % en 2013 → 24 % en 2016) est en grande partie un **artefact** de cette règle.
- **MeSH incomplets en 2015-2016** : les articles `In-Process` et `In-Data-Review` ne sont pas encore indexés. Les comparaisons de sujets entre années sont donc biaisées.
- **Identité des auteurs** : la règle « nom + prénom » limite les fusions abusives, contrairement à « nom + initiales », mais elle reste imparfaite. Deux homonymes complets sont fusionnés, et une même personne écrite de deux façons compte double (« Markus Graefen » / « M Graefen »).
- **Hiérarchie MeSH** : l'arbre des descripteurs n'est pas dans les fichiers XML. Il pourrait être ajouté à partir du fichier MeSH de la NLM, en le reliant par l'UI.
