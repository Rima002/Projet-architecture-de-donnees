"""
Exécute les requêtes de entrepot/requetes_analyse.sql et affiche les résultats.

Usage : python analyse.py [numéro]   ex. python analyse.py 5   (toutes par défaut)
"""
import re
import sqlite3
import sys

BASE = "entrepot/entrepot_pubmed.db"
REQUETES = "entrepot/requetes_analyse.sql"


def lire_requetes():
    texte = open(REQUETES, encoding="utf-8").read()
    blocs = re.split(r"^-- (Q\d+) : (.*)$", texte, flags=re.M)
    return [(blocs[i], blocs[i + 1], blocs[i + 2].strip()) for i in range(1, len(blocs), 3)]


def afficher(cur):
    entetes = [c[0] for c in cur.description]
    lignes = [["" if v is None else str(v) for v in l] for l in cur.fetchall()]
    largeurs = [min(45, max(len(x) for x in col)) for col in zip(entetes, *lignes)]
    fmt = lambda l: "  ".join(v[:45].ljust(w) for v, w in zip(l, largeurs))
    print(fmt(entetes))
    print("  ".join("-" * w for w in largeurs))
    for l in lignes:
        print(fmt(l))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    choix = sys.argv[1:] and f"Q{sys.argv[1]}"
    cx = sqlite3.connect(BASE)
    for num, titre, sql in lire_requetes():
        if choix and num != choix:
            continue
        print(f"\n=== {num} : {titre}")
        afficher(cx.execute(sql))


if __name__ == "__main__":
    main()
