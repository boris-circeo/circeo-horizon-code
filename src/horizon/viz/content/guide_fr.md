## Mode d'emploi {#use}
Cette page compare des stratégies de routage (« routeurs ») exécutées sur les mêmes hivers simulés. Tout est calculé hors ligne ; rien ici n'est une prévision.
- **Overview** répond à « qui récolte le plus ? » : tableau politiques x tirages, moyenne et dispersion, comparaison appariée A contre B.
- **Explorer** répond à « où et quand un routeur perd-il ? » : choisir un tirage, déplacer le curseur temporel, lire la carte et les courbes synchronisées.
- Les petites icônes **i** et les termes en pointillés s'expliquent au survol ; la ligne grise sous chaque titre dit comment lire le panneau.
- Les pastilles sous la barre des politiques signalent des points d'attention calculés sur les données. Un clic mène ici.
- Touches dans l'Explorer : flèches gauche / droite = 1 h (majuscule : 1 jour), espace = lecture.

## Le problème en une page {#problem}
Un navire à propulsion vélique produit de l'électricité en navigant ou en tenant position dans un vent favorable. La puissance dépend de la vitesse du vent vrai ([[TWS]]) et de l'angle sous lequel il rencontre la route ([[TWA]]) : le meilleur cas est un vent de travers de 18 à 26 nœuds entre 75 et 105 degrés (la [[productive band|bande productive]]). Trop peu de vent ne donne rien ; au-delà de {{polar.derate_kn}} nœuds la puissance est réduite, et au-delà de {{polar.cutout_kn}} nœuds la machine s'arrête par sécurité.
Le routeur choisit où aller toutes les {{replan_h}} h en ne connaissant que des prévisions, dont l'erreur croît avec l'échéance. Son score est l'énergie J récoltée sur {{duration_d}} jours. L'**oracle** connaît le vent réel à l'avance et fournit la borne haute ; l'écart à l'oracle est le [[regret]]. Améliorer un routeur, c'est réduire cet écart ; l'Explorer montre où il se creuse.

## Les routeurs expliqués {#routers}
Chaque routeur est une politique : à chaque replanification il reçoit une prévision causale et renvoie un plan (destinations toutes les {{plan_dt_h}} h). Le simulateur exécute le plan et mesure l'énergie sur le vent RÉEL.

### B0 - attente au meilleur point fixe {#r-B0}
Rejoint en ligne droite un point choisi sur des hivers d'entraînement (tirages différents de ceux d'évaluation) et y tient position toute la mission. Aucune prévision. Mesure ce que vaut un bon choix statique. Faiblesse : ne peut ni éviter les tempêtes ni chercher le vent ; dans le climat synthétique son point est près de la côte française, artefact du générateur (voir Limites).

### B0_spec - attente dans la zone indicative {#r-B0_spec}
Comme B0 mais en un point fixe (50N 15W) inspiré de la zone d'exploitation indicative du cahier des charges. Sert de référence « plan naïf ». Attendez-vous au plus mauvais résultat dans le climat synthétique.

