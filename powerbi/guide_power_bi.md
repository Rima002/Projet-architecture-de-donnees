# Exploration de l'entrepôt PubMed avec Power BI

Ce guide utilise les noms des menus de **Power BI Desktop en anglais**.

Fichiers de ce dossier :
- `mesures.dax` : les mesures à créer (étape 4) ;
- `import_power_query.m` : import depuis les CSV, seulement pour l'option B de l'étape 2.

Prérequis : avoir exécuté `python chargement.py`, qui charge la base PostgreSQL `entrepot_pubmed` et produit les CSV dans `entrepot/csv/`.

---

## Étape 1 — Installer et régler Power BI Desktop

Power BI Desktop est gratuit. Installez-le depuis le **Microsoft Store** : cherchez « Power BI Desktop ».

Avant d'importer les données, désactivez trois automatismes qui ne conviennent pas à ce modèle. Allez dans **File > Options and settings > Options > Current File > Data Load**, et décochez :
- **Import relationships from data sources** : sinon, Power BI recrée les relations à partir des clés étrangères de PostgreSQL, sans tenir compte des copies `dim_temps_creation` et `dim_pays_affiliation` ;
- **Autodetect new relationships after data is loaded** ;
- **Auto date/time** : sinon, Power BI ajoute sa propre hiérarchie Année / Trimestre / Mois / Jour sur les colonnes de date.

## Étape 2 — Importer les tables

### Option A (recommandée) : connexion directe à PostgreSQL

