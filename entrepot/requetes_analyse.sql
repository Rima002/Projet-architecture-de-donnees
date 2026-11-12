-- =====================================================================
-- Requêtes d'analyse de l'entrepôt PubMed (exploitation)
-- Chaque requête répond à une question d'analyse ; "-- Q<n> :" sert de
-- séparateur pour analyse.py.
-- =====================================================================

-- Q1 : Évolution du nombre de publications par année (forage : année -> trimestre)
SELECT t.annee,
       SUM(CASE WHEN t.trimestre = 1 THEN f.nb_publication ELSE 0 END) AS t1,
       SUM(CASE WHEN t.trimestre = 2 THEN f.nb_publication ELSE 0 END) AS t2,
       SUM(CASE WHEN t.trimestre = 3 THEN f.nb_publication ELSE 0 END) AS t3,
       SUM(CASE WHEN t.trimestre = 4 THEN f.nb_publication ELSE 0 END) AS t4,
       SUM(CASE WHEN t.trimestre IS NULL THEN f.nb_publication ELSE 0 END) AS mois_inconnu,
       SUM(f.nb_publication) AS total
FROM fait_publication f
JOIN dim_temps t ON t.id_temps = f.id_temps_publication
GROUP BY t.annee
ORDER BY t.annee;

-- Q2 : Les 10 revues qui publient le plus (avec leur pays)
SELECT r.titre, r.pays, SUM(f.nb_publication) AS publications,
       ROUND(AVG(f.nb_auteurs), 1) AS auteurs_par_article
FROM fait_publication f
JOIN dim_revue r ON r.id_revue = f.id_revue
GROUP BY r.id_revue
ORDER BY publications DESC
LIMIT 10;

-- Q3 : Les 10 pays les plus productifs (pays du premier auteur)
SELECT p.pays, p.continent, SUM(f.nb_publication) AS publications,
       ROUND(100.0 * SUM(f.nb_publication) / (SELECT COUNT(*) FROM fait_publication), 1) AS part_pct
FROM fait_publication f
JOIN dim_pays p ON p.id_pays = f.id_pays_premier_auteur
GROUP BY p.id_pays
ORDER BY publications DESC
LIMIT 10;

-- Q4 : Tableau croisé continent x année (agrégation : pays -> continent)
SELECT p.continent,
       SUM(CASE WHEN t.annee = 2013 THEN 1 ELSE 0 END) AS "2013",
       SUM(CASE WHEN t.annee = 2014 THEN 1 ELSE 0 END) AS "2014",
       SUM(CASE WHEN t.annee = 2015 THEN 1 ELSE 0 END) AS "2015",
       SUM(CASE WHEN t.annee = 2016 THEN 1 ELSE 0 END) AS "2016",
       COUNT(*) AS total
FROM fait_publication f
JOIN dim_pays p ON p.id_pays = f.id_pays_premier_auteur
JOIN dim_temps t ON t.id_temps = f.id_temps_publication
GROUP BY p.continent
ORDER BY total DESC;

-- Q5 : Sujets MeSH principaux (hors population) : 2013 contre 2015
SELECT m.libelle,
       COUNT(DISTINCT CASE WHEN t.annee = 2013 THEN pm.id_article END) AS articles_2013,
       COUNT(DISTINCT CASE WHEN t.annee = 2015 THEN pm.id_article END) AS articles_2015,
       COUNT(DISTINCT pm.id_article) AS articles_total
FROM pont_mesh pm
JOIN dim_mesh m ON m.id_mesh = pm.id_mesh
JOIN fait_publication f ON f.id_article = pm.id_article
JOIN dim_temps t ON t.id_temps = f.id_temps_publication
WHERE pm.sujet_majeur = 1 AND m.est_check_tag = 0
GROUP BY m.id_mesh
ORDER BY articles_total DESC
LIMIT 10;

