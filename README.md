# Entrepôt de données PubMed

Projet du module *Architecture de données modernes* : construire un entrepôt de données à partir de 4 036 fichiers XML PubMed (articles publiés entre 2012 et 2016, principalement sur le cancer de la prostate).

Le projet suit six étapes, plus une étape d'exploitation :

1. Compréhension des données d'entrée
2. Nettoyage des données
3. Choix du modèle multidimensionnel
4. Définition des concepts multidimensionnels
5. Définition du modèle multidimensionnel
6. Chargement des données
7. Exploitation (requêtes SQL et guide Power BI)

La conception et sa justification sont détaillées dans [conception_entrepot.md](conception_entrepot.md).

## Résultat

L'entrepôt contient **4 012 articles uniques**. Il suit un schéma en étoile avec tables pont : une ligne de faits par article, et cinq tables pont pour les relations plusieurs-à-plusieurs (auteurs, MeSH, mots-clés, types de publication, financeurs).

```
DIM_TEMPS (2 rôles)   DIM_REVUE   DIM_LANGUE   DIM_STATUT   DIM_PAYS   DIM_ARTICLE
                 \        |           |            |          |        /
                  └────────────── FAIT_PUBLICATION ───────────────────┘
                     /          |            |            |          \
           PONT_AUTEUR     PONT_MESH    PONT_MOT_CLE  PONT_TYPE_PUB  PONT_FINANCEMENT
            |      |        |       |        |             |              |
    DIM_AUTEUR  DIM_PAYS  DIM_MESH  DIM_     DIM_MOT_CLE   DIM_TYPE_PUB   DIM_FINANCEUR
                                    QUALIFICATIF
```

| Bilan du nettoyage (fichiers source) | Nombre |
|---|---|
| Fichiers déjà corrects | 3 892 |
| Fichiers corrigés | 115 |
| Fichiers supprimés (PMID absent) | 23 |
| Fichiers supprimés (doublons) | 6 |

## Exécution

Prérequis : Python 3.9 ou plus récent (testé avec Python 3.12). Aucune bibliothèque à installer.

Depuis la racine du dépôt :

```
python nettoyage.py
python nettoyage_valeurs.py
python chargement.py
python analyse.py
```

| Script | Rôle | Produit |
|---|---|---|
| `nettoyage.py` | Répare la structure XML, retire les articles sans PMID et les doublons | `pubmed_clean/`, `rapport_nettoyage.csv` |
| `nettoyage_valeurs.py` | Harmonise les valeurs (casse, dates, pays), extrait le pays des affiliations, retire les e-mails | `pubmed_normalise/`, `rapport_valeurs.csv` |
| `chargement.py` | Crée la base, charge les dimensions, les faits et les ponts, puis lance les contrôles | `entrepot/entrepot_pubmed.db`, `entrepot/csv/` |
| `analyse.py` | Exécute les 12 requêtes d'analyse (`python analyse.py 5` pour une seule) | Affichage dans le terminal |

Les fichiers source ne sont jamais modifiés. `pubmed_clean/` et `pubmed_normalise/` ne sont pas versionnés, car les deux premiers scripts les régénèrent.

## Organisation du dépôt

```
pubmed doc/                 Fichiers XML source
nettoyage.py                Étape 2 : structure
nettoyage_valeurs.py        Étape 2 : valeurs
chargement.py               Étape 6 : ETL
analyse.py                  Exécution des requêtes d'analyse
conception_entrepot.md      Étapes 1 à 6 : conception et justifications
rapport_nettoyage.csv       Traitement appliqué à chaque fichier
rapport_valeurs.csv         Journal des valeurs modifiées (avant / après)
entrepot/
    schema.sql              Schéma de l'entrepôt
    requetes_analyse.sql    12 requêtes d'analyse
    entrepot_pubmed.db      Base SQLite chargée
    csv/                    Export de chaque table
    anomalies_chargement.txt
powerbi/
    guide_power_bi.md       Construction du rapport, pas à pas
    import_power_query.m    Import des tables dans Power BI
    mesures.dax             Mesures DAX
```

La base SQLite s'ouvre sans serveur. Le schéma est écrit en SQL standard, et les CSV permettent de charger les données dans un autre outil.

## Limites

- **Affiliations** : avant 2014, PubMed ne donne souvent que l'affiliation du premier auteur. Les analyses par pays utilisent donc le pays du premier auteur, et la hausse apparente de la collaboration internationale est en grande partie un artefact.
- **MeSH** : beaucoup d'articles de 2015-2016 ne sont pas encore indexés, ce qui biaise les comparaisons de sujets entre années.
- **Auteurs** : ils sont identifiés par leur nom et leur prénom normalisés. Les homonymes sont donc fusionnés, et une même personne écrite de deux façons compte double.
- **Power BI** : le guide et les scripts n'ont pas encore été testés dans Power BI Desktop.

## Données

Les données proviennent de [PubMed](https://pubmed.ncbi.nlm.nih.gov/) (National Library of Medicine, États-Unis). Les résumés restent soumis aux droits de leurs éditeurs.
