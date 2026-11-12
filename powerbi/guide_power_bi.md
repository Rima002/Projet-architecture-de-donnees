# Exploration de l'entrepôt PubMed avec Power BI

Fichiers de ce dossier :
- `import_power_query.m` : script d'import des 18 tables (étape 2) ;
- `mesures.dax` : les mesures à créer (étape 4).

Prérequis : avoir exécuté `python chargement.py`, qui produit les CSV dans `entrepot/csv/`.

---

## Étape 1 — Installer Power BI Desktop

Power BI Desktop est gratuit. Installez-le depuis le **Microsoft Store** : cherchez « Power BI Desktop ». Les mises à jour seront alors automatiques.

Au premier lancement, aucune connexion n'est nécessaire : fermez la fenêtre qui demande de se connecter.

## Étape 2 — Importer les tables (Power Query)

1. **Accueil > Transformer les données**. L'éditeur Power Query s'ouvre.
2. **Créer le paramètre** : Gérer les paramètres > Nouveau.
   - Nom : `DossierCSV` ;
   - Type : Texte ;
   - Valeur : le chemin du dossier `entrepot\csv\`, **avec le `\` final** (voir le bloc 1 du fichier `.m`).
3. **Créer la fonction** : Nouvelle source > Requête vide > Éditeur avancé. Collez le **bloc 2** et renommez la requête `fnChargerCSV`.
4. **Créer les 20 requêtes** (bloc 3) : pour chacune, Nouvelle source > Requête vide, tapez la formule, par exemple `= fnChargerCSV("fait_publication")`, puis renommez la requête.
   - `dim_temps` et `dim_pays` sont chargées **deux fois**, sous deux noms différents. C'est voulu : ce sont des **dimensions à rôles multiples** (expliqué à l'étape 3).
5. **Fermer et appliquer**.

> La fonction lit les nombres au format anglais (`0.25`), quelle que soit la langue de Windows. Sans elle, avec un Windows en français, les poids `0.25` seraient lus comme `25` ou comme du texte.

**Variante sans script** : Obtenir des données > Texte/CSV, une table à la fois. Dans la fenêtre d'aperçu, choisissez *Délimiteur : point-virgule*. Ensuite, dans Power Query : Fichier > Options > *Paramètres régionaux* = Anglais (États-Unis).

## Étape 3 — Créer les relations (vue Modèle)

Power BI peut détecter certaines relations tout seul. **Supprimez-les toutes** (vue Modèle > Gérer les relations), puis créez exactement celles-ci :

| De (côté plusieurs *) | Vers (côté 1) | Direction du filtre |
|---|---|---|
| fait_publication[id_temps_publication] | dim_temps[id_temps] | Unique |
| fait_publication[id_temps_creation] | dim_temps_creation[id_temps] | Unique |
| fait_publication[id_revue] | dim_revue[id_revue] | Unique |
| fait_publication[id_langue] | dim_langue[id_langue] | Unique |
| fait_publication[id_statut] | dim_statut[id_statut] | Unique |
| fait_publication[id_pays_premier_auteur] | dim_pays[id_pays] | Unique |
| fait_publication[id_article] | dim_article[id_article] | **Les deux** (relation 1-1) |
| pont_auteur[id_article] | fait_publication[id_article] | **Les deux** |
| pont_auteur[id_auteur] | dim_auteur[id_auteur] | Unique |
| pont_auteur[id_pays] | dim_pays_affiliation[id_pays] | Unique |
| pont_mesh[id_article] | fait_publication[id_article] | **Les deux** |
| pont_mesh[id_mesh] | dim_mesh[id_mesh] | Unique |
| pont_mesh[id_qualificatif] | dim_qualificatif[id_qualificatif] | Unique |
| pont_mot_cle[id_article] | fait_publication[id_article] | **Les deux** |
| pont_mot_cle[id_mot_cle] | dim_mot_cle[id_mot_cle] | Unique |
| pont_type_pub[id_article] | fait_publication[id_article] | **Les deux** |
| pont_type_pub[id_type_pub] | dim_type_pub[id_type_pub] | Unique |
| pont_financement[id_article] | fait_publication[id_article] | **Les deux** |
| pont_financement[id_financeur] | dim_financeur[id_financeur] | Unique |

**Pourquoi « Les deux » entre un pont et le fait ?** Quand on choisit un auteur, le filtre part de `dim_auteur`, passe par `pont_auteur`, puis doit **remonter** jusqu'à `fait_publication`. Il traverse donc la relation dans le sens inverse, ce qui demande un filtrage dans les deux sens. Power BI peut afficher un avertissement à ce moment-là : c'est normal pour ce modèle.

**Pourquoi deux tables Temps et deux tables Pays ?** Le fait est lié deux fois au temps (date de publication et date de création). Le pays aussi est utilisé deux fois (pays du 1er auteur dans le fait, pays d'affiliation dans le pont). Power BI n'accepte qu'**un seul chemin actif** entre deux tables : on duplique donc la dimension pour chaque rôle.

Le schéma obtenu dans la vue Modèle est celui de `conception_entrepot.md`, section 5. Faites-en une capture d'écran pour le rapport.

## Étape 4 — Préparer le modèle

1. **Mesures** : Accueil > Entrer des données > nommez la table `Mesures` > Charger. Puis, pour chaque mesure de `mesures.dax` : clic droit sur `Mesures` > Nouvelle mesure > collez.
2. **Tri des mois** : sélectionnez `dim_temps[libelle_mois]`, puis Outils de colonne > *Trier par colonne* > `mois`. Faites de même pour `dim_temps_creation`.
3. **Hiérarchie du temps** : dans `dim_temps`, clic droit sur `annee` > *Créer une hiérarchie*, puis ajoutez `trimestre` et `libelle_mois`.
4. **Cartes** : sélectionnez `dim_pays[pays]`, puis Outils de colonne > *Catégorie de données* = **Pays/Région**. Faites de même pour `dim_pays_affiliation[pays]` et `dim_revue[pays]`.
5. **Masquer les clés** : en vue Modèle, masquez toutes les colonnes `id_*` et `poids`, pour que seuls les libellés et les mesures apparaissent dans les visuels.
6. **Format** : les mesures `%…` en Pourcentage ; les délais et les moyennes avec 1 décimale.

## Étape 5 — Construire le rapport

Chaque page répond à une question d'analyse de la conception. Les chiffres attendus sont ceux de `python analyse.py`, ce qui permet de vérifier que le modèle est correct.

### Page 1 — Vue d'ensemble
- **Cartes** : `Publications` (4 012), `Revues` (1 075), `Auteurs distincts`, `Délai acceptation (jours)` (≈ 107).
- **Histogramme** : axe = hiérarchie Temps, valeur = `Publications`. Utilisez l'**exploration** (flèches du visuel) pour passer de l'année au trimestre puis au mois. Ça montre le *drill-down*.
- **Segments** : `dim_langue[libelle]`, `dim_statut[statut_citation]`, `dim_type_pub[categorie]`.

### Page 2 — Géographie
- **Carte** (ou carte choroplèthe) : emplacement = `dim_pays[pays]`, taille = `Publications`. Filtre du visuel : pays ≠ « Inconnu ».
- **Matrice** : lignes = `dim_pays[continent]` puis `dim_pays[pays]`, colonnes = `dim_temps[annee]`, valeur = `Publications`. C'est le tableau croisé avec *roll-up* (pays → continent).
- **Courbe** : `% collaboration internationale` par année. Ajoutez une zone de texte pour expliquer le biais d'avant 2014 (voir conception, section « Limites »).

### Page 3 — Revues
- **Barres** : top 10 de `dim_revue[titre]` par `Publications` (filtre du visuel : *N premiers* = 10).
- **Nuage de points** : un point par revue, X = `Publications`, Y = `Délai acceptation (jours)`. Le nuage montre si les grosses revues sont plus lentes.
- **Segment** : `dim_revue[pays]`.

### Page 4 — Thématiques (MeSH et mots-clés)
- **Treemap** : `dim_mesh[libelle]` par `Publications (sujet majeur)`. Filtre de page : `dim_mesh[est_check_tag]` = 0, pour exclure Humans, Male, etc.
- **Barres** : `dim_qualificatif[libelle]` par `Publications` (angle d'étude : génétique, traitement…).
- **Anneau** : population étudiée. `dim_mesh[libelle]` filtré sur Humans, Animals et Mice, par `Publications`.
- **Interaction à montrer** : cliquez sur un sujet MeSH, et toutes les autres pages se filtrent, y compris les revues et les pays. C'est l'effet des tables pont avec le filtre « Les deux ».

### Page 5 — Auteurs
- **Tableau** : `dim_auteur[nom]`, `dim_auteur[prenom]`, `Publications`, `Articles en 1er auteur`, `Articles en dernier auteur`, `Publications pondérées (auteurs)`. Triez par `Publications`.
- **Barres** : `dim_pays_affiliation[pays]` par `Auteurs distincts`.
- Vérification à mettre dans le rapport : la **somme** de `Publications` dans le tableau dépasse 4 012, parce qu'un article a plusieurs auteurs. Celle de `Publications pondérées` vaut exactement 4 012.

### Page 6 — Financements
- **Barres** : `dim_financeur[agence]` par `Publications`.
- **Carte** : `% financées`.
- **Matrice** : `dim_financeur[pays]` × `dim_temps[annee]`.

## Étape 6 — Vérifier les chiffres

| Vérification | Valeur attendue |
|---|---|
| `Publications` sans filtre | 4 012 |
| `Publications` pour 2013 / 2015 | 1 763 / 1 486 |
| Top revue | PloS one : 158 |
| Top pays (1er auteur) | United States : 1 274 |
| Top auteur | Graefen Markus : 27 |

Si un chiffre est différent, le problème vient presque toujours d'une **relation** (mauvaise colonne ou mauvaise direction) ou d'une colonne lue comme du texte (revoir l'étape 2).

Enregistrez ensuite le rapport sous `powerbi/entrepot_pubmed.pbix`.