-- Q6 : Population étudiée : humains, animaux, les deux (articles indexés MeSH)
SELECT CASE
         WHEN h = 1 AND a = 1 THEN 'Humains et animaux'
         WHEN h = 1 THEN 'Humains'
         WHEN a = 1 THEN 'Animaux'
         ELSE 'Non précisé'
       END AS population,
       COUNT(*) AS articles
FROM (SELECT pm.id_article,
             MAX(m.libelle = 'Humans') AS h,
             MAX(m.libelle = 'Animals') AS a
      FROM pont_mesh pm JOIN dim_mesh m ON m.id_mesh = pm.id_mesh
      GROUP BY pm.id_article)
GROUP BY population
ORDER BY articles DESC;

-- Q7 : Les 10 auteurs les plus prolifiques (dont 1er et dernier auteur)
SELECT a.nom, a.prenom, COUNT(*) AS articles,
       SUM(pa.est_premier) AS premier_auteur,
       SUM(pa.est_dernier) AS dernier_auteur,
       ROUND(SUM(pa.poids), 2) AS contribution_ponderee
FROM pont_auteur pa
JOIN dim_auteur a ON a.id_auteur = pa.id_auteur
WHERE a.est_collectif = 0
GROUP BY a.id_auteur
ORDER BY articles DESC
LIMIT 10;

-- Q8 : Les financeurs les plus fréquents
SELECT fi.agence, fi.pays, COUNT(DISTINCT pf.id_article) AS articles_finances,
       SUM(pf.nb_subventions) AS subventions
FROM pont_financement pf
JOIN dim_financeur fi ON fi.id_financeur = pf.id_financeur
GROUP BY fi.id_financeur
ORDER BY articles_finances DESC
LIMIT 10;

-- Q9 : Collaboration internationale (affiliations dans plusieurs pays) par année
SELECT t.annee, COUNT(*) AS articles,
       SUM(f.nb_pays_affiliation > 1) AS internationaux,
       ROUND(100.0 * SUM(f.nb_pays_affiliation > 1) / COUNT(*), 1) AS part_pct
FROM fait_publication f
JOIN dim_temps t ON t.id_temps = f.id_temps_publication
WHERE t.annee BETWEEN 2013 AND 2016
GROUP BY t.annee
ORDER BY t.annee;

-- Q10 : Délai moyen entre réception et acceptation, par revue (>= 15 articles)
SELECT r.titre, COUNT(f.delai_acceptation_jours) AS articles,
       ROUND(AVG(f.delai_acceptation_jours)) AS delai_moyen_jours,
       MIN(f.delai_acceptation_jours) AS mini, MAX(f.delai_acceptation_jours) AS maxi
FROM fait_publication f
JOIN dim_revue r ON r.id_revue = f.id_revue
WHERE f.delai_acceptation_jours IS NOT NULL
GROUP BY r.id_revue
HAVING COUNT(f.delai_acceptation_jours) >= 15
ORDER BY delai_moyen_jours;

-- Q11 : Catégories de publication : comptage simple et pondéré (piège des tables pont)
SELECT tp.categorie,
       COUNT(*) AS liens_article_type,
       COUNT(DISTINCT pt.id_article) AS articles_distincts,
       ROUND(SUM(pt.poids), 1) AS articles_ponderes
FROM pont_type_pub pt
JOIN dim_type_pub tp ON tp.id_type_pub = pt.id_type_pub
GROUP BY tp.categorie
ORDER BY articles_distincts DESC;

-- Q12 : Statut d'indexation : part des articles déjà indexés MEDLINE, par année de création
SELECT t.annee, s.statut_citation, COUNT(*) AS articles
FROM fait_publication f
JOIN dim_statut s ON s.id_statut = f.id_statut
JOIN dim_temps t ON t.id_temps = f.id_temps_creation
GROUP BY t.annee, s.statut_citation
ORDER BY t.annee, articles DESC;
