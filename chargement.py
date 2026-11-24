"""
Étape 6 : chargement de l'entrepôt de données PubMed (ETL).

Usage : python chargement.py [dossier_source]
  par défaut : "pubmed_normalise" (sortie de nettoyage_valeurs.py)

Produit :
  base PostgreSQL entrepot_pubmed (schéma : entrepot/schema.sql ; connexion : connexion.py)
  entrepot/csv/<table>.csv      export de chaque table (Power BI, Excel…)

Ordre : extraction des articles -> dimensions (clés de substitution)
        -> faits -> tables pont -> contrôles de cohérence.
"""
import csv
import datetime
import io
import os
import sys
import unicodedata
import xml.etree.ElementTree as ET

from connexion import BASE, connecter, creer_base_si_absente

SRC = sys.argv[1] if len(sys.argv) > 1 else "pubmed_normalise"
DOSSIER = "entrepot"
INCONNU = "Inconnu"

NOMS_MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
             "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

LANGUES = {"eng": "Anglais", "fre": "Français", "spa": "Espagnol", "chi": "Chinois",
           "ger": "Allemand", "jpn": "Japonais", "rus": "Russe", "dan": "Danois",
           "hun": "Hongrois", "pol": "Polonais", "dut": "Néerlandais", "cze": "Tchèque",
           "nor": "Norvégien", "ita": "Italien", "por": "Portugais", "tur": "Turc",
           "kor": "Coréen", "swe": "Suédois", "gre": "Grec", "heb": "Hébreu",
           "und": "Non déterminée"}

CONTINENTS = {
    "Afrique": "Algeria Angola Benin Botswana Burkina_Faso Cameroon Congo Egypt Ethiopia Gabon "
               "Ghana Kenya Libya Madagascar Malawi Mali Mauritius Morocco Mozambique Namibia "
               "Nigeria Rwanda Senegal South_Africa Sudan Tanzania Togo Tunisia Uganda Zambia Zimbabwe",
    "Amérique du Nord": "Canada Mexico United_States Cuba Jamaica Puerto_Rico Dominican_Republic "
                        "Costa_Rica El_Salvador Guatemala Honduras Nicaragua Panama",
    "Amérique du Sud": "Argentina Bolivia Brazil Chile Colombia Ecuador Paraguay Peru Uruguay Venezuela",
    "Asie": "Afghanistan Armenia Azerbaijan Bahrain Bangladesh Brunei Cambodia China Georgia Hong_Kong India "
            "Indonesia Iran Iraq Israel Japan Jordan Kazakhstan Kuwait Lebanon Malaysia Mongolia "
            "Myanmar Nepal Oman Pakistan Palestine Philippines Qatar Saudi_Arabia Singapore "
            "South_Korea Sri_Lanka Syria Taiwan Thailand Turkey United_Arab_Emirates Vietnam Yemen",
    "Europe": "Albania Austria Belarus Belgium Bosnia_and_Herzegovina Bulgaria Croatia Cyprus "
              "Czech_Republic Denmark Estonia Finland France Germany Greece Hungary Iceland Ireland "
              "Italy Kosovo Latvia Liechtenstein Lithuania Luxembourg Macedonia Malta Moldova Monaco "
              "Montenegro Netherlands Norway Poland Portugal Romania Russia Serbia Slovakia Slovenia "
              "Spain Sweden Switzerland Ukraine United_Kingdom",
    "Océanie": "Australia New_Zealand",
}
CONTINENT = {p.replace("_", " "): c for c, liste in CONTINENTS.items() for p in liste.split()}

# Descripteurs MeSH qui décrivent la population étudiée plutôt que le sujet
CHECK_TAGS = {"Humans", "Animals", "Male", "Female", "Pregnancy", "Mice", "Rats", "Dogs", "Cats",
              "Cattle", "Swine", "Infant", "Infant, Newborn", "Child", "Child, Preschool",
              "Adolescent", "Adult", "Young Adult", "Middle Aged", "Aged", "Aged, 80 and over"}


def categorie_type(libelle):
    l = libelle.lower()
    if "clinical trial" in l or "randomized" in l:
        return "Essai clinique"
    if l in ("review", "meta-analysis", "systematic review"):
        return "Synthèse"
    if l.startswith("research support"):
        return "Financement"
    if l in ("journal article", "comparative study", "multicenter study", "evaluation studies",
             "validation studies", "observational study", "case reports", "clinical study"):
        return "Recherche originale"
    return "Autre"


def normaliser(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.replace(".", " ").replace("-", " ").split())


