"""
Étape 2 (suite) : nettoyage des valeurs des fichiers XML PubMed.

Usage : python nettoyage_valeurs.py [dossier_source] [dossier_sortie]
  par défaut : "pubmed_clean" (sortie de nettoyage.py) -> "pubmed_normalise"

Règles appliquées :
  R1 espaces      : suppression des espaces en trop dans tous les textes.
  R2 langue       : codes de langue en minuscules (ENG -> eng).
  R3 type_pub     : casse des types de publication (JOURNAL ARTICLE -> Journal Article).
  R4 dates        : mois et jours sur 2 chiffres (1 -> 01, Feb -> 02) ;
                    éléments de date vides ou invalides (année -0001) supprimés ;
                    PubDate sans Year/Month (MedlineDate, Season) complétée.
  R5 pays_revue   : pays de la revue manquant déduit des autres articles de la
                    même revue ; pays harmonisés (England -> United Kingdom).
  R6 mot_cle      : variantes de casse d'un mot-clé unifiées sur la forme la
                    plus fréquente (PROSTATE CANCER -> prostate cancer).
  R7 affiliation  : adresses e-mail retirées ; pays extrait dans l'attribut
                    Country de <Affiliation>.
  R8 mesh         : libellé d'un descripteur / qualificatif MeSH vérifié par son
                    identifiant UI (forme la plus fréquente dans le corpus).

Chaque modification est tracée dans rapport_valeurs.csv (avant / après).
"""
import collections
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET

SRC = sys.argv[1] if len(sys.argv) > 1 else "pubmed_clean"
DST = sys.argv[2] if len(sys.argv) > 2 else "pubmed_normalise"