### B1 - programmation dynamique déterministe à horizon glissant (5 j, 15 j) {#r-B1}
À chaque replanification il prend la prévision de contrôle (un seul membre), résout une programmation dynamique ([[DP]]) sur la grille sur son horizon et suit le début du chemin optimal ([[MPC]]). La fin d'horizon n'a aucune valeur ([[terminal value|valeur terminale]] = 0), donc il peut finir l'horizon dans un mauvais endroit. Il croit entièrement la prévision, y compris aux grandes échéances : c'est le piège de type Jensen (un vent incertain n'est pas son vent moyen). Un horizon plus long ne devrait aider que tant que la prévision est fiable ; ici 15 j est en moyenne moins bon que 5 j.

### Oracle - optimum a posteriori {#r-Oracle}
Une DP sur le vent réel sur toute la mission, exécutée en boucle ouverte. Non causal : c'est l'étalon, jamais un concurrent. Sa propre discrétisation (pas de {{plan_dt_h}} h, stencil de {{stencil_arcs}} arcs) rend le regret optimiste d'environ 2 points.

### ENS - DP stochastique d'ensemble avec CVaR {#r-ENS}
Tire un ensemble de prévisions, le réduit à quelques scénarios représentatifs (des [[medoid|médoïdes]] sur les modes principaux de variabilité) et résout une DP à deux étages : un tronc commun de 48 h qui ne peut pas anticiper le scénario ([[non-anticipativity|non-anticipativité]]), puis une branche par scénario. L'objectif mélange la moyenne et une mesure de queue ([[CVaR]]) pour éviter les plans bons en moyenne mais catastrophiques en tempête. Avantage attendu sur B1 : plus grand quand la dispersion de l'ensemble est forte (tempêtes incertaines), plus faible les semaines calmes. Le panneau « Replan diagnostics » montre les poids des scénarios, la variance expliquée et les statistiques de valeur.

### REF - raffineur continu {#r-REF}
Prend un plan DP et en polit les 48 premières heures avec un optimiseur continu (IPOPT via CasADi) au pas de 30 min, en utilisant la valeur DP à la fin de cette fenêtre comme [[terminal value|valeur terminale]]. Il vise à supprimer les trajectoires en escalier et la dépendance à l'orientation de la DP sur grille. Gain attendu : modeste mais systématique ; s'il retombe sur le plan de base, la trace est identique.

### Autres routeurs {#r-generic}
Une politique de nom inconnu est affichée avec ses seuls paramètres exportés. Donnez-lui un préfixe connu (B0, B1, ENS, REF) pour obtenir sa description ici.

## Matrice des capacités {#matrix}
| Routeur | Utilise la prévision | Ensemble | Mesure de risque | Horizon | Valeur terminale | Raffineur | Causal |
|---|---|---|---|---|---|---|---|
| B0 / B0_spec | non | non | - | - | - | non | oui |
| B1_5d / B1_15d | membre de contrôle | non | aucune (moyenne) | 5 j / 15 j | nulle | non | oui |
| ENS | ensemble réduit | oui | CVaR | 15 j (tronc 48 h) | nulle | non | oui |
| REF | comme sa DP de base | comme la base | comme la base | 48 h raffinées | valeur DP à t+48 h | oui (NLP) | oui |
| Oracle | vent réel | - | - | toute la mission | - | non | NON |

## Hypothèses en vigueur {#hyp}
Tous les nombres ci-dessous sont des hypothèses à remplacer par des données réelles ; les conclusions portent sur les comportements relatifs, pas sur l'énergie absolue.
- **Polaire** : {{polar.kind}}. Optimum de travers vers {{polar.twa_opt_deg}} degrés, plafond {{polar.cap_kw}} kW, réduction dès {{polar.derate_kn}} nœuds, arrêt à {{polar.cutout_kn}} nœuds.
- **Météo** : hiver nord-atlantique simulé ({{weather}} ; jet, cyclones mobiles, indice de régime, bruit). Les erreurs de prévision croissent avec l'échéance ; vérité et prévisions viennent du même générateur.
- **Espace et temps** : grille de {{grid_km}} km, pas DP de {{plan_dt_h}} h, replanification toutes les {{replan_h}} h, missions de {{duration_d}} j depuis {{start}}, pas de contrainte de retour au port, distance minimale à la côte 20 km.
- **Simplifications** : ni dérive ni courant dans la recherche sur graphe, pas de latence de disponibilité des prévisions, vérité horaire.
- **Statistique** : {{n_seeds}} tirages (un tirage = un hiver). La dispersion entre tirages est grande.

## À quoi ressemble un bon résultat {#expect}
- Tout routeur causal doit se situer entre B0_spec (pire) et l'oracle (meilleur) ; le regret d'un bon routeur est de quelques dizaines de pourcents ou moins.
- Un routeur doit garder son navire plus longtemps dans la bande productive qu'un routeur statique : comparez les colonnes « Productive band ».
- La courbe d'écart à l'oracle doit croître lentement et régulièrement ; les marches brutales signalent quelques mauvaises décisions à étudier.
- Les routeurs d'ensemble doivent gagner surtout sur les tirages à forte dispersion de tempêtes ; sinon regardez les poids des scénarios.
- Un optimisme de plan (énergie planifiée moins réalisée) proche de zéro signifie que le routeur croit une prévision qui se réalise.

## Limites connues {#limits}
- Les trajectoires sont en escalier : la DP se déplace selon {{stencil_arcs}} directions, soit environ 6 % de dépendance de l'énergie à l'orientation.
- Le regret est optimiste d'environ 2 points (l'oracle ne voit le vent réel que toutes les 3 h).
- Biais de climatologie synthétique : les tempêtes se renforcent vers l'est, donc le meilleur point fixe est près de la côte française et non au large.
- Peu de tirages : {{n_seeds}} hivers sont indicatifs, pas statistiquement concluants.
- Le TWA est indéfini en attente ; le temps d'attente compte dans la bande de TWA pour la part productive.
- Les cellules à moins de 20 km de la côte sont interdites à l'optimiseur ; aucun couloir de sortie de port n'est modélisé.

## Par où commencer {#path}
1. Overview : lisez le résumé et les pastilles ; notez le classement par regret.
2. Comparaison appariée : choisissez les deux routeurs qui vous intéressent, regardez les victoires et la différence moyenne.
3. Ouvrez le tirage où ils diffèrent le plus (clic sur une valeur du tableau par tirage).
4. Dans le graphe d'écart à l'oracle, trouvez où la courbe monte le plus vite ; utilisez « Biggest losses » pour y sauter.
5. Sur la carte, regardez la bande de vent et les centres de tempête à ce moment : le routeur était-il au mauvais endroit, ou la prévision fausse ?
6. Comparez le plan (pointillé) à la trace réelle, et lisez l'optimisme de plan et les diagnostics de replanification.

## Historique {#changelog}
- **S0** - grille, unités et conventions de vent, polaire synthétique, fichier de distance signée à la côte.
- **S1** - météo synthétique avec prévisions causales, noyau DP, enveloppe de puissance, simulateur en boucle fermée, B0 / B1 / oracle, premier chiffre de regret.
- **S2 (en cours)** - réduction d'ensemble et DP à deux étages avec CVaR, raffineur continu, cet inspecteur.