def id_temps(annee, mois, jour):
    """AAAAMMJJ ; un 00 marque une partie inconnue (AAAAMM00, AAAA0000) ; 0 = inconnu."""
    if not annee:
        return 0
    mois = int(mois) if mois else 0
    jour = int(jour) if jour and mois else 0
    return int(annee) * 10000 + mois * 100 + jour


def construire_dim_temps(cles):
    """Calendrier complet (tous les jours des années utilisées), plus des membres
    « jour inconnu » par mois et « mois inconnu » par année.
    Hiérarchie : jour -> mois -> année."""
    # colonnes : id_temps, jour (date complète), mois ('AAAA-MM'), annee,
    #            libelle_jour, libelle_mois, niveau_precision
    lignes = [(0, None, None, 0, "Date inconnue", "Date inconnue", "Inconnue")]
    annees = sorted({k // 10000 for k in cles if k})
    for a in annees:
        lignes.append((a * 10000, None, None, a,
                       f"{a} (date incomplète)", f"{a} (mois inconnu)", "Année"))
        for m in range(1, 13):
            mois, libelle = f"{a}-{m:02d}", f"{NOMS_MOIS[m - 1]} {a}"
            lignes.append((a * 10000 + m * 100, None, mois, a,
                           f"{libelle} (jour inconnu)", libelle, "Mois"))
            d = datetime.date(a, m, 1)
            while d.month == m:
                lignes.append((a * 10000 + m * 100 + d.day, d, mois, a,
                               d.strftime("%d/%m/%Y"), libelle, "Jour"))
                d += datetime.timedelta(days=1)
    return sorted(lignes)


def date_de(e):
    """datetime.date d'un élément Year/Month/Day complet, sinon None."""
    if e is None:
        return None
    try:
        return datetime.date(int(e.findtext("Year")), int(e.findtext("Month")), int(e.findtext("Day")))
    except (TypeError, ValueError):
        return None


class Dimension:
    """Attribue une clé de substitution à chaque valeur naturelle distincte."""

    def __init__(self, inconnu=None):
        self.lignes = {}
        if inconnu is not None:
            self.lignes[INCONNU] = (0, inconnu)

    def cle(self, naturelle, attributs):
        if naturelle not in self.lignes:
            self.lignes[naturelle] = (len(self.lignes) + 1, attributs)
        return self.lignes[naturelle][0]

    def rangs(self):
        return [(k, *a) for k, a in sorted(self.lignes.values())]


# ------------------------------------------------------------ extraction / transformation
def transformer():
    temps = set()
    dims = {n: Dimension() for n in ("revue", "langue", "statut", "auteur", "mesh",
                                     "qualificatif", "mot_cle", "type_pub", "financeur")}
    dims["pays"] = Dimension(inconnu=(INCONNU, INCONNU))
    articles, faits = [], []
    ponts = {n: [] for n in ("auteur", "mesh", "mot_cle", "type_pub", "financement")}
    anomalies = []

    def temps_cle(e, f, pmid):
        if e is None:
            return 0
        k = id_temps(e.findtext("Year"), e.findtext("Month"), e.findtext("Day"))
        if k % 100:
            try:
                datetime.date(k // 10000, k // 100 % 100, k % 100)
            except ValueError:  # ex. 31 avril : on garde le mois
                anomalies.append(f"{f} PMID {pmid} : date invalide {k}, jour ignoré")
                k -= k % 100
        temps.add(k)
        return k

    fichiers = sorted(os.listdir(SRC), key=lambda f: int(f[:-4]) if f[:-4].isdigit() else f)
    for f in fichiers:
        for a in ET.parse(os.path.join(SRC, f)).getroot():
            mc = a.find("MedlineCitation")
            art = mc.find("Article")
            pmid = int(mc.findtext("PMID"))
            id_article = len(articles) + 1

            # --- dim_article
            doi = (a.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='doi']")
                   or art.findtext("ELocationID[@EIdType='doi']"))
            pmc = a.findtext("PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
            articles.append((id_article, pmid, art.findtext("ArticleTitle"), doi, pmc, f))

            # --- temps (deux rôles : publication, création dans PubMed)
            t_pub = temps_cle(art.find("Journal/JournalIssue/PubDate"), f, pmid)
            dc = mc.find("DateCreated")
            t_cre = temps_cle(dc, f, pmid)

            # --- revue
            j, mji = art.find("Journal"), mc.find("MedlineJournalInfo")
            nlm = mji.findtext("NlmUniqueID") if mji is not None else None
            pays_revue = (mji.findtext("Country") if mji is not None else None) or INCONNU
            id_revue = dims["revue"].cle(nlm or j.findtext("ISSN") or j.findtext("Title"), (
                nlm or j.findtext("ISSN") or j.findtext("Title"), j.findtext("Title"),
                j.findtext("ISOAbbreviation"), j.findtext("ISSN"),
                pays_revue, CONTINENT.get(pays_revue, INCONNU)))

            # --- langue (première langue citée)
            code = (art.findtext("Language") or "und").lower()
            if len(art.findall("Language")) > 1:
                anomalies.append(f"{f} PMID {pmid} : plusieurs langues, première retenue ({code})")
            id_langue = dims["langue"].cle(code, (code, LANGUES.get(code, code)))

            # --- statut (dimension junk)
            st = (mc.get("Status") or INCONNU, art.get("PubModel") or INCONNU,
                  a.findtext("PubmedData/PublicationStatus") or INCONNU)
            id_statut = dims["statut"].cle(st, (st[0], "Oui" if st[0] == "MEDLINE" else "Non", st[1], st[2]))

            # --- auteurs + pays d'affiliation
            auteurs = art.findall("AuthorList/Author")
            pays_article, id_pays_premier = set(), 0
            for rang, au in enumerate(auteurs, 1):
                if au.findtext("CollectiveName"):
                    nom = au.findtext("CollectiveName")
                    nat = "collectif|" + normaliser(nom)
                    attrs = (nat, nom, None, None, None, 1)
                else:
                    nom, prenom = au.findtext("LastName") or INCONNU, au.findtext("ForeName")
                    nat = normaliser(nom) + "|" + normaliser(prenom)
                    orcid = au.findtext("Identifier[@Source='ORCID']")
                    attrs = (nat, nom, prenom, au.findtext("Initials"), orcid, 0)
                id_auteur = dims["auteur"].cle(nat, attrs)
                pays = next((x.get("Country") for x in au.iter("Affiliation") if x.get("Country")), None)
                id_pays = dims["pays"].cle(pays, (pays, CONTINENT.get(pays, INCONNU))) if pays else 0
                if pays:
                    pays_article.add(pays)
                if rang == 1:
                    id_pays_premier = id_pays
                ponts["auteur"].append([id_article, id_auteur, rang, int(rang == 1),
                                        int(rang == len(auteurs)), id_pays, 1 / len(auteurs)])

            # --- MeSH : une ligne par (descripteur, qualificatif)
            lignes_mesh = {}
            for h in mc.findall("MeshHeadingList/MeshHeading"):
                d = h.find("DescriptorName")
                id_mesh = dims["mesh"].cle(d.get("UI"), (d.get("UI"), d.text, int(d.text in CHECK_TAGS)))
                quals = h.findall("QualifierName") or [None]
                for q in quals:
                    lib = q.text if q is not None else "(aucun)"
                    id_q = dims["qualificatif"].cle(lib, (lib,))
                    majeur = d.get("MajorTopicYN") == "Y" or (q is not None and q.get("MajorTopicYN") == "Y")
                    lignes_mesh[(id_mesh, id_q)] = int(majeur)
            for (id_mesh, id_q), majeur in lignes_mesh.items():
                ponts["mesh"].append([id_article, id_mesh, id_q, majeur, 1 / len(lignes_mesh)])
            nb_mesh = len({m for m, _ in lignes_mesh})

            # --- mots-clés
            # sorted : ordre fixe, donc mêmes clés de substitution à chaque exécution
            mots = {k.text for k in mc.iter("Keyword") if k.text}
            for m in sorted(mots):
                ponts["mot_cle"].append([id_article, dims["mot_cle"].cle(m, (m,)), 1 / len(mots)])

            # --- types de publication
            types = {t.text for t in art.iter("PublicationType") if t.text}
            for t in sorted(types):
                ponts["type_pub"].append([id_article, dims["type_pub"].cle(t, (t, categorie_type(t))),
                                          1 / len(types)])

            # --- financements, regroupés par (agence, pays)
            fin = {}
            for g in art.iter("Grant"):
                k = (g.findtext("Agency") or INCONNU, g.findtext("Country") or INCONNU)
                fin[k] = fin.get(k, 0) + 1
            for k, nb in fin.items():
                ponts["financement"].append([id_article, dims["financeur"].cle(k, k), nb, 1 / len(fin)])

            # --- mesures
            hist = {p.get("PubStatus"): date_de(p) for p in a.iter("PubMedPubDate")}
            delai_acc = delai(hist.get("received"), hist.get("accepted"), f, pmid, "acceptation", anomalies)
            delai_idx = delai(date_de(dc), date_de(mc.find("DateCompleted")), f, pmid, "indexation", anomalies)
            faits.append((id_article, t_pub, t_cre, id_revue, id_langue, id_statut, id_pays_premier,
                          1, len(auteurs), len(pays_article), nb_mesh, len(mots),
                          sum(1 for c in mc.iter("CommentsCorrections") if c.get("RefType") == "Cites"),
                          sum(fin.values()), int(art.find("Abstract") is not None),
                          delai_acc, delai_idx))

    return dims, construire_dim_temps(temps), articles, faits, ponts, anomalies


def delai(debut, fin, f, pmid, nom, anomalies):
    if not (debut and fin):
        return None
    jours = (fin - debut).days
    if jours < 0 or jours > 3650:  # incohérent : écarté de la mesure
        anomalies.append(f"{f} PMID {pmid} : délai d'{nom} incohérent ({jours} jours), mis à NULL")
        return None
    return jours


# ------------------------------------------------------------ chargement
def charger(dims, dim_temps, articles, faits, ponts):
    """Recrée le schéma puis charge les tables, dans une seule transaction :
    en cas d'erreur (clé étrangère, type…), rien n'est chargé."""
    creer_base_si_absente()
    cx = connecter()
    with open(os.path.join(DOSSIER, "schema.sql"), encoding="utf-8") as fh:
        schema = fh.read()

    def copier(cur, table, lignes):
        tampon = io.StringIO()
        csv.writer(tampon).writerows(lignes)  # None -> champ vide -> NULL
        tampon.seek(0)
        cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv)", tampon)

    with cx, cx.cursor() as cur:
        cur.execute(schema)
        # dimensions d'abord, puis faits, puis ponts (contraintes de clés étrangères)
        copier(cur, "dim_temps", dim_temps)
        for nom, d in dims.items():
            copier(cur, "dim_" + nom, d.rangs())
        copier(cur, "dim_article", articles)
        copier(cur, "fait_publication", faits)
        for nom, lignes in ponts.items():
            copier(cur, "pont_" + nom, lignes)
    return cx


def tables_entrepot(cx):
    with cx.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name")
        return [r[0] for r in cur.fetchall()]


def exporter_csv(cx):
    dossier = os.path.join(DOSSIER, "csv")
    os.makedirs(dossier, exist_ok=True)
    tables = tables_entrepot(cx)
    with cx.cursor() as cur:
        for t in tables:
            # BOM UTF-8 : accents corrects à l'ouverture dans Excel
            with open(os.path.join(dossier, t + ".csv"), "w", newline="", encoding="utf-8-sig") as fh:
                cur.copy_expert(f"COPY (SELECT * FROM {t} ORDER BY 1) TO STDOUT "
                                "WITH (FORMAT csv, HEADER, DELIMITER ';')", fh)
    return tables


def controler(cx, nb_attendu):
    def q(sql):
        with cx.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]

    controles = [
        ("1 ligne de faits par article", q("SELECT COUNT(*) FROM fait_publication") == nb_attendu),
        ("PMID uniques", q("SELECT COUNT(DISTINCT pmid) FROM dim_article") == nb_attendu),
        ("clés étrangères déclarées (vérifiées par PostgreSQL au chargement)",
         q("SELECT COUNT(*) FROM information_schema.table_constraints "
           "WHERE constraint_type = 'FOREIGN KEY'") > 0),
        ("nb_auteurs = lignes de pont_auteur",
         q("SELECT SUM(nb_auteurs) FROM fait_publication") == q("SELECT COUNT(*) FROM pont_auteur")),
        ("chaque date de fait existe dans dim_temps (niveau jour, mois ou année)",
         q("SELECT COUNT(*) FROM fait_publication f LEFT JOIN dim_temps t "
           "ON t.id_temps = f.id_temps_publication WHERE t.id_temps IS NULL") == 0),
    ]
    for pont in ("auteur", "mesh", "mot_cle", "type_pub", "financement"):
        controles.append((f"somme des poids pont_{pont} = nb d'articles concernés", q(
            f"SELECT ABS(SUM(poids) - COUNT(DISTINCT id_article)) < 1e-6 FROM pont_{pont}")))
    return controles


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dims, dim_temps, articles, faits, ponts, anomalies = transformer()
    cx = charger(dims, dim_temps, articles, faits, ponts)
    tables = exporter_csv(cx)

    print(f"Base PostgreSQL : {BASE}")
    with cx.cursor() as cur:
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t:20} {cur.fetchone()[0]:7} lignes")
    print("Contrôles :")
    for nom, ok in controler(cx, len(articles)):
        print(f"  [{'OK' if ok else 'ÉCHEC'}] {nom}")
    with open(os.path.join(DOSSIER, "anomalies_chargement.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(anomalies))
    print(f"Anomalies signalées : {len(anomalies)} (entrepot/anomalies_chargement.txt)")
    cx.close()


if __name__ == "__main__":
    main()
