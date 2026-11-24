"""
Connexion à la base PostgreSQL de l'entrepôt.

Les paramètres sont lus dans les variables d'environnement standard de PostgreSQL ;
à défaut, les valeurs ci-dessous sont utilisées :
  PGHOST=localhost  PGPORT=5432  PGUSER=postgres  PGDATABASE=entrepot_pubmed
Le mot de passe est lu dans PGPASSWORD, sinon demandé au clavier (jamais écrit
dans le code ni dans un fichier).
"""
import getpass
import os

import psycopg2

BASE = os.environ.get("PGDATABASE", "entrepot_pubmed")


def parametres():
    p = {"host": os.environ.get("PGHOST", "localhost"),
         "port": os.environ.get("PGPORT", "5432"),
         "user": os.environ.get("PGUSER", "postgres")}
    if "PGPASSWORD" not in os.environ:
        # gardé pour la durée du programme seulement, pour ne pas le redemander
        os.environ["PGPASSWORD"] = getpass.getpass(
            f"Mot de passe PostgreSQL ({p['user']}@{p['host']}:{p['port']}) : ")
    p["password"] = os.environ["PGPASSWORD"]
    return p


def connecter(base=BASE):
    return psycopg2.connect(dbname=base, client_encoding="UTF8", **parametres())


def creer_base_si_absente():
    cx = connecter("postgres")
    cx.autocommit = True  # CREATE DATABASE est interdit dans une transaction
    with cx.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE \"{BASE}\" ENCODING 'UTF8' TEMPLATE template0")
            print(f"Base {BASE} créée.")
    cx.close()
