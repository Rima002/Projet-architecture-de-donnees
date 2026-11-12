"""
Nettoyage des fichiers XML PubMed.

Usage : python nettoyage.py [dossier_source] [dossier_sortie]
  par défaut : "pubmed doc" -> "pubmed_clean"

Étapes :
  1. Suppression du BOM UTF-8.
  2. Réparation de la racine : "PubmedArticleSet>" sans "<", balises racine
     en double, balise de fermeture tronquée en fin de fichier.
  3. Échappement des caractères interdits dans le texte ("<0.5 ng/ml", "&" seul).
  4. Ré-équilibrage des balises : fermetures orphelines supprimées,
     balises non fermées refermées, <PubmedArticle> manquant ré-inséré.
  4b. Fragments collés au mauvais niveau (ex. <ArticleTitle> dans un
     <MeshHeading>) remis à leur place, ou supprimés s'ils y sont déjà.
  5. Suppression des articles sans PMID (MedlineCitation/PMID absent ou vide) ;
     si plus aucun article valide, le fichier est supprimé (non copié).
  6. Suppression des doublons : un article déjà présent dans un fichier
     précédent (même PMID et même contenu) est retiré.
  7. Vérification finale avec un parseur XML + rapport CSV.

Les fichiers originaux ne sont jamais modifiés.
"""
import copy
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET

SRC = sys.argv[1] if len(sys.argv) > 1 else "pubmed doc"
DST = sys.argv[2] if len(sys.argv) > 2 else "pubmed_clean"

TOKEN_RE = re.compile(r"<[^<>]*>|[^<]+|<")
TAG_RE = re.compile(r"<(/?)([A-Za-z_][\w.\-]*)[^>]*?(/?)>$", re.S)
CHAMPS_CLES = ["ArticleTitle", "Journal", "Abstract", "AuthorList", "PubmedData"]

# emplacement attendu (structure PubMed) des principaux blocs d'un article
EMPLACEMENT = {t: "MedlineCitation" for t in (  # PMID exclu : présent aussi dans CommentsCorrections
    "DateCreated", "DateCompleted", "DateRevised", "Article", "MedlineJournalInfo",
    "ChemicalList", "CitationSubset", "CommentsCorrectionsList", "MeshHeadingList",
    "KeywordList", "OtherID", "GeneralNote", "SupplMeshList", "InvestigatorList",
    "PersonalNameSubjectList", "OtherAbstract")}
EMPLACEMENT.update({t: "MedlineCitation/Article" for t in (
    "Journal", "ArticleTitle", "Pagination", "ELocationID", "Abstract", "AuthorList",
    "Language", "GrantList", "PublicationTypeList", "ArticleDate", "VernacularTitle")})
EMPLACEMENT.update({"MedlineCitation": "", "PubmedData": "", "History": "PubmedData",
                    "PublicationStatus": "PubmedData", "ArticleIdList": "PubmedData",
                    "PubMedPubDate": "PubmedData/History"})
MULTIPLES = {"ELocationID", "Language", "OtherID", "GeneralNote", "OtherAbstract",
             "CitationSubset", "PubMedPubDate"}


def reparer_racine(txt):
    txt = txt.lstrip("﻿").strip()
    # "PubmedArticleSet>" en début de fichier (le "<" a été perdu)
    txt = re.sub(r"^PubmedArticleSet>", "<PubmedArticleSet>", txt)
    # balise incomplète en fin de fichier, ex. "</PubmedArticleS"
    txt = re.sub(r"<[^<>]*$", "", txt)
    # on retire toutes les balises racine (doublons, fermeture prématurée)
    # puis on ré-encadre proprement
    txt = re.sub(r"</?PubmedArticleSet\s*>", "", txt)
    return txt


def echapper_texte(txt):
    # "&" qui n'est pas une entité
    return re.sub(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|\w+;)", "&amp;", txt)


def equilibrer(txt):
    """Reconstruit un XML bien formé à partir d'un flux de balises abîmé."""
    out, pile = [], []
    for tok in TOKEN_RE.findall(txt):
        if not tok.startswith("<"):
            out.append(echapper_texte(tok))
            continue
        m = TAG_RE.match(tok)
        if not m:  # "<" isolé dans le texte, ex. "<0.5 ng/ml"
            out.append(echapper_texte(tok).replace("<", "&lt;"))
            continue
        fermeture, nom, auto = m.group(1), m.group(2), m.group(3)
        if auto:
            out.append(tok)
        elif fermeture:
            if nom in pile:
                while pile[-1] != nom:  # referme les balises restées ouvertes
                    out.append(f"</{pile.pop()}>")
                pile.pop()
                out.append(tok)
            # sinon : fermeture orpheline (fragment coupé) -> ignorée
        else:
            if nom == "PubmedArticle" and nom in pile:  # article collé dans un autre
                while pile:
                    n = pile.pop()
                    out.append(f"</{n}>")
                    if n == "PubmedArticle":
                        break
            if nom == "MedlineCitation" and "PubmedArticle" not in pile:
                # balise <PubmedArticle> perdue (remplacée par </PubmedArticleSet>)
                pile.append("PubmedArticle")
                out.append("<PubmedArticle>")
            pile.append(nom)
            out.append(tok)
    while pile:
        out.append(f"</{pile.pop()}>")
    return "".join(out)


