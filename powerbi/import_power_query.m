// =====================================================================
// Import de l'entrepôt PubMed dans Power BI (Power Query, langage M)
// Voir guide_power_bi.md, étape 2, pour savoir où coller chaque bloc.
// =====================================================================


// ---------------------------------------------------------------------
// BLOC 1 : paramètre DossierCSV
// Accueil > Transformer les données > Gérer les paramètres > Nouveau
//   Nom : DossierCSV   Type : Texte   Valeur actuelle :
//   C:\Users\rimaf\OneDrive\Desktop\3_ID\Architecture de donnees modernes\projet pubmed doc\entrepot\csv\
// (le "\" final est obligatoire)
// ---------------------------------------------------------------------


// ---------------------------------------------------------------------
// BLOC 2 : fonction fnChargerCSV
// Nouvelle source > Requête vide > Éditeur avancé > coller > renommer en fnChargerCSV
// Lit un CSV de l'entrepôt (séparateur ";", UTF-8) et type les colonnes :
// nombres lus au format anglais (0.25) quelle que soit la langue de Windows.
// ---------------------------------------------------------------------
(nomTable as text) as table =>
let
    Source    = Csv.Document(File.Contents(DossierCSV & nomTable & ".csv"),
                    [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes   = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Colonnes  = Table.ColumnNames(Entetes),
    SansVides = Table.TransformColumns(Entetes,
                    List.Transform(Colonnes, (c) => {c, each if _ = "" then null else _})),
    Valeurs   = (c) => List.RemoveNulls(Table.Column(SansVides, c)),
    EstNombre = (c) => List.MatchesAll(Valeurs(c),
                    each (try Number.FromText(_, "en-US") otherwise null) <> null),
    EstEntier = (c) => List.MatchesAll(Valeurs(c), each not Text.Contains(_, ".")),
    Types     = List.Transform(List.Select(Colonnes, EstNombre),
                    (c) => {c, if EstEntier(c) then Int64.Type else type number}),
    Resultat  = Table.TransformColumnTypes(SansVides, Types, "en-US")
in
    Resultat


// ---------------------------------------------------------------------
// BLOC 3 : une requête par table
// Pour chaque ligne : Nouvelle source > Requête vide, coller la formule
// dans la barre de formule, puis renommer la requête avec le nom indiqué.
// ---------------------------------------------------------------------
// Requête                  Formule
// fait_publication       = fnChargerCSV("fait_publication")
// dim_article            = fnChargerCSV("dim_article")
// dim_temps              = fnChargerCSV("dim_temps")
// dim_temps_creation     = fnChargerCSV("dim_temps")          // 2e rôle du temps
// dim_revue              = fnChargerCSV("dim_revue")
// dim_langue             = fnChargerCSV("dim_langue")
// dim_statut             = fnChargerCSV("dim_statut")
// dim_pays               = fnChargerCSV("dim_pays")           // pays du 1er auteur
// dim_pays_affiliation   = fnChargerCSV("dim_pays")           // pays de chaque auteur
// dim_auteur             = fnChargerCSV("dim_auteur")
// dim_mesh               = fnChargerCSV("dim_mesh")
// dim_qualificatif       = fnChargerCSV("dim_qualificatif")
// dim_mot_cle            = fnChargerCSV("dim_mot_cle")
// dim_type_pub           = fnChargerCSV("dim_type_pub")
// dim_financeur          = fnChargerCSV("dim_financeur")
// pont_auteur            = fnChargerCSV("pont_auteur")
// pont_mesh              = fnChargerCSV("pont_mesh")
// pont_mot_cle           = fnChargerCSV("pont_mot_cle")
// pont_type_pub          = fnChargerCSV("pont_type_pub")
// pont_financement       = fnChargerCSV("pont_financement")
