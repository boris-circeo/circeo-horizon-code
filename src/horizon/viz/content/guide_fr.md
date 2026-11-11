## Mode d'emploi {#use}
Cette page compare des stratégies de routage (« routeurs ») exécutées sur les mêmes hivers simulés. Tout est calculé hors ligne ; rien ici n'est une prévision.
- **Overview** répond à « qui récolte le plus ? » : tableau politiques x tirages, moyenne et dispersion, comparaison appariée A contre B.
- **Explorer** répond à « où et quand un routeur perd-il ? » : choisir un tirage, déplacer le curseur temporel, lire la carte et les courbes synchronisées.
- Les petites icônes **i** et les termes en pointillés s'expliquent au survol ; la ligne grise sous chaque titre dit comment lire le panneau.
- Les pastilles sous la barre des politiques signalent des points d'attention calculés sur les données. Un clic mène ici.
- Touches dans l'Explorer : flèches gauche / droite = 1 h (majuscule : 1 jour), espace = lecture.

## Le problème en une page {#problem}
Un navire à propulsion vélique (deux rotors Flettner, propulseur électrique d'appoint) porte une éolienne et produit de l'électricité en naviguant ou en tenant position dans un vent favorable. La polaire donne la puissance **nette** : production brute de l'éolienne moins la consommation de propulsion ; elle peut donc être négative au près. La puissance dépend de la vitesse du vent vrai ([[TWS]]) et de l'angle sous lequel il rencontre la route ([[TWA]]) : le meilleur cas est un vent de travers de 18 à 26 nœuds entre 75 et 105 degrés (la [[productive band|bande productive]]). Trop peu de vent ne donne rien ; au-delà de {{polar.derate_kn}} nœuds la puissance est réduite, et au-delà de {{polar.cutout_kn}} nœuds la machine s'arrête par sécurité.
Le routeur choisit où aller toutes les {{replan_h}} h en ne connaissant que des prévisions, dont l'erreur croît avec l'échéance. Son score est l'énergie J récoltée sur {{duration_d}} jours. L'**oracle** connaît le vent réel à l'avance et fournit la borne haute ; l'écart à l'oracle est le [[regret]]. Améliorer un routeur, c'est réduire cet écart ; l'Explorer montre où il se creuse.

## Les modèles testés {#models}
Première visite ? Lisez cette section d'abord ; elle ne suppose pas de connaître la note de conception. Les figures ci-dessous ne sont pas des schémas : chacune est calculée à la construction avec le vrai code sur les vraies données (polaire BETA du client, vent ERA5 de 2015, simulations annuelles 2015), avec axes et unités. Chacune est accompagnée d'un texte qui dit ce qu'elle montre, comment la lire, ce qu'il faut retenir, pourquoi c'est important pour le routage et quelles sont ses limites. Cliquez sur une figure pour l'agrandir. La chaîne de modèles se lit dans cet ordre :
- **1-2 Le navire** : la polaire de puissance et l'enveloppe dans l'espace des vitesses disent quelle puissance rapporte chaque manœuvre.
- **3 Le planificateur** : la programmation dynamique sur un graphe espace-temps (grille de 40 km, pas de 3 h, stencil de 49 déplacements) trouve la meilleure route pour un vent donné.
- **4-6 La boucle** : le plan est recalculé toutes les 6 h sur une nouvelle prévision (MPC) ; les ensembles décrivent l'incertitude ; un raffineur continu lisse les 48 premières heures.
- **7 La fin d'horizon** : la valeur terminale dit à la DP ce que vaut le navire quand la fenêtre se termine.
- **8-9 Le verdict** : facteur de charge par routeur (FC, base 100 % = 3 MW toute l'année ; écarts en points) et marge de sécurité côtière.
Si les figures sont absentes (export construit sans les données client), les anciens schémas s'affichent à la place.

!fig ship
!fig problem
!fig dp
!fig stencil
!fig envelope
!fig mpc
!fig ensemble
!fig cvar
!fig refiner
!fig terminal
!fig oracle
!fig cf

### Fiches : ce que chaque routeur utilise et fait {#m-cards}
**B0 (point fixe ; dans les simulations annuelles S4 : poste fixe optimal avec clairvoyance)**
- Informations utilisées : aucune à l'exécution. En S1-S3 le point est choisi sur des hivers passés ; dans les simulations annuelles S4 c'est le meilleur emplacement de 2015 lui-même, connu a posteriori (argmax de la puissance moyenne de tenue de position 2015 de la vérité ERA5, à au moins 50 km de la côte, dans la boîte ERA5, à moins de 800 NM de 47N 6,5W).
- Optimise : rien à l'exécution ; le navire y est tenu immobile et produit par bords de travers alternés.
- Résultat (S4, 2015) : FC 57,1 %, soit 30,9 points sous l'oracle.
- Horizon : toute la mission, sans replanification.
- Forces : simple, robuste, un plancher honnête. Faiblesses : ne peut ni éviter les tempêtes ni chercher le vent.
- Dans l'Explorer : une trajectoire qui va en un point et y reste ; part d'attente proche de 100 %.

**B1 (DP déterministe, 5 ou 15 jours)**
- Informations utilisées : une prévision (membre de contrôle) toutes les 6 h.
- Optimise : l'énergie attendue comme si cette prévision était vraie, sur 5 ou 15 jours ; valeur terminale 0.
- Forces : suit le bon vent. Faiblesses : trop de confiance aux longues échéances, peut finir l'horizon au mauvais endroit.
- Dans l'Explorer : une trajectoire qui change à chaque replanification ; comparer 5 j et 15 j.
- Résultat (S4, 2015, 5 j + raffineur) : FC 77,5 %, soit 10,4 points sous l'oracle ; avec la valeur terminale climatologique (B1c) : FC 79,7 %, 8,3 points sous l'oracle.

**ENS (DP d'ensemble avec CVaR)**
- Informations utilisées : un ensemble de prévisions réduit à quelques scénarios médoïdes et leur dispersion.
- Optimise : un mélange moyenne et queue (CVaR) avec un tronc de 48 h qui ne peut pas anticiper le scénario.
- Horizon : 48 h communes, puis une branche par scénario. Forces : prudent quand la météo est incertaine. Faiblesses : exige des ensembles informatifs ; plus coûteux.
- Dans l'Explorer : le panneau de replanification montre scénarios, poids et dispersion.
- Résultat (S4, 2015, 10 j, 20 membres, 6 scénarios, + raffineur + valeur terminale climatologique) : FC 80,7 %, soit 7,3 points sous l'oracle.

**REF (raffineur continu)**
- Informations utilisées : le plan DP de base et la même prévision.
- Optimise : les 48 premières heures au pas de 30 min, avec la valeur DP en fin de fenêtre comme valeur terminale.
- Forces : trajectoire lisse, moins de biais de grille. Faiblesses : gain modeste ; peut retomber sur le plan de base.
- Dans l'Explorer : la même route que sa base mais sans escaliers.
- Résultat : le raffineur fait partie de tous les routeurs S4 ci-dessus ; sur une fenêtre de 48 h il raccourcit la route et gagne environ un demi pour cent d'énergie (figure 6).

**Oracle (a posteriori)**
- Informations utilisées : le vent réel, à l'avance. Optimise une fois toute la mission.
- Forces : le plafond pour le regret. Faiblesses : non causal, donc pas un concurrent.
- Dans l'Explorer : la ligne de référence à laquelle regret et écart sont mesurés.
- Résultat (S4, 2015, anticipation glissante de 15 j + raffineur, borne approximative) : FC 88,0 %, la référence des écarts. Tous les écarts sont en points de FC (base 100 % = 3 MW toute l'année).

## Les routeurs expliqués {#routers}
Chaque routeur est une politique : à chaque replanification il reçoit une prévision causale et renvoie un plan (destinations toutes les {{plan_dt_h}} h). Le simulateur exécute le plan et mesure l'énergie sur le vent RÉEL.

### B0 - attente au meilleur point fixe {#r-B0}
Rejoint en ligne droite un point choisi sur des hivers d'entraînement (tirages différents de ceux d'évaluation) et y tient position toute la mission. Aucune prévision. Mesure ce que vaut un bon choix statique. Faiblesse : ne peut ni éviter les tempêtes ni chercher le vent ; dans le climat synthétique son point est près de la côte française, artefact du générateur (voir Limites). **Dans les simulations annuelles S4**, B0 est le poste fixe optimal avec clairvoyance : le meilleur emplacement de 2015 lui-même (argmax de la puissance moyenne de tenue de position 2015 de la vérité ERA5, à au moins 50 km de la côte, dans la boîte ERA5, à moins de 800 NM de 47N 6,5W), une référence plus forte qu'un point choisi sur d'autres hivers.

### B0_spec - attente dans la zone indicative {#r-B0_spec}
Comme B0 mais en un point fixe (50N 15W) inspiré de la zone d'exploitation indicative du cahier des charges. Sert de référence « plan naïf ». Attendez-vous au plus mauvais résultat dans le climat synthétique.

### B1 - programmation dynamique déterministe à horizon glissant (5 j, 15 j) {#r-B1}
À chaque replanification il prend la prévision de contrôle (un seul membre), résout une programmation dynamique ([[DP]]) sur la grille sur son horizon et suit le début du chemin optimal ([[MPC]]). La fin d'horizon n'a aucune valeur ([[terminal value|valeur terminale]] = 0), donc il peut finir l'horizon dans un mauvais endroit. Il croit entièrement la prévision, y compris aux grandes échéances : c'est le piège de type Jensen (un vent incertain n'est pas son vent moyen). Un horizon plus long ne devrait aider que tant que la prévision est fiable ; ici 15 j est en moyenne moins bon que 5 j.

### Oracle - optimum a posteriori {#r-Oracle}
Une DP sur le vent réel sur toute la mission, exécutée en boucle ouverte. Non causal : c'est l'étalon, jamais un concurrent. Sa propre discrétisation (pas de {{plan_dt_h}} h, stencil de {{stencil_arcs}} arcs) rend le regret optimiste d'environ 2 points.

### ENS - DP stochastique d'ensemble avec CVaR {#r-ENS}
Tire un ensemble de prévisions, le réduit à quelques scénarios représentatifs (des [[medoid|médoïdes]] sur les modes principaux de variabilité) et résout une DP à deux étages : un tronc commun de 48 h qui ne peut pas anticiper le scénario ([[non-anticipativity|non-anticipativité]]), puis une branche par scénario. L'objectif mélange la moyenne et une mesure de queue ([[CVaR]]) pour éviter les plans bons en moyenne mais catastrophiques en tempête. Avantage attendu sur B1 : plus grand quand la dispersion de l'ensemble est forte (tempêtes incertaines), plus faible les semaines calmes. Le panneau « Replan diagnostics » montre les poids des scénarios, la variance expliquée et les statistiques de valeur.

**État au S2 : ENS ne bat pas encore B1.** Le diagnostic (docs/sprints/S2_diagnosis.md) n'a trouvé aucun bug : l'ensemble synthétique est bien calibré en dispersion, mais sa moyenne n'est pas meilleure que la prévision de contrôle, donc il n'apporte que de la dispersion et aucune information. Une vraie prévision d'ensemble se comporte autrement. À réévaluer avec un modèle d'erreur réaliste ou de vrais reforecasts (S3).

### REF - raffineur continu {#r-REF}
Prend un plan DP et en polit les 48 premières heures avec un optimiseur continu (IPOPT via CasADi) au pas de 30 min, en utilisant la valeur DP à la fin de cette fenêtre comme [[terminal value|valeur terminale]]. Il vise à supprimer les trajectoires en escalier et la dépendance à l'orientation de la DP sur grille. Gain attendu : modeste mais systématique ; s'il retombe sur le plan de base, la trace est identique. **Constaté au S2** : +3 % d'énergie environ et une dispersion entre hivers réduite ; c'est l'effet le plus net du sprint.

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

## L'onglet Polar {#polar}
Affiché quand l'export embarque la polaire de puissance utilisée par les routeurs. C'est la table de puissance nette P en fonction de la vitesse du vent vrai ([[TWS]]), de l'angle du vent ([[TWA]]) et de la vitesse U du navire dans l'eau.
- Angle = TWA depuis le haut (0 degré = vent debout, 180 = vent arrière) ; les deux amures sont dessinées en miroir. Rayon = U. Couleur = puissance nette : bleu négatif, blanc nul, rouge positif. Hachures grises = nœuds infaisables ou masqués.
- Le curseur règle le TWS. Le tireté est U*(TWA), la vitesse qui maximise la puissance là où elle est positive. Le graphe de droite montre P-dagger(TWA) = max sur U de P pour le TWS choisi et quelques TWS de référence.
- Dans l'Explorer, un petit encart polaire montre où chaque navire opère (TWA, U) à l'instant du curseur, sur la polaire au TWS de la politique choisie ; le tableau donne la puissance polaire au TWS propre du navire. Un navire sur une zone bleue perd de l'énergie ; un point loin du tireté navigue à une mauvaise vitesse.
- Faits sur cette polaire (données VPP du client) : puissance nette = production brute de la turbine moins consommation de propulsion, donc elle peut être négative ; vent debout elle est au mieux nulle par physique ; les trous d'échec d'optimisation du [[VPP]] ont été réparés par interpolation ; le secteur lent vent arrière (TWA de 135 degrés ou plus avec U de 2,5 m/s ou moins) est masqué comme bug connu du VPP ; sous 10 nœuds la production est prise quasi nulle (hypothèse énoncée par le client, à confirmer).

## Hypothèses en vigueur {#hyp}
Tous les nombres ci-dessous sont des hypothèses à remplacer par des données réelles ; les conclusions portent sur les comportements relatifs, pas sur l'énergie absolue.
**Communes à tous les runs**
- **Espace et temps** : grille de {{grid_km}} km, pas DP de {{plan_dt_h}} h, replanification toutes les {{replan_h}} h, missions de {{duration_d}} j, pas de contrainte de retour au port, distance minimale à la côte 20 km.
- **Simplifications** : ni dérive ni courant dans la recherche sur graphe, pas de latence de disponibilité des prévisions.
- **Statistique** : {{n_seeds}} runs par politique. La dispersion entre runs est grande.
**Runs synthétiques (S1, S2)**
- **Polaire** : {{polar.kind}}. Optimum de travers vers {{polar.twa_opt_deg}} degrés, plafond {{polar.cap_kw}} kW, réduction dès {{polar.derate_kn}} nœuds, arrêt à {{polar.cutout_kn}} nœuds.
- **Météo** : hiver nord-atlantique simulé ({{weather}} ; jet, cyclones mobiles, indice de régime, bruit). Vérité et prévisions viennent du même générateur. Départ : {{start}}.
**Runs sur données réelles (S3)**
- **Vérité** : vent à 10 m ERA5 de 2015 (horaire), regrillé sur la grille de planification ; les cellules hors de la boîte ERA5 sont grisées sur la carte et remplies par les valeurs du bord.
- **Prévision** : modèle de perturbation échangeable construit à partir de la vérité (déplacement, amplitude et bruit dépendant de l'échéance), de sorte que la vérité est statistiquement un membre de plus. Ce n'est pas une archive de prévisions réelles.
- **Polaire** : la polaire BETA du client décrite dans l'onglet Polar, avec ses masques et réparations.
- **Optimiseur** : stencil à macro-arcs (un arc peut couvrir jusqu'à 2 pas DP, environ 49 directions, plus grand écart angulaire environ 18 degrés) et valeur terminale climatologique (énergie d'une tenue de position sous le vent climatologique local pour le reste de l'horizon).

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
- Ensemble synthétique non informatif : sa moyenne n'est pas meilleure que le contrôle ; la valeur de l'ensemble ne peut pas être jugée sur ces données.
- Les cellules à moins de 20 km de la côte sont interdites à l'optimiseur ; aucun couloir de sortie de port n'est modélisé.
- **Les prévisions S3 sont construites à partir de la vérité** (perturbation d'oracle) : la causalité repose sur les statistiques d'erreur, pas sur le flux de données, et les prévisions successives sont indépendantes entre elles.
- **La polaire sous 10 nœuds** et le secteur lent vent arrière masqué sont des hypothèses du client / des défauts connus du VPP.
- **Une seule année de météo (2015)** : la variabilité saisonnière et interannuelle n'est pas échantillonnée.

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
- **S2** - réduction d'ensemble et DP à deux étages avec CVaR, raffineur continu, cet inspecteur. Résultats : le raffineur gagne ; l'ensemble ne gagne pas encore, à cause de la météo synthétique (voir ENS).
- **S3** - données réelles : vérité ERA5 2015, modèle d'erreur de prévision échangeable, polaire BETA du client avec réparations et masques VPP, stencil à macro-arcs, valeur terminale climatologique ; l'inspecteur gagne l'onglet Polar et le support ERA5.
- **Inspecteur v4.5** - champ de vent de style Windy avec particules animées, onglet Vitrine pour les présentations, facteur de charge en % et écarts à la référence en points (pts), polaires d'occupation, onglet Saisons, figures techniques dans le Guide.
- **Inspecteur v4.6** - mises en page adaptées au téléphone et à la tablette (tactile, barre d'onglets défilante, Guide plein écran, définitions au toucher), commandes de lecture de la Vitrine (vitesse, frise mensuelle, barre d'espace), particules de vent masquées pendant la lecture, respect de « réduire les animations ».