def nettoyer(chemin):
    with open(chemin, encoding="utf-8-sig", errors="replace") as f:
        brut = f.read()
    try:
        ET.fromstring(brut)
        malforme = False
    except ET.ParseError:
        malforme = True

    xml = "<PubmedArticleSet>" + equilibrer(reparer_racine(brut)) + "</PubmedArticleSet>"
    racine = ET.fromstring(xml)

    gardes, pmids, retires, replaces = [], [], 0, 0
    for enfant in list(racine):
        pmid = enfant.findtext("MedlineCitation/PMID") if enfant.tag == "PubmedArticle" else None
        if pmid and pmid.strip():
            gardes.append(enfant)
            pmids.append(pmid.strip())
            replaces += replacer_fragments(enfant)
        else:
            racine.remove(enfant)
            retires += 1
    manquants = sorted({c for a in gardes for c in CHAMPS_CLES if a.find(f".//{c}") is None})
    return racine, malforme, pmids, retires, manquants, replaces


def chemin(element, parents):
    noms = []
    while element in parents:
        element = parents[element]
        noms.append(element.tag)
    return "/".join(reversed(noms[:-1]))  # sans "PubmedArticle"


def replacer_fragments(article):
    """Un morceau d'article collé au mauvais niveau (ex. <ArticleTitle> dans un
    <MeshHeading>) est remis à sa place, ou supprimé s'il y est déjà."""
    n = 0
    for _ in range(100):
        parents = {c: p for p in article.iter() for c in p}
        mal_place = next((e for e in article.iter() if e in parents and e.tag in EMPLACEMENT
                          and chemin(e, parents) != EMPLACEMENT[e.tag]), None)
        if mal_place is None:
            break
        parents[mal_place].remove(mal_place)
        cible = article
        for nom in filter(None, EMPLACEMENT[mal_place.tag].split("/")):
            cible = cible.find(nom) if cible.find(nom) is not None else ET.SubElement(cible, nom)
        existants = cible.findall(mal_place.tag)
        if mal_place.tag in MULTIPLES:
            deja = any(canonique(x) == canonique(mal_place) for x in existants)
        else:
            deja = bool(existants)
        if not deja:
            cible.append(mal_place)
        n += 1
    # un MeshHeading ne contient que DescriptorName / QualifierName, sans sous-éléments
    for liste in article.iter("MeshHeadingList"):
        for h in list(liste):
            for c in list(h):
                if c.tag not in ("DescriptorName", "QualifierName"):
                    h.remove(c)
                    n += 1
                for sous in list(c):
                    c.remove(sous)
                    n += 1
            if not (h.findtext("DescriptorName") or "").strip():
                liste.remove(h)
                n += 1
    return n


def canonique(article):
    """Contenu d'un article sans les espaces de mise en forme, pour comparer."""
    copie = copy.deepcopy(article)
    for e in copie.iter():
        e.text = (e.text or "").strip() or None
        e.tail = None
    return ET.tostring(copie)


def main():
    os.makedirs(DST, exist_ok=True)
    fichiers = sorted(
        (f for f in os.listdir(SRC) if f.endswith(".xml")),
        key=lambda f: int(f[:-4]) if f[:-4].isdigit() else f,
    )
    rapport, vus = [], {}  # PMID -> (fichier, contenu canonique)
    for f in fichiers:
        racine, malforme, pmids, retires, manquants, replaces = nettoyer(os.path.join(SRC, f))
        # suppression des articles déjà vus avec exactement le même contenu
        doublons = set()
        for article in list(racine):
            pmid = article.findtext("MedlineCitation/PMID").strip()
            contenu = canonique(article)
            if pmid in vus and vus[pmid][1] == contenu:
                racine.remove(article)
                pmids.remove(pmid)
                doublons.add(vus[pmid][0])
            else:
                vus.setdefault(pmid, (f, contenu))
        doublon_de = ";".join(sorted(doublons))
        if pmids:
            ET.indent(racine, space="    ")
            ET.ElementTree(racine).write(os.path.join(DST, f), encoding="utf-8", xml_declaration=True)
            statut = "corrige" if malforme or retires or doublons or replaces else "ok"
        elif doublons:
            statut = "supprime_doublon"
        else:
            statut = "supprime_sans_pmid"
        rapport.append({
            "fichier": f,
            "statut": statut,
            "malforme": malforme,
            "pmids": ";".join(pmids),
            "articles_retires": retires,
            "fragments_replaces": replaces,
            "champs_manquants": ";".join(manquants),
            "doublon_de": doublon_de,
        })

    with open("rapport_nettoyage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rapport[0].keys(), delimiter=";")
        w.writeheader()
        w.writerows(rapport)

    compte = lambda cond: sum(1 for r in rapport if cond(r))
    print(f"Fichiers traités           : {len(rapport)}")
    print(f"  intacts                  : {compte(lambda r: r['statut'] == 'ok')}")
    print(f"  corrigés                 : {compte(lambda r: r['statut'] == 'corrige')}")
    print(f"  supprimés (PMID absent)  : {compte(lambda r: r['statut'] == 'supprime_sans_pmid')}")
    print(f"  avec champs manquants    : {compte(lambda r: r['champs_manquants'] and r['statut'] != 'supprime_sans_pmid')}")
    print(f"  supprimés (doublon)      : {compte(lambda r: r['statut'] == 'supprime_doublon')}")
    print(f"  avec fragments replacés  : {compte(lambda r: r['fragments_replaces'])}")
    print(f"  articles en doublon retirés : {compte(lambda r: r['doublon_de'])}")
    print(f"Sortie : {DST}/  -  rapport : rapport_nettoyage.csv")


if __name__ == "__main__":
    main()