1. **Home > Get data > More… > Database > PostgreSQL database**.
2. Server : `localhost` ; Database : `entrepot_pubmed` ; Data Connectivity mode : **Import**.
3. Identifiants : onglet **Database**, utilisateur `postgres` et votre mot de passe PostgreSQL. Si Power BI signale que la connexion n'est pas chiffrée, acceptez : le serveur est sur votre propre machine.
4. Dans le **Navigator**, cochez les **18 tables** (`dim_…`, `fait_publication`, `pont_…`), puis cliquez sur **Transform Data**.
5. Créez les deux **dimensions à rôles multiples** (expliqué à l'étape 3) :
   - clic droit sur `public dim_temps` > **Reference**, puis renommez la copie `dim_temps_creation` ;
   - faites de même avec `public dim_pays` pour créer `dim_pays_affiliation`.
6. Retirez le préfixe `public ` du nom des autres requêtes (double-clic sur le nom). Sinon, les mesures de `mesures.dax` ne trouveront pas les tables.
7. **Close & Apply**.

Avec cette option, les types des colonnes viennent directement de PostgreSQL : pas de problème de format des nombres.

### Option B : import depuis les fichiers CSV

À utiliser si la connexion à PostgreSQL ne fonctionne pas.

1. **Home > Transform data**. L'éditeur Power Query s'ouvre.
2. **Créer le paramètre** : **Manage Parameters > New Parameter**.
   - Name : `DossierCSV` ;
   - Type : Text ;
   - Current Value : le chemin du dossier `entrepot\csv\`, **avec le `\` final** (voir le bloc 1 du fichier `.m`).
3. **Créer la fonction** : **New Source > Blank Query**, puis **Advanced Editor**. Collez le **bloc 2** et renommez la requête `fnChargerCSV`.
4. **Créer les 20 requêtes** (bloc 3) : pour chacune, **New Source > Blank Query**, tapez la formule dans la barre de formule, par exemple `= fnChargerCSV("fait_publication")`, puis renommez la requête.
   - `dim_temps` et `dim_pays` sont chargées **deux fois**, sous deux noms différents. C'est voulu : ce sont des **dimensions à rôles multiples** (expliqué à l'étape 3).
5. **Close & Apply**.

> La fonction lit les nombres au format anglais (`0.25`), quelle que soit la langue de Windows. Sans elle, avec un Windows en français, les poids `0.25` seraient lus comme `25` ou comme du texte.

## Étape 3 — Créer les relations (vue Model)

Ouvrez la vue **Model** : c'est la troisième icône dans la barre de gauche. Allez dans **Home > Manage relationships** : s'il y a déjà des relations, **supprimez-les toutes**. Créez ensuite exactement les 19 relations ci-dessous avec **New relationship**, en cochant **Make this relationship active** pour chacune.

| From table (côté *) | To table (côté 1) | Cross-filter direction |
|---|---|---|
| fait_publication[id_temps_publication] | dim_temps[id_temps] | Single |
| fait_publication[id_temps_creation] | dim_temps_creation[id_temps] | Single |
| fait_publication[id_revue] | dim_revue[id_revue] | Single |
| fait_publication[id_langue] | dim_langue[id_langue] | Single |
| fait_publication[id_statut] | dim_statut[id_statut] | Single |
| fait_publication[id_pays_premier_auteur] | dim_pays[id_pays] | Single |
| fait_publication[id_article] | dim_article[id_article] | **Both**, Cardinality *One to one (1:1)* |
| pont_auteur[id_article] | fait_publication[id_article] | **Both** |
| pont_auteur[id_auteur] | dim_auteur[id_auteur] | Single |
| pont_auteur[id_pays] | dim_pays_affiliation[id_pays] | Single |
| pont_mesh[id_article] | fait_publication[id_article] | **Both** |
| pont_mesh[id_mesh] | dim_mesh[id_mesh] | Single |
| pont_mesh[id_qualificatif] | dim_qualificatif[id_qualificatif] | Single |
| pont_mot_cle[id_article] | fait_publication[id_article] | **Both** |
| pont_mot_cle[id_mot_cle] | dim_mot_cle[id_mot_cle] | Single |
| pont_type_pub[id_article] | fait_publication[id_article] | **Both** |
| pont_type_pub[id_type_pub] | dim_type_pub[id_type_pub] | Single |
| pont_financement[id_article] | fait_publication[id_article] | **Both** |
| pont_financement[id_financeur] | dim_financeur[id_financeur] | Single |

**Pourquoi « Both » entre un pont et le fait ?** Quand on choisit un auteur, le filtre part de `dim_auteur`, passe par `pont_auteur`, puis doit **remonter** jusqu'à `fait_publication`. Il traverse donc la relation dans le sens inverse, ce qui demande un filtrage dans les deux sens.

**Pourquoi deux tables Temps et deux tables Pays ?** Le fait est lié deux fois au temps (date de publication et date de création). Le pays aussi est utilisé deux fois (pays du 1er auteur dans le fait, pays d'affiliation dans le pont). Power BI n'accepte qu'**un seul chemin actif** entre deux tables : on duplique donc la dimension pour chaque rôle. Chaque copie n'a qu'**une seule** relation.

**Vérification :** dans la vue Model, une ligne pleine indique une relation active, une ligne en pointillés une relation inactive. Il ne doit y avoir **aucune ligne en pointillés**, et les 5 ponts doivent avoir une double flèche du côté de `fait_publication`.

Le schéma obtenu dans la vue Model est celui de `conception_entrepot.md`, section 5. Faites-en une capture d'écran pour le rapport.

## Étape 4 — Préparer le modèle

Les réglages des colonnes se font dans le volet **Properties** de la vue Model : sélectionnez une colonne dans le volet **Data** à droite, puis ouvrez **Properties** avec la flèche **«**. Pour régler plusieurs colonnes d'un coup, maintenez **Ctrl** en cliquant.

1. **Résumé des colonnes** (*Advanced > Summarize by*). Par défaut, Power BI additionne toutes les colonnes numériques, ce qui n'a de sens que pour certaines.

   | Colonnes | Summarize by |
   |---|---|
   | Toutes les `id_*`, `annee`, `pmid`, `rang`, `est_collectif`, `est_check_tag` | **None** |
   | `delai_acceptation_jours`, `delai_indexation_jours` | **Average** |
   | `nb_*`, `avec_resume`, `est_premier`, `est_dernier`, `sujet_majeur`, `poids`, `nb_subventions` | **Sum** (0/1 ou compteurs : la somme a un sens) |

2. **Tri chronologique** (*Advanced > Sort by column*). Sans ce réglage, Power BI trie les libellés par ordre alphabétique (« Août » avant « Janvier »).
   - `dim_temps[libelle_mois]` → trier par **mois** ;
   - `dim_temps[libelle_jour]` → trier par **id_temps** ;
   - faites de même dans `dim_temps_creation`.

3. **Hiérarchie du temps (Année → Mois → Jour)** : dans `dim_temps`, clic droit sur `annee` > **Create hierarchy**. Ajoutez ensuite `libelle_mois`, puis `libelle_jour` à cette hiérarchie (clic droit > **Add to hierarchy**), et renommez-la `Calendrier`. Faites de même dans `dim_temps_creation`.
   - Les dates incomplètes apparaissent à leur niveau : « Mars 2015 (jour inconnu) » sous Mars 2015, « 2015 (mois inconnu) » sous 2015. Les totaux par mois et par année restent donc justes.
   - Pour n'afficher que les dates connues au jour près, filtrez `niveau_precision` = « Jour ».

4. **Hiérarchie géographique (Continent → Pays)** : dans `dim_pays`, clic droit sur `continent` > **Create hierarchy**, ajoutez `pays`, puis renommez la hiérarchie `Géographie`. Faites de même dans `dim_pays_affiliation`.

5. **Cartes géographiques** : sélectionnez `dim_pays[pays]`, puis *Advanced > Data category* = **Country/Region**. Faites de même pour `dim_pays_affiliation[pays]` et `dim_revue[pays]`.

6. **Mesures** : **Home > Enter data**, nommez la table `Mesures`, puis **Load**. Pour chaque mesure de `mesures.dax` : clic droit sur `Mesures` > **New measure**, collez la formule et appuyez sur Entrée.

7. **Format des mesures** : cliquez sur une mesure dans le volet Data, puis utilisez le ruban **Measure tools** (*Format* et nombre de décimales).

   | Mesures | Format |
   |---|---|
   | `% …` et `Évolution vs année précédente` | **Percentage**, 1 décimale |
   | `Délai …`, `… par article` | **Decimal number**, 1 décimale |
   | `Publications pondérées (auteurs)` | **Decimal number**, 2 décimales |
   | `Publications`, `Revues`, `Auteurs distincts`, `Articles en …` | **Whole number**, séparateur de milliers (bouton **,**) |

   Si vous glissez une colonne directement dans un visuel, réglez son format de la même façon dans le ruban **Column tools**. Pour les colonnes de date `jour`, choisissez un format court (14/03/2001).

8. **Masquer les clés** : dans la vue Model, faites un clic droit sur les colonnes `id_*` > **Hide in report view**. Seuls les libellés et les mesures apparaîtront alors dans la liste des champs.

## Étape 5 — Construire le rapport

Revenez à la vue **Report** (première icône de la barre de gauche). Chaque page répond à une question d'analyse de la conception. Les chiffres attendus sont ceux de `python analyse.py`, ce qui permet de vérifier que le modèle est correct.

Les visuels se trouvent dans le volet **Visualizations > Build visual**. Les réglages d'apparence sont dans **Format visual** (l'icône pinceau). Ce volet a une barre **Search** pour trouver un réglage par son nom.

### Page 1 — Vue d'ensemble
- **Card** : `Publications` (4 012), `Revues` (1 075), `Auteurs distincts`, `Délai acceptation (jours)` (≈ 107). Si une carte affiche « 4K », réglez le format de la mesure (étape 4, point 7).
- **Stacked column chart** : X-axis = hiérarchie `Calendrier` de `dim_temps`, Y-axis = `Publications`. Les flèches en haut du visuel permettent l'**exploration** (*drill down*) : de l'année au mois, puis au jour.
- **Line chart** : X-axis = hiérarchie `Calendrier` de `dim_temps_creation`, Y-axis = `Publications`. La date de création est toujours connue au jour près : ce visuel montre bien le niveau Jour.
- **Slicer** : `dim_langue[libelle]`, `dim_statut[statut_citation]`, `dim_type_pub[categorie]`.

### Page 2 — Géographie
- **Map** (ou **Filled map**) : Location = `dim_pays[pays]`, Bubble size = `Publications`. Dans *Filters on this visual*, excluez « Inconnu ».
- **Matrix** : Rows = hiérarchie `Géographie` de `dim_pays`, Columns = `dim_temps[annee]`, Values = `Publications`. C'est le tableau croisé avec *roll-up* (pays → continent) ; le bouton **+** de chaque continent déplie ses pays.
- **Line chart** : `% collaboration internationale` par `dim_temps[annee]`. Ajoutez une **Text box** (ruban **Insert**) pour expliquer le biais d'avant 2014 (voir conception, section « Limites »).

### Page 3 — Revues
- **Clustered bar chart** : Y-axis = `dim_revue[titre]`, X-axis = `Publications`. Dans *Filters on this visual*, sur `titre` : Filter type = **Top N**, Show items = Top **10**, By value = `Publications`.
- **Scatter chart** : Values = `dim_revue[titre]`, X-axis = `Publications`, Y-axis = `Délai acceptation (jours)`. Le nuage montre si les grosses revues sont plus lentes.
- **Slicer** : `dim_revue[pays]`.

### Page 4 — Thématiques (MeSH et mots-clés)
- **Treemap** : Category = `dim_mesh[libelle]`, Values = `Publications (sujet majeur)`. Dans *Filters on this visual* (et **pas** *on this page*), ajoutez `dim_mesh[est_check_tag]` = 0, pour exclure Humans, Male, etc. Un filtre de page retirerait aussi Humans et Animals de l'anneau ci-dessous.
- **Clustered bar chart** : `dim_qualificatif[libelle]` par `Publications` (angle d'étude : génétique, traitement…).
- **Donut chart** : population étudiée. Legend = `dim_mesh[libelle]` filtré sur Humans, Animals et Mice ; Values = `Publications`.
- **Interaction à montrer** : cliquez sur un sujet MeSH, et les autres visuels de la page se filtrent, y compris les revues et les pays. C'est l'effet des tables pont avec le filtre « Both ».

### Page 5 — Auteurs
- **Table** : `dim_auteur[nom]`, `dim_auteur[prenom]`, `Publications`, `Articles en 1er auteur`, `Articles en dernier auteur`, `Publications pondérées (auteurs)`. Pour trier, cliquez sur l'en-tête de colonne `Publications`, ou passez par **… > Sort by**.
  - Gardez `nom` **et** `prenom` : avec le nom seul, Power BI regroupe tous les auteurs qui ont le même nom de famille.
- **Clustered bar chart** : `dim_pays_affiliation[pays]` par `Auteurs distincts`.
- **Vérification à mettre dans le rapport :** la ligne *Total* de `Publications` affiche **4 012**, mais l'addition des lignes du tableau donne beaucoup plus, parce qu'un article a plusieurs auteurs. Power BI recalcule `DISTINCTCOUNT` au niveau du total, et ne fait pas la somme des lignes. La colonne `Publications pondérées`, elle, s'additionne exactement : ses lignes et son total font tous les deux 4 012.

### Page 6 — Financements
- **Clustered bar chart** : `dim_financeur[agence]` par `Publications`.
- **Card** : `% financées`.
- **Matrix** : Rows = `dim_financeur[pays]`, Columns = `dim_temps[annee]`, Values = `Publications`.

## Étape 6 — Vérifier les chiffres

| Vérification | Valeur attendue |
|---|---|
| `Publications` sans filtre | 4 012 |
| `Publications` pour 2013 / 2015 | 1 763 / 1 486 |
| Top revue | PloS one : 158 |
| Top pays (1er auteur) | United States : 1 274 |
| Top auteur (nom + prénom) | Graefen Markus : 27 |

Si un chiffre est différent, le problème vient presque toujours d'une **relation** (mauvaise colonne, mauvaise direction ou relation inactive) ou d'une colonne lue comme du texte (revoir l'étape 2).

Enregistrez ensuite le rapport sous `powerbi/entrepot_pubmed.pbix` (**File > Save as**).

## Mettre à jour après un nouveau chargement

Après chaque `python chargement.py`, cliquez sur **Home > Refresh** dans Power BI. Les relations et les réglages restent en place, tant que les noms de colonnes ne changent pas.