MOIS = {m: f"{i:02d}" for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
SAISONS = {"winter": "01", "spring": "04", "summer": "07", "fall": "10", "autumn": "10"}
ELEMENTS_DATE = {"DateCreated", "DateCompleted", "DateRevised", "ArticleDate", "PubDate", "PubMedPubDate"}

# ---------------------------------------------------------------- pays
PAYS = [p.replace("_", " ") for p in """Afghanistan Albania Algeria Argentina Armenia Australia
Austria Azerbaijan Bahrain Bangladesh Belarus Belgium Benin Bolivia Bosnia_and_Herzegovina
Botswana Brazil Bulgaria Burkina_Faso Cameroon Canada Chile China Colombia Congo Costa_Rica
Croatia Cuba Cyprus Czech_Republic Denmark Ecuador Egypt Estonia Ethiopia Finland France Gabon
Germany Ghana Greece Honduras Kosovo Liechtenstein Madagascar Mauritius Myanmar Namibia Nicaragua
Paraguay Puerto_Rico Dominican_Republic El_Salvador Cambodia Brunei Mozambique Angola Mali Togo Guatemala Hong_Kong Hungary Iceland India Indonesia Iran Iraq Ireland Israel Italy
Jamaica Japan Jordan Kazakhstan Kenya Kuwait Latvia Lebanon Libya Lithuania Luxembourg Macedonia
Malawi Malaysia Malta Mexico Moldova Monaco Mongolia Montenegro Morocco Nepal Netherlands
New_Zealand Nigeria Norway Oman Pakistan Palestine Panama Peru Philippines Poland Portugal Qatar
Romania Russia Rwanda Saudi_Arabia Senegal Serbia Singapore Slovakia Slovenia South_Africa
South_Korea Spain Sri_Lanka Sudan Sweden Switzerland Syria Taiwan Tanzania Thailand Tunisia
Turkey Uganda Ukraine United_Arab_Emirates United_Kingdom United_States Uruguay Venezuela
Vietnam Yemen Zambia Zimbabwe""".split()]

ALIAS_PAYS = {p.lower(): p for p in PAYS}
ALIAS_PAYS.update({
    "usa": "United States", "u.s.a": "United States", "us": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "great britain": "United Kingdom",
    "the netherlands": "Netherlands", "holland": "Netherlands", "nederland": "Netherlands",
    "p.r. china": "China", "p. r. china": "China", "pr china": "China", "p.r.china": "China",
    "people's republic of china": "China", "china (mainland)": "China", "prc": "China",
    "korea": "South Korea", "republic of korea": "South Korea", "korea (south)": "South Korea",
    "iran (islamic republic of)": "Iran", "i.r. iran": "Iran", "islamic republic of iran": "Iran",
    "russian federation": "Russia", "viet nam": "Vietnam", "slovak republic": "Slovakia",
    "czechia": "Czech Republic", "r.o.c": "Taiwan", "republic of china": "Taiwan",
    "españa": "Spain", "espana": "Spain", "deutschland": "Germany", "méxico": "Mexico",
    "brasil": "Brazil", "italia": "Italy", "suisse": "Switzerland", "schweiz": "Switzerland",
    "österreich": "Austria", "turkiye": "Turkey", "türkiye": "Turkey", "polska": "Poland",
    "hong kong sar": "Hong Kong", "kingdom of saudi arabia": "Saudi Arabia", "ksa": "Saudi Arabia",
    "uae": "United Arab Emirates", "republic of ireland": "Ireland", "eire": "Ireland",
    "republic of serbia": "Serbia", "republic of macedonia": "Macedonia",
    # nomenclature NLM des pays de revue
    "china (republic : 1949- )": "Taiwan", "russia (federation)": "Russia",
    "georgia (republic)": "Georgia",
})
ETATS_US = [e.replace("_", " ") for e in """alabama alaska arizona arkansas california colorado
connecticut delaware florida georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana
maine maryland massachusetts michigan minnesota mississippi missouri montana nebraska nevada
new_hampshire new_jersey new_mexico new_york north_carolina north_dakota ohio oklahoma oregon
pennsylvania rhode_island south_carolina south_dakota tennessee texas utah vermont virginia
washington west_virginia wisconsin wyoming district_of_columbia""".split()]
CODES_US = """AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV
NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC""".split()
CODES_CANADA = "AB BC MB NB NL NS ON PE QC SK".split()
VILLES = {"seattle": "United States", "boston": "United States", "houston": "United States",
          "baltimore": "United States", "bethesda": "United States", "toronto": "Canada",
          "montreal": "Canada", "london": "United Kingdom", "paris": "France", "tokyo": "Japan",
          "beijing": "China", "shanghai": "China", "seoul": "South Korea", "milan": "Italy",
          "rome": "Italy", "madrid": "Spain", "munich": "Germany", "berlin": "Germany"}
for e in ETATS_US:
    ALIAS_PAYS.setdefault(e, "United States")
ALIAS_PAYS.update(VILLES)

# recherche d'un nom de pays n'importe où dans le texte (le plus long d'abord)
RECHERCHE_PAYS = re.compile(
    r"\b(" + "|".join(sorted((re.escape(a) for a in ALIAS_PAYS if len(a) > 3),
                             key=len, reverse=True)) + r")\b", re.I)
EMAIL_RE = re.compile(r"\s*(Electronic address:)?\s*[\w.+-]+@[\w-]+(\.[\w-]+)+\.?", re.I)


def pays_segment(seg):
    """Pays correspondant à un morceau d'adresse, ou None."""
    s = re.sub(r"\(.*?\)", "", seg)                 # "(USA)", "(J.M.)"
    s = re.sub(r"\b\d[\d\s-]*\b", "", s)            # codes postaux
    s = re.sub(r"^\s*and\s+|\s+and\s*$", "", s.strip(" .;"), flags=re.I).strip(" .;")
    if s.lower() in ALIAS_PAYS:
        return ALIAS_PAYS[s.lower()]
    mots = s.split()
    if mots and mots[-1] in CODES_US:               # "TX", "DC USA", "CA 90095"
        return "United States"
    if mots and mots[-1] in CODES_CANADA:
        return "Canada"
    if mots and mots[-1].lower() in ALIAS_PAYS:     # "DC USA", "NY USA"
        return ALIAS_PAYS[mots[-1].lower()]
    return None


def extraire_pays(texte):
    segments = re.split(r"[,;]", texte)
    for seg in reversed(segments):                  # le pays est en fin d'adresse
        p = pays_segment(seg)
        if p:
            return p
    trouves = RECHERCHE_PAYS.findall(texte)
    return ALIAS_PAYS[trouves[-1].lower()] if trouves else None


def normaliser_pays(p):
    return ALIAS_PAYS.get(p.strip().lower(), p.strip()) if p else p


# ---------------------------------------------------------------- outils
class Journal:
    def __init__(self):
        self.lignes = []
        self.compte = collections.Counter()

    def __call__(self, fichier, pmid, regle, champ, avant, apres):
        self.compte[regle] += 1
        # le journal ne doit pas conserver les adresses retirées des données
        avant, apres = (EMAIL_RE.sub(" [e-mail retiré]", str(v)) for v in (avant, apres))
        self.lignes.append([fichier, pmid, regle, champ, avant, apres])


def textes(article):
    for e in article.iter():
        if e.text and e.text.strip():
            yield e


def charger(dossier):
    for f in sorted(os.listdir(dossier), key=lambda f: int(f[:-4]) if f[:-4].isdigit() else f):
        yield f, ET.parse(os.path.join(dossier, f))


def cle_revue(article):
    mji = article.find("MedlineCitation/MedlineJournalInfo")
    j = article.find("MedlineCitation/Article/Journal")
    cles = []
    if mji is not None:
        cles += [("nlm", mji.findtext("NlmUniqueID")), ("issn", mji.findtext("ISSNLinking"))]
    if j is not None:
        cles += [("issn", j.findtext("ISSN")), ("titre", (j.findtext("Title") or "").lower())]
    return [c for c in cles if c[1]]


# ---------------------------------------------------------------- 1er passage : référentiels
def construire_referentiels():
    pays_revue, variantes_mc, types_pub = {}, collections.defaultdict(collections.Counter), {}
    libelles_mesh = collections.defaultdict(collections.Counter)
    for _, arbre in charger(SRC):
        for a in arbre.getroot():
            pays = a.findtext("MedlineCitation/MedlineJournalInfo/Country")
            if pays:
                for c in cle_revue(a):
                    pays_revue.setdefault(c, normaliser_pays(pays))
            for k in a.iter("Keyword"):
                if k.text and k.text.strip():
                    t = " ".join(k.text.split()).rstrip(".")
                    variantes_mc[t.lower()][t] += 1
            for t in a.iter("PublicationType"):
                if t.text and not t.text.isupper():
                    types_pub[t.text.lower()] = t.text
            for m in list(a.iter("DescriptorName")) + list(a.iter("QualifierName")):
                if m.get("UI") and m.text:
                    libelles_mesh[m.get("UI")][" ".join(m.text.split())] += 1
    # forme retenue : la plus fréquente, à égalité celle qui n'est pas en majuscules
    forme_mc = {k: max(v.items(), key=lambda x: (x[1], not x[0].isupper(), x[0].islower()))[0]
                for k, v in variantes_mc.items()}
    libelle_mesh = {ui: v.most_common(1)[0][0] for ui, v in libelles_mesh.items()}
    return pays_revue, forme_mc, types_pub, libelle_mesh


# ---------------------------------------------------------------- règles
def r1_espaces(a, log):
    for e in textes(a):
        propre = " ".join(e.text.split())
        if propre != e.text.strip():
            log("R1_espaces", e.tag, e.text, propre)
        e.text = propre


def r2_langue(a, log):
    for e in a.iter("Language"):
        if e.text and e.text != e.text.lower():
            log("R2_langue", "Language", e.text, e.text.lower())
            e.text = e.text.lower()


def r3_type_pub(a, log, types_pub):
    for e in a.iter("PublicationType"):
        if e.text and e.text.isupper():
            nouveau = types_pub.get(e.text.lower(), e.text.title())
            log("R3_type_pub", "PublicationType", e.text, nouveau)
            e.text = nouveau


def r4_dates(a, log):
    for parent in list(a.iter()):
        for d in list(parent):
            if d.tag not in ELEMENTS_DATE:
                continue
            nom = d.tag + (f"[{d.get('PubStatus')}]" if d.get("PubStatus") else "")
            for c in list(d):                       # sous-éléments vides : <Month />
                if not (c.text or "").strip():
                    d.remove(c)
                    log("R4_dates", f"{nom}/{c.tag}", "(vide)", "(supprimé)")
            annee = d.findtext("Year")
            if d.tag == "PubDate" and annee is None:
                completer_pubdate(d, nom, log)
                continue
            if annee is None or not re.fullmatch(r"(19|20)\d\d", annee):
                parent.remove(d)
                log("R4_dates", nom, ET.tostring(d, encoding="unicode").split(">")[0] + f"> Year={annee}",
                    "(date supprimée)")
                continue
            for tag in ("Month", "Day"):
                e = d.find(tag)
                if e is None:
                    continue
                v = e.text.strip()
                nv = MOIS.get(v[:3].lower(), v) if tag == "Month" else v
                nv = nv.zfill(2) if nv.isdigit() else nv
                if nv != v:
                    log("R4_dates", f"{nom}/{tag}", v, nv)
                    e.text = nv


def completer_pubdate(d, nom, log):
    """PubDate sans Year : on la déduit de MedlineDate ('2015 Nov-Dec') ou Season."""
    md, saison = d.findtext("MedlineDate"), d.findtext("Season")
    source = md or ""
    m = re.match(r"(\d{4})\s*([A-Za-z]{3})?", source)
    if not m:
        return
    annee, mois = m.group(1), MOIS.get((m.group(2) or "").lower())
    ET.SubElement(d, "Year").text = annee
    if mois:
        ET.SubElement(d, "Month").text = mois
    log("R4_dates", f"{nom}/MedlineDate", md, f"Year={annee} Month={mois or '-'}")
    if saison and d.find("Month") is None and saison.lower() in SAISONS:
        ET.SubElement(d, "Month").text = SAISONS[saison.lower()]


def r4_saison(a, log):
    for d in a.iter("PubDate"):
        s = d.findtext("Season")
        if s and d.find("Month") is None and s.lower() in SAISONS:
            ET.SubElement(d, "Month").text = SAISONS[s.lower()]
            log("R4_dates", "PubDate/Season", s, f"Month={SAISONS[s.lower()]}")


def r5_pays_revue(a, log, pays_revue):
    mci = a.find("MedlineCitation")
    mji = mci.find("MedlineJournalInfo")
    if mji is None:
        mji = ET.SubElement(mci, "MedlineJournalInfo")
    c = mji.find("Country")
    if c is not None and c.text:
        nouveau = normaliser_pays(c.text)
        if nouveau != c.text:
            log("R5_pays_revue", "Country", c.text, nouveau)
            c.text = nouveau
        return
    deduit = next((pays_revue[k] for k in cle_revue(a) if k in pays_revue), None)
    if deduit:
        if c is None:
            c = ET.Element("Country")
            mji.insert(0, c)
        c.text = deduit
        log("R5_pays_revue", "Country", "(absent)", deduit)
    else:
        log("R5_pays_revue", "Country", "(absent)", "(non déductible)")


def r6_mots_cles(a, log, forme_mc):
    for k in a.iter("Keyword"):
        if not k.text:
            continue
        nouveau = forme_mc.get(k.text.rstrip(".").lower(), k.text)
        if nouveau != k.text:
            log("R6_mot_cle", "Keyword", k.text, nouveau)
            k.text = nouveau


def r8_mesh(a, log, libelle_mesh):
    for m in list(a.iter("DescriptorName")) + list(a.iter("QualifierName")):
        attendu = libelle_mesh.get(m.get("UI"))
        if attendu and m.text != attendu:
            log("R8_mesh", m.tag, m.text, attendu)
            m.text = attendu


def r7_affiliations(a, log, stats):
    for titre in a.iter("ArticleTitle"):  # adresse parfois collée à la fin du titre
        if titre.text and EMAIL_RE.search(titre.text):
            sans_mail = EMAIL_RE.sub("", titre.text).strip()
            log("R7_affiliation", "ArticleTitle/email", titre.text, sans_mail)
            titre.text = sans_mail
    for af in a.iter("Affiliation"):
        if not af.text:
            continue
        sans_mail = EMAIL_RE.sub("", af.text).strip(" ;,")
        if sans_mail != af.text:
            log("R7_affiliation", "Affiliation/email", af.text, sans_mail)
            af.text = sans_mail
        pays = extraire_pays(af.text)
        stats[pays is not None] += 1
        if pays:
            af.set("Country", pays)
        else:
            log("R7_affiliation", "Affiliation/pays", af.text, "(pays non trouvé)")


# ---------------------------------------------------------------- programme
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pays_revue, forme_mc, types_pub, libelle_mesh = construire_referentiels()
    os.makedirs(DST, exist_ok=True)
    journal, stats_aff, n = Journal(), collections.Counter(), 0
    for f, arbre in charger(SRC):
        for a in arbre.getroot():
            n += 1
            pmid = a.findtext("MedlineCitation/PMID")
            log = lambda regle, champ, avant, apres: journal(f, pmid, regle, champ, avant, apres)
            r1_espaces(a, log)
            r2_langue(a, log)
            r3_type_pub(a, log, types_pub)
            r4_dates(a, log)
            r4_saison(a, log)
            r5_pays_revue(a, log, pays_revue)
            r6_mots_cles(a, log, forme_mc)
            r7_affiliations(a, log, stats_aff)
            r8_mesh(a, log, libelle_mesh)
        ET.indent(arbre, space="    ")
        arbre.write(os.path.join(DST, f), encoding="utf-8", xml_declaration=True)

    with open("rapport_valeurs.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fichier", "pmid", "regle", "champ", "avant", "apres"])
        w.writerows(journal.lignes)

    print(f"Articles traités : {n}")
    for regle, nb in sorted(journal.compte.items()):
        print(f"  {regle:16} {nb:6} modifications")
    total = sum(stats_aff.values())
    print(f"Pays d'affiliation trouvé : {stats_aff[True]}/{total} ({100 * stats_aff[True] / total:.1f} %)")
    print(f"Sortie : {DST}/  -  journal : rapport_valeurs.csv")


if __name__ == "__main__":
    main()
