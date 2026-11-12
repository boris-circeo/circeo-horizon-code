# 1. Objet et synthèse

## 1.1 Objet et périmètre

Ce document est la deuxième note de la série HORIZON. La note v1 (CIRCEO-OPS-DES-860 rev A) a posé le problème du routage énergétique d'une flottille de navires-éoliennes, la méthode HORIZON et un jeu d'hypothèses de conception. Depuis, une **preuve de concept** (PoC, sprints S0 à S4) a été construit et exécuté sur une année de météo réelle, puis un sprint de consolidation (S5) a été consacré à **comprendre, contester et affiner** : quel est le phénomène physique, que valent les hypothèses de la v1, quelles grandeurs pilotent réellement le résultat, et à quel point celui-ci dépend de la qualité des prévisions et de celle de l'environnement de test.

Le document poursuit quatre buts :

1. **Rendre compte** de ce qui a été construit et mesuré (chapitre 2) ;
2. **Décrire la météo océanique qui compte** pour un navire-éolienne, mesurée sur la réanalyse ERA5 (chapitre 3) ;
3. **Passer en revue chacune des hypothèses de la v1**, méthodiquement, avec le test qui peut la confirmer ou la réfuter, et dire où nous en sommes (chapitre 4) ;
4. **Documenter les sensibilités**, l'algorithme affiné HORIZON v2 et ses résultats typiques (chapitres 5 à 7), puis **dire franchement ce qui reste à prouver** (chapitre 8) et quelles données acquérir (chapitre 9).

::: {.cal .todo}
[ÉTAT DE LA RÉDACTION]{.lab}
Cette révision A est une **ébauche structurée**. Les chapitres 2, 3, 4 (méthode et acquis), 8, 9 et les annexes sont rédigés sur la base des sprints S0 à S4 et des travaux S5 déjà terminés (registre d'hypothèses, analyse de la météo océanique). Les chapitres 5, 6 et 7 dépendent de la **campagne de sensibilité** en cours ; ils portent le marqueur <span class="todo">[À COMPLÉTER S5-campagne]</span> partout où un résultat est attendu. Aucun chiffre de la campagne n'est cité tant qu'il n'est pas validé.
:::

## 1.2 Comment lire ce document

**Encadrés.** Les encadrés ont un sens fixe : *points clés* (cyan), *décision* (bleu), *hypothèse* (ambre), *point ouvert* (violet), *sécurité* (rouge), *critère d'acceptation* (vert), *note* (gris). Les encadrés ambre pâle intitulés « À compléter » signalent un contenu en attente.

**Conventions.** Les unités, la convention de vent, l'angle de vent vrai (TWA) et les définitions des indicateurs (facteur de charge, regret, puissance de tenue de position) sont rappelés en annexe A. Les grandeurs de vent sont en nœuds (kn) dans les analyses météorologiques et en m/s pour les vitesses du navire ; les puissances sont en kW ou MW, les énergies en MWh. La virgule est le séparateur décimal dans le texte.

**Références aux hypothèses.** Chaque hypothèse de la v1 est identifiée par une référence `H-<chapitre>-<n>` où le chapitre est celui de la note v1 ; les hypothèses relatives à *notre* environnement de test portent la référence `H-X-<n>`. Le registre complet figure en annexe C. Les énoncés de la v1 y sont **paraphrasés** (la note v1 est confidentielle et n'est pas recopiée).

**Figures.** Les figures des chapitres 2 et 7 sont produites par le code du dépôt à partir des données réelles (annexe E) ; les figures du chapitre 3 sont les figures de travail de l'analyse S5. Les légendes d'axes de ces figures sont en anglais (figures de travail) ; les légendes et commentaires sont en français.

## 1.3 Synthèse

::: {.cal .todo}
[SYNTHÈSE À COMPLÉTER]{.lab}
<span class="todo">[À COMPLÉTER S5-campagne]</span> La synthèse exécutive (dix lignes) sera rédigée à la clôture de la campagne : verdict sur la valeur du routage, sur la valeur des prévisions d'ensemble et de la fonction de valeur apprise, sensibilité à la qualité des prévisions, défauts par défaut retenus pour HORIZON v2, facteur de charge sur le scénario cible et réserves.
:::

En attendant, voici ce qui est **déjà établi** et qui ne dépend pas de la campagne.

::: {.cal .key}
[ACQUIS À CE JOUR]{.lab}
- **Le routage vaut largement son coût.** Sur l'année 2015 réelle (ERA5, polaire BETA), un navire médian routé atteint un facteur de charge annuel de 0,775 à 0,807 contre 0,571 pour le meilleur point fixe, soit +36 à +41 % d'énergie, avec 12 mois sur 12 en faveur du routage (S4). L'écart au meilleur point fixe est de l'ordre de 40 % et non de 4 %.
- **Environ 70 à 80 % de l'avantage de l'oracle sur le point fixe tient à « être au bon endroit au bon moment »** : une programmation dynamique à prévision parfaite sur la seule puissance de tenue de position suffit à en expliquer 71 % (navire à 4 m/s) à 80 % (8 m/s). La vitesse maximale du navire compte peu (+0,03 de facteur de charge de 4 à 8 m/s) ; savoir *où* aller compte beaucoup.
- **La météo n'offre pas de « système à suivre ».** Les motifs de vent productif se déplacent à 13 nœuds (été) à 23 nœuds (hiver) en médiane, mais un navire qui suivrait parfaitement un système fait *moins bien* que le navire immobile au-delà d'environ 18 h ; l'intérêt de la mobilité vient du gradient spatial à l'échelle de 450 à 650 km, pas de la poursuite d'une dépression.
- **Les horizons utiles de l'information sont de 1 à 5 jours.** Les épisodes productifs durent 11 h en médiane et le champ de vent se renouvelle en 17 à 22 h ; au-delà de 5 jours le modèle de prévision de notre environnement n'apporte guère plus que la climatologie.
- **Plusieurs hypothèses de la v1 sont contredites par nos mesures** (23 sur 119 au statut « contredit ») : l'enveloppe étroite de la polaire, la valeur d'information parfaite de 15 à 40 %, le caractère « conservateur » de l'approximation en deux étages, l'erreur numérique « de quelques dixièmes de pour cent », le nombre de « soixante hivers indépendants ». Douze sont confirmées. 69 restent ouvertes (chapitre 4).
- **Le PoC repose sur des prévisions simulées, sur une seule année, avec un oracle approché.** Les effets de 1 à 3 % (ensemble, fonction de valeur apprise, terminal climatologique) sont **sous le seuil de détectabilité** de nos données (chapitre 8).
:::

# 2. Ce que nous avons construit

## 2.1 La preuve de concept en cinq sprints

Le PoC a été développé en cinq sprints (S0 à S4), chacun clos par une revue indépendante, puis consolidé par S5. Le tableau ci-dessous résume chaque sprint ; les détails chiffrés sont dans les comptes rendus de sprint du dépôt.

| Sprint | Contenu livré | Résultat marquant |
|--------|--------------------------------------------------|------------------------------------------|
| **S0** Fondations | Grille de planification en projection azimutale équivalente de Lambert (LAEA), conventions de vent/cap/TWA, cinématique (dérive, vent apparent), polaire de puissance (table + polaire synthétique + courbe de tenue de position), distance signée à la côte | Trois écarts à la note v1 corrigés dès l'implémentation (formule de TWA décalée de 180°, dérive discontinue, vent apparent sans courant) |
| **S1** Cœur déterministe | Générateur de météo synthétique, programmation dynamique (DP) arrière sur graphe espace-temps (arcs géodésiques), *enveloppe de puissance* à caps mélangés (louvoyage), simulateur causal en boucle fermée, lignes de base B0 (point fixe), B1 (MPC déterministe), oracle | Première courbe de regret ; l'horizon déterministe long (15 j) fait moins bien que 5 j ; quantification du stencil (6 % de dépendance à l'orientation) |
| **S2** Incertitude et raffineur | Ensembles (EOF vectorielle, k-médoïdes maison), DP stochastique à deux étages (tronc de 48 h), raffineur en contrôle optimal continu (CasADi/IPOPT, 30 min sur 48 h), inspecteur de résultats | Le raffineur apporte environ +3 % (4/5 et 5/5 victoires) ; la valeur de l'ensemble est **non évaluable** sur la météo synthétique (la moyenne n'y bat pas le contrôle) |
| **S3** Données réelles | Cache ERA5 2015 sur grille de 40 km, polaire réelle BETA, modèle de prévision par perturbation de la vérité ERA5, arcs macro (K = 49), oracle raffiné | Sur 10 missions de 30 j : routage +25 % d'énergie contre le meilleur point fixe ; raffineur +6 à +7 % ; ensemble + raffineur : écart faible avec B1 raffiné + terminal climatologique (+0,7 %, non significatif) |
| **S4** Année persistante | Modèle de prévision v2 (cohérence entre émissions, latence, saisonnalité), marge côtière exacte, couloir de sortie de Lorient, exécutions d'un an reprenables, étude du biais de clairvoyance (E0), valeur terminale apprise $V_\theta$ | Annuel 2015 : oracle approché 0,880 ; ENS 0,807 ; B1c 0,797 ; B0 0,571 ; 0 violation de côte, 0 intervention de garde |

: Les cinq sprints du PoC et leurs principaux résultats.

Le dépôt de code compte environ 260 fonctions de test (conventions, physique, DP, ensembles, raffineur, simulateur, valeur, inspecteur) ; la politique de dépendances exclut toute licence GPL/AGPL (le registre des licences est tenu dans le dépôt).

## 2.2 L'architecture HORIZON telle qu'implémentée

::: {.cal .note}
[ARCHITECTURE EN UNE PHRASE]{.lab}
Une exploration stratégique par programmation dynamique sur un graphe de 40 km × 3 h, un raffinement tactique en contrôle optimal continu sur 48 h au pas de 30 min qui consomme le champ de valeur stratégique comme valeur terminale, et une exécution à horizon glissant avec replanification toutes les 6 h, le tout alimenté par des prévisions (déterministes ou d'ensemble) et un terminal de valeur climatologique ou appris.
:::

![Le routeur en une image : trois couches entre la météo et le facteur de charge (figure produite par le code du dépôt).](fig/tech_architecture.svg)

Les composants se résument ainsi.

- **Graphe et stencil.** Grille LAEA de 40 km, pas de temps de 3 h ; chaque nœud relie une « tenue de position » et 48 arcs (16 d'un pas, 32 de deux pas, dits macro-arcs) d'une portée maximale d'environ 170 km. Les longueurs d'arc sont géodésiques (l'équivalence entre longueurs de grille et longueurs réelles atteint 3 % en bordure de bassin).
- **Enveloppe de puissance.** La puissance d'un arc est la meilleure puissance atteignable *en mélangeant les caps* (enveloppe concave supérieure de la polaire dans le plan des vitesses sol, calculée par enveloppe convexe tridimensionnelle) après prise en compte de la perte de manœuvre. Elle unifie transit et tenue de position et supprime le biais de quantification du stencil.
- **Programmation dynamique.** Récursion arrière compilée (Numba) : un horizon de 13 jours sur le bassin de 40 km est résolu en environ 0,5 s sur un cœur.
- **Raffineur.** Problème de contrôle optimal à tirs multiples sur 0-48 h au pas de 30 min, sur l'enveloppe de puissance, avec contrainte de distance signée à la côte (contrôle des nœuds, quarts et milieux de segment) et le champ de valeur de la DP en terminal ; échelle de reprise et repli de sécurité.
- **Ensemble.** 20 membres réduits à $k = 6$ médoïdes réels (EOF vectorielle pondérée, PAM), DP par scénario jusqu'à 48 h puis agrégation $(1-\gamma)\,\mathbb{E} + \gamma\,\mathrm{CVaR}_\alpha$, avec un tronc commun déterministe de 48 h pour la non-anticipativité ; $\gamma = 0$ dans S3 et S4.
- **Valeur terminale.** Soit nulle, soit climatologique (puissance de tenue de position moyenne), soit apprise ($V_\theta$ : LightGBM, validation croisée en laissant un mois de côté).
- **Exécution.** Simulateur causal ; la prévision est demandée à l'instant courant, avec latence de disponibilité (ensemble 6 h, contrôle 4 h, cycles 00/06/12/18 UTC) ; replanification toutes les 6 h ; pas de simulation de 15 min.

Les trois routeurs de référence sont **B0** (meilleur point fixe, « mouillage virtuel »), **B1** (MPC déterministe sur la prévision de contrôle ; B1c est la variante à terminal climatologique ; le suffixe *REF* ajoute le raffineur) et **ENS_REF** (ensemble à 20 membres, 10 jours, raffineur). Le routeur **Oracle_REF_H** (météo réalisée connue sur 15 jours, terminal climatologique, raffineur) fournit une borne *approchée* du regret.

## 2.3 L'environnement de test

::: {.cal .ass}
[HYPOTHÈSE STRUCTURANTE]{.lab}
Tous les résultats du PoC sont obtenus dans un environnement simulé : la vérité est la réanalyse ERA5 2015 (grille de 40 km, vent horaire à 10 m), le navire est décrit par la polaire BETA, et les **prévisions sont une perturbation paramétrée de la vérité**, non des prévisions numériques réelles. Les conclusions sur l'horizon utile, la valeur de l'ensemble et le terminal sont donc conditionnelles à cette loi d'erreur (H-X-1, H-2-22).
:::

**Boucle fermée causale.** Le simulateur impose l'absence de fuite d'information : la prévision d'un instant ne dépend pas de la vérité future (vérifié à l'identité binaire après effacement du futur) ; l'énergie est recalculée de façon indépendante à partir des segments bruts (1e-5 de précision relative) ; l'accumulation en simple précision introduit une erreur de 6e-7.

**Modèle de prévision (v2).** La prévision est construite en déplaçant la vérité (déplacement efficace de 40 km à 1 jour à environ 250 km à 7 jours), en modulant son amplitude et en ajoutant un bruit croissant avec l'échéance, avec : (i) une *cohérence entre émissions* successives (moyenner des émissions passées ne fait pas converger vers la vérité), (ii) une *latence* de disponibilité, (iii) une modulation *saisonnière* de 15 % de l'échelle d'erreur (hypothèse, maximum le 15 janvier), (iv) des membres d'ensemble échangeables. L'erreur RMSE du contrôle est de 2,3 / 3,9 / 5,0 / 6,2 m/s aux échéances de 1 / 3 / 5 / 7 jours ; la moyenne d'ensemble bat le contrôle (facteur 1,35 à 1,38 en RMSE, artefact d'échangeabilité) ; le rapport dispersion/erreur est voisin de 1. La loi d'erreur est étalonnée sur des cibles hypothétiques de RMSE d'un ensemble opérationnel, pas ajustée à de vraies prévisions.

**Sprint S5 : un environnement plus réaliste.** Pour la campagne de sensibilité, l'environnement a été complété par : les pertes de manœuvre (virements, empannages, changements de cap) facturées par le simulateur, des boutons de qualité de prévision (échelle d'erreur, latence, cohérence, dispersion, amplitude saisonnière), une erreur de polaire de la vérité (échelle, décalage de TWA), des indicateurs d'exposition aux tempêtes, des routeurs simples (heuristiques voraces, moyenne d'ensemble) et une file de calcul reprenable (chapitre 5).

## 2.4 Les données

| Donnée | Source et traitement | Statut |
|--------------|------------------------------------------------------------------|--------------------|
| **Vent ERA5 2015** | Composantes $(u, v)$ à 10 m, horaires, boîte 32°O–5°E / 38–65°N, régrillées sur la grille LAEA de 40 km (79 × 82 cellules, 3944 cellules marines) ; vérification $u/v$ vrai est/nord à 1e-6 de l'original | Données client ; une seule année |
| **Polaire BETA** | Données VPP du client : puissance nette $P[\mathrm{TWS}, \mathrm{TWA}, U]$ ; $\Psi$ = TWA (0 = vent debout, vérifié par l'identité du vent apparent à 2e-5 m/s près) | Données client |
| **Côte** | Natural Earth 10 m converti en distance signée (SDF) sur 10 km, ressource de 226 ko versionnée ; marge $d_{min} = 20$ km | Libre de droits |
| **Polaire synthétique** | Hypothèses de la note v1 (S0-S2 seulement) | Abandonnée au profit de BETA |

: Les données du PoC.

**Décisions et constats du client qui contraignent l'environnement.**

- La puissance de la polaire est **nette** : production de l'éolienne moins consommation de la propulsion (rotors Flettner et hélice auxiliaire) ; elle peut être négative.
- Les polaires BETA **incluent déjà** la limite du générateur : aucun plafonnement ou arrêt en vent fort n'est superposé (le plateau est d'environ 3 MW de 22 à 50 kn au meilleur TWA).
- Les trous d'optimisation de la table ont été réparés (client) ; le secteur « lent sous le vent » (TWA ≥ 135°, U ≤ 2,5 m/s) est masqué comme bogue du VPP (client ; les bornes exactes sont un choix de l'équipe, à confirmer).
- Au-dessous de 10 kn de vent, la production est négligeable (client).
- La politique de dépendances est propriétaire/commerciale : licences permissives préférées, copyleft faible tolérée et reportée, GPL/AGPL interdites (décision du 2026-11-10).
- Le brief S5 (2026-11-11) exclut toute complexité de routeur nouvelle (réservée à S6) et demande d'instrumenter, comprendre, contester et affiner.

::: {.cal .open}
[POINT OUVERT]{.lab}
Les bornes du masque de bogue du VPP et la possibilité d'un plafonnement réel du générateur au-delà de 35-40 kn sont à confirmer avec le client et l'architecte naval : si le navire réel réduit sa puissance en vent très fort, les routeurs réglés sur BETA surestiment les secteurs de tempête (H-2-14, H-9-1).
:::

![La polaire de puissance BETA et son enveloppe (figures produites par le code du dépôt).](fig/tech_polar.svg)

# 3. La météo océanique qui compte

Ce chapitre répond à une question simple : *quel est le phénomène que le routeur doit exploiter ?* Il rassemble l'analyse de la phénoménologie du vent océanique sur ERA5 2015 (travail S5/WP2) et la confronte aux affirmations météorologiques de la note v1. Tous les chiffres sont issus d'**une seule année** (2015) sur la boîte ERA5 de 32°O–5°E et 38–65°N ; la section 3.8 liste les réserves.

## 3.1 Données, définitions, méthode

**Données.** Vent horaire à 10 m, 2015, grille de 40 km (79 × 82 cellules), cellules marines uniquement (3944 cellules, 8760 h). La vitesse de vent vrai (TWS) est exprimée en nœuds.

**Puissance de tenue de position.** On note $P_{hold}(\mathrm{TWS})$ la puissance d'un navire *immobile* (courbe de tenue construite à partir de l'enveloppe de la polaire BETA). Valeurs de repère : 8 kn → 40 kW, 10 kn → 300 kW, 14 kn → 830 kW, 18 kn → 1770 kW, 20 kn → 2320 kW, 22 kn → 2390 kW, 26 kn → 2500 kW. Cette courbe est inférieure d'environ 15 à 20 % au plateau de navigation libre (≈ 3 MW), car un navire qui tient sa position louvoie près du vent. On définit

$$\mathrm{CF}_{hold} = \frac{P_{hold}}{3000\ \mathrm{kW}}.$$

Un vent est dit **productif** lorsque $P_{hold} > 2$ MW (TWS ≳ 19 kn) et **calme** lorsque TWS < 10 kn ($P_{hold} < 300$ kW).

::: {.cal .acc}
[VALIDATION CROISÉE AVEC LE SIMULATEUR]{.lab}
Une DP à prévision parfaite *interdite de bouger* ($v = 0$) depuis le point de départ de S4 (56,49°N ; 21,6°O) donne un $\mathrm{CF}_{hold}$ annuel de 0,572 et des valeurs mensuelles de 0,784 / 0,691 / 0,702 / … / 0,627, identiques à la ligne B0 de S4 (0,571 ; 0,784 ; 0,691 ; 0,701). $\mathrm{CF}_{hold}$ est donc un représentant fidèle de ce que récolte un navire tenu en position dans le simulateur, et le point de départ de S4 est bien le meilleur point fixe hauturier (meilleure cellule fixe de l'analyse : 0,579).
:::

La grille a un pas de 40 km et le pas de temps est de 1 h. Les saisons sont DJF, MAM, JJA, SON.

## 3.2 Distribution du vent et capacité de récolte

| Moyenne sur les cellules marines | DJF | MAM | JJA | SON | Année |
|---|---|---|---|---|---|
| TWS moyen [kn] | 20,8 | 16,7 | 13,7 | 16,8 | 17,0 |
| calme < 10 kn [% du temps] | 12,5 | 20,9 | 29,3 | 20,3 | 20,8 |
| 10–14 kn | 11,6 | 18,1 | 24,2 | 17,6 | 17,9 |
| 14–18 kn | 14,9 | 19,8 | 22,2 | 19,5 | 19,1 |
| 18–26 kn | 32,0 | 28,8 | 21,3 | 30,0 | 28,0 |
| > 26 kn | 29,1 | 12,5 | 2,9 | 12,5 | 14,2 |
| $P_{hold} > 2$ MW [%] | 57,3 | 36,7 | 20,1 | 38,1 | 38,0 |
| $P_{hold}$ moyenne [kW] | 1753 | 1337 | 979 | 1362 | 1356 |
| $\mathrm{CF}_{hold}$ | 0,584 | 0,446 | 0,326 | 0,454 | 0,452 |

: Distribution du vent vrai et puissance de tenue de position, par saison (moyenne bassin).

![Cartes annuelles du vent et de la puissance de tenue de position (ERA5 2015, boîte 32°O–5°E / 38–65°N).](fig/w_a1_annual_maps.png)

![Cartes saisonnières du facteur de charge de tenue de position.](fig/w_a1_seasonal_maps.png)

![Histogrammes de TWS et $\mathrm{CF}_{hold}$ mensuel du bassin.](fig/w_a1_hist_monthly.png)

**Faits saillants.**

- Quantiles annuels du TWS (5, 10, 25, 50, 75, 90, 95 %) : 4 / 6 / 11 / 16 / 22 / 27 / 31 kn. Seulement 28 % du temps se situe dans la bande 18–26 kn, 14 % au-dessus de 26 kn (énergie du plateau, « perdue » au-delà du coude) et 21 % en calme.
- Le $\mathrm{CF}_{hold}$ mensuel du bassin varie de 0,59 (janvier) à 0,31 (juillet) puis revient à 0,60 (décembre) : le rapport hiver/été vaut **1,9** (la note v1 évoque 2 à 3 pour l'« énergie disponible » ; le plateau de la polaire BETA comprime ce rapport). Le motif suit le TWS moyen mensuel (21,2 → 13,3 kn).
- **Spatial.** Le $\mathrm{CF}_{hold}$ annuel par cellule s'étend de 0,32 à 0,56 (déciles 10-90 %, soit 962 à 1671 kW) ; 40 % des cellules dépassent 0,5, aucune ne dépasse 0,6 sur l'année (63 % des cellules dépassent 0,6 en DJF seul ; aucune cellule ne dépasse 0,5 en JJA). Par bande de latitude : 35–40°N 0,29 ; 40–45°N 0,38 ; 45–50°N 0,46 ; 50–55°N 0,49 ; 55–60°N 0,52 ; 60–65°N 0,50. La zone de référence de la v1 (48–52°N / 12–20°O) a un TWS moyen de 22,9 / 17,2 / 15,1 / 18,1 kn (DJF / MAM / JJA / SON) et un $\mathrm{CF}_{hold}$ annuel de 0,50.
- **La meilleure cellule de l'année est au bord ouest de la boîte** (57,7°N ; 31,4°O ; $\mathrm{CF}_{hold}$ = 0,579) : l'optimum est tronqué par la limite de 32°O (et celle de 65°N). Le point de départ de S4 (56,5°N ; 21,6°O) n'en diffère que de 0,007.

::: {.cal .key}
[CONSÉQUENCES POUR LE ROUTAGE]{.lab}
(i) La ressource est de grande échelle et fortement saisonnière : en hiver le navire doit se trouver dans la moitié du bassin balayée par les dépressions (50–60°N) ; l'été est intrinsèquement pauvre ($\mathrm{CF}_{hold}$ moyen 0,33 ; 0,41 pour le meilleur point fixe). (ii) 14 % du temps au-dessus de 26 kn : le plateau de la polaire (sans plafonnement dans BETA) rend la position et le moment peu critiques *pour l'énergie* dans les vents très forts, mais c'est précisément là que se pose la question de la survie (H-9-1) et où ERA5 sous-estime le vent (section 3.8). (iii) 21 % de calme et 18 % dans la rampe 10–14 kn : un navire fixe perd environ 40 % de son temps à une production presque nulle.
:::

## 3.3 Persistance des conditions productives et des calmes en un point fixe

On calcule les longueurs d'épisodes par cellule marine (pas horaire, 8760 h) ; « comblé 3 h » signifie que les interruptions de 3 h ou moins sont ignorées. Toutes cellules confondues :

| Type d'épisode | Épisodes par cellule et par an | Médiane [h] | Moyenne [h] | Médiane pondérée par le temps [h] | Part du temps en épisodes ≥ 24 h / 72 h |
|---|---|---|---|---|---|
| $P_{hold} > 2$ MW | 167 | 11 | 19,9 | 38 | 70 % / 22 % |
| $P_{hold} > 2$ MW (trous ≤ 3 h comblés) | 125 | 17 | 27,1 | 48 | 78 % / 31 % |
| TWS 18–26 kn | 279 | 6 | 8,8 | 15 | 29 % / 1,6 % |
| calme < 10 kn | 142 | 7 | 12,8 | 24 | 51 % / 14 % |
| calme < 10 kn (comblé) | 120 | 9 | 15,5 | 29 | 58 % / 18 % |

: Statistiques d'épisodes en un point fixe (ERA5 2015, toutes cellules marines).

![Distribution des longueurs d'épisodes productifs et de calmes.](fig/w_a2_runlengths.png)

- La bande 18–26 kn seule est éphémère (médiane 6 h ; 7 % des épisodes durent ≥ 24 h) car le vent la traverse en route vers plus de 26 kn. $P_{hold} > 2$ MW (ouvert vers le haut) dure plus longtemps : médiane 11 h mais longue queue (90e centile 49 h ; 4 % des épisodes ≥ 72 h, qui portent 22 % du temps productif). Longueur moyenne d'un épisode productif par saison : 26,6 h (DJF), 18,3 (MAM), 13,8 (JJA), 18,6 h (SON) ; médianes 16 / 11 / 9 / 11 h.
- Intervalles entre épisodes productifs : médiane 11 h, moyenne 32 h, médiane pondérée par le temps 92 h ; 58 % du temps improductif est dans des intervalles de plus de 72 h. En JJA l'intervalle moyen est de 56 h (90e centile 145 h) contre 19 h en DJF.
- Calmes : médiane 7 h, moyenne 12,8 h ; 14 % du temps calme est dans des calmes ≥ 72 h (épisodes ≥ 72 h : 1,7 %). Le temps de retour entre calmes a une médiane de 27 h (moyenne 48 h) ; en DJF les intervalles entre calmes sont longs (69 h en moyenne).
- Attente entre une heure improductive et la prochaine heure productive (toutes cellules) : médiane 36 h, moyenne 81 h, 90e centile 191 h, 95e 280 h, 99e 619 h. Médiane / 90e centile par saison : DJF 19 / 115 h ; MAM 34 / 189 h ; JJA 57 / 258 h ; SON 32 / 146 h.
- Fenêtres sans aucune heure productive en un point fixe : 38 % des fenêtres de 24 h, 20 % de celles de 72 h, 7,9 % de celles de 168 h (JJA : 58 / 34 / 15 % ; DJF : 20 / 9 / 3 %).

::: {.cal .key}
[CE QUE CELA SIGNIFIE]{.lab}
Un navire fixe voit des conditions productives typiquement pendant 0,5 à 1 jour, puis attend 1,5 jour (médiane 36 h, 8 jours au 95e centile) ; une fenêtre de 72 h a une chance sur cinq de n'en contenir aucune. C'est la raison structurelle de l'écart 57 % → 88 % observé dans S4 : il faut « être ailleurs » à l'échelle de quelques jours. L'échelle de temps des épisodes (10 à 30 h) est plus courte que l'horizon tactique de 48 h du raffineur : celui-ci doit anticiper un vent qui peut avoir disparu en un jour ; seuls les épisodes longs (≥ 72 h, 22 % du temps productif, surtout en DJF) sont exploitables par un navire lent qui arrive tard.
:::

## 3.4 Structure spatio-temporelle et déplacement des systèmes productifs

### 3.4.1 Autocorrélation

Sur les anomalies par rapport à la climatologie mensuelle :

- **Temporelle**, en un point fixe : temps d'e-folding de l'anomalie de TWS de 17 h (temps intégral 16,6 h) ; de l'anomalie du vecteur vent 22 h. Autocorrélation de l'anomalie de TWS à 6 / 12 / 24 / 48 / 72 h : 0,76 / 0,51 / 0,25 / 0,10 / 0,04, négative après 96 h. L'indicateur binaire $P_{hold} > 2$ MW a un e-folding de 16,8 h mais une queue lourde (0,28 à 24 h, 0,19 à 48 h, 0,12 à 120 h, 0,09 à 240 h) ; cette queue est le cycle saisonnier, pas une mémoire météorologique.
- **Spatiale** (anomalie du vecteur vent) : longueur d'e-folding de 625 km en moyenne (552 à 710 km selon l'azimut), distance de demi-corrélation de 404 à 522 km. L'anisotropie est faible (584 km est-ouest contre 666 km nord-sud). L'anomalie de TWS est presque isotrope : e-folding 450 km (404 à 500 km), demi-corrélation 294 à 356 km.
- **Conséquence** : avec une longueur de corrélation de 450 à 650 km et un temps de corrélation de 17 à 22 h, le champ comporte environ une cellule indépendante par carré de 700 km et se renouvelle environ chaque jour.

![Autocorrélations temporelle et spatiale, vitesses de translation des motifs, probabilité conditionnelle de rester productif selon que l'on reste ou que l'on suit le système.](fig/w_a3_spacetime.png)

### 3.4.2 Vitesse de translation des motifs

La vitesse de translation est estimée par corrélation croisée décalée des champs d'anomalie de TWS à $t$ et $t + \Delta t$ ($\Delta t$ = 3 h et 6 h), sur des blocs de 800 km (pas de 400 km), recherche de ±12 cellules, interpolation sous-maille, blocs retenus si la corrélation au pic dépasse 0,5 (99,5 % retenus ; corrélation moyenne 0,94 au pic contre 0,88 sans décalage). Vitesses en nœuds ($\Delta t$ = 3 h ; à 6 h, les médianes diffèrent de 1 à 2 kn) :

| Blocs | Médiane | Moyenne | Déciles 10-90 | < 7,8 kn (navire 4 m/s) | < 15,6 kn (navire 8 m/s) | > 20 kn | > 30 kn | % vers l'est |
|---|---|---|---|---|---|---|---|---|
| tous | 13,6 | 16,9 | 2,3–36,1 | 31 % | 56 % | 33 % | 16 % | 83 |
| productifs (TWS moyen ≥ 16 kn) | 18,7 | 21,1 | 3,0–41,4 | 21 % | 42 % | 47 % | 24 % | 87 |
| forts (≥ 20 kn) | 22,1 | 23,8 | 3,0–45,2 | 18 % | 34 % | 55 % | 31 % | 89 |
| faibles (< 12 kn) | 7,3 | 9,8 | 1,6–21,2 | 53 % | 81 % | 12 % | 4 % | 76 |
| productifs DJF | 23,2 | 25,1 | 3,9–47,0 | 16 % | 32 % | 58 % | 34 % | 88 |
| productifs JJA | 13,2 | 14,7 | 2,7–28,7 | 30 % | 60 % | 27 % | 8 % | 84 |

: Vitesse de translation des motifs d'anomalie de vent (kn).

La vitesse moyenne (tous blocs) est de +11,1 kn vers l'est et +2,3 kn vers le nord (blocs productifs : +14,3 et +3,7). Les systèmes productifs d'hiver se déplacent donc à 20–35 kn (médiane 23 kn ; écart interquartile 12,5–35 kn), en accord avec la v1 ; mais la distribution est large (environ un tiers des motifs sont plus lents que 15,6 kn), les systèmes d'été avancent à 13 kn et les motifs faibles sont lents (7 kn). Le rapport entre la vitesse du système et la vitesse productive du navire (3–4 m/s, soit 6–8 kn) est d'environ 2,4 pour le bloc productif médian et 3 en DJF (moyennes 2,7 et 3,2), non de 4 à 6 comme l'écrit la v1 pour un navire de 3–9 kn ; il est de 1,2 à 1,5 face à la vitesse maximale absolue du navire (8 m/s = 15,6 kn). Ces vitesses sont celles de motifs d'anomalie de 800 km (mélange d'advection et de propagation d'ondes) et ne sont pas mesurables au-delà de ≈ 43 kn à $\Delta t$ = 6 h.

### 3.4.3 Persistance lagrangienne contre eulérienne ; taille des taches

On estime la probabilité qu'une cellule productive à l'instant $t$ le soit encore $\tau$ heures plus tard, (a) au même endroit (eulérien), (b) à l'endroit déplacé de la vitesse locale du motif (un navire qui suivrait exactement le système), (c) en suivant avec une vitesse plafonnée à 7,8 ou 15,6 kn. La probabilité inconditionnelle est de 0,378.

| $\tau$ [h] | rester (eulérien) | suivre ≤ 7,8 kn | suivre ≤ 15,6 kn | vitesse complète du système |
|---|---|---|---|---|
| 6 | 0,795 | 0,812 | 0,820 | 0,821 |
| 12 | 0,682 | 0,698 | 0,703 | 0,691 |
| 24 | 0,570 | 0,564 | 0,546 | 0,497 |
| 48 | 0,516 | 0,476 | 0,428 | 0,393 |

: Probabilité qu'un point productif le soit encore $\tau$ heures plus tard.

- Suivre le système aide de 1,5 à 2,5 points à 6–12 h, mais **fait moins bien que rester** au-delà d'environ 18 h (−7 points à 24 h et −12 points à 48 h pour un suiveur parfait ; à 48 h il ne fait guère mieux que la chance climatologique de 0,38). En DJF : rester 0,69 / 0,67 à 24 / 48 h contre 0,61 / 0,56 en suivant. En JJA : rester 0,355 / 0,239, suivre 0,315 / 0,17.
- **Interprétation** : le « vent productif » n'est pas un objet conservé que l'on emporte ; les dépressions se creusent, se comblent et sont relayées par le membre suivant de la trajectoire des tempêtes, de sorte qu'un lieu situé dans le régime productif le reste plus souvent que la tache qui se déplace.
- **Géométrie des taches** ($P_{hold} > 2$ MW, composantes connexes ≥ 20 cellules, n = 2226) : diamètre équivalent médian 530 km (quartiles 313–1030 km ; 90e centile 1700 km, tronqué par le domaine), vitesse médiane 11 kn ; 41 % des taches sont plus lentes que 7,8 kn et 62 % plus lentes que 15,6 kn ; temps de passage d'une tache sur un point fixe : 35 h en médiane (quartiles 18–89 h).

::: {.cal .key}
[CONSÉQUENCES]{.lab}
(i) L'affirmation de la v1 selon laquelle les systèmes distancent le navire, qui ne peut donc que se trouver sur leur trajectoire sans jamais les chasser, est **confirmée en vitesse** et **précisée** : la question n'est pas de chasser, car même un chasseur parfait perd contre un navire immobile au-delà de 18 h. (ii) La valeur de la mobilité est à chercher dans le gradient spatial à l'échelle de 450 à 650 km (section 3.5), pas dans le surf d'une dépression. (iii) Un rendez-vous avec une tache de 500 km qui avance à 20 kn dure environ un jour pour un navire fixe ; un navire qui traverse la trajectoire à 4 m/s la traverse. (iv) Les horizons de prévision d'intérêt sont le temps de passage (1 à 3 jours), non la semaine que la v1 propose pour le champ de valeur stratégique.
:::

## 3.5 Atteignabilité et valeur de la mobilité

### 3.5.1 Meilleur vent atteignable

Portée statique (distance par la mer ≤ $vT$, stencil à 8 voisins). *local* est le $\mathrm{CF}_{hold}$ moyen à la cellule du navire ; *meilleur maintenant* est la meilleure $P_{hold}$ instantanée dans la portée ; *persistance* consiste à se rendre à la meilleure cellule du moment et lire le $\mathrm{CF}_{hold}$ sur la fenêtre suivante ; *prévision parfaite* consiste à se rendre à la cellule de meilleure moyenne future (borne supérieure biaisée vers le haut par le maximum sur 12 à 3000 cellules).

| Vitesse, $T$ | Portée [km] / cellules | local | meilleur maintenant | rester, fenêtre suivante | persistance | prévision parfaite | gain prévision si rester < 0,4 |
|---|---|---|---|---|---|---|---|
| 4 m/s, 6 h | 86 / 12 | 0,452 | 0,545 | 0,449 | 0,485 | 0,534 | +0,12 |
| 4 m/s, 24 h | 346 / 187 | 0,451 | 0,727 | 0,451 | 0,490 | 0,674 | +0,34 |
| 4 m/s, 72 h | 1037 / 1263 | 0,449 | 0,840 | 0,450 | 0,494 | 0,746 | +0,46 |
| 8 m/s, 6 h | 173 / 55 | 0,452 | 0,632 | 0,449 | 0,527 | 0,618 | +0,26 |
| 8 m/s, 24 h | 691 / 651 | 0,451 | 0,814 | 0,451 | 0,519 | 0,769 | +0,52 |
| 8 m/s, 72 h | 2074 / 3058 | 0,449 | 0,859 | 0,450 | 0,504 | 0,791 | +0,53 |

: Meilleur vent atteignable et gains de relocalisation (facteur de charge de tenue de position).

À 24 h, un navire à 4 m/s peut atteindre (346 km, environ une longueur de corrélation) une cellule dont le facteur de charge instantané est de 0,73 contre 0,45 localement ; à 8 m/s, 0,81. Mais ce que l'on trouve en allant vers la meilleure cellule du moment a en grande partie disparu à la fenêtre suivante : la relocalisation par persistance ne réalise que +3 à +7 points (0,49 à 4 m/s et 24 h ; 0,52 à 8 m/s), à peu près indépendamment de $T$. La prévision parfaite réalise +22 points (4 m/s, 24 h) à +32 points (8 m/s, 24 h) et sature après 24–72 h. L'été est le plus bas en niveau absolu (0,58–0,66 à 4 m/s) mais le gain est voisin (+0,26 à +0,34). Dans 54 % du temps, le facteur de charge de la fenêtre suivante d'un navire fixe est inférieur à 0,5 ; quand il est inférieur à 0,4, relocaliser avec prévision parfaite gagne 0,34 (4 m/s, 24 h) et la persistance 0,12.

### 3.5.2 Oracle à prévision parfaite sur le champ de puissance de tenue

Programmation dynamique sur les champs de $\mathrm{CF}_{hold}$ moyens sur 3 h, navire libre de se déplacer dans un disque de rayon $v\,\Delta t$ (cellules de 40 km), sans coût de manœuvre ni de transit, départ à 56,49°N / 21,6°O :

| Vitesse du navire $v$ [m/s] | 0 | 4 | 6 | 8 | 12 | 16 | 24 | 32 |
|---|---|---|---|---|---|---|---|---|
| $\mathrm{CF}_{hold}$ annuel de l'oracle | 0,572 | 0,791 | 0,807 | 0,820 | 0,834 | 0,840 | 0,848 | 0,853 |
| JJA / DJF aux mêmes vitesses | 0,41 / 0,70 | 0,72 / 0,85 | 0,75 / 0,86 | 0,76 / 0,86 | 0,79 / 0,87 | 0,80 / 0,87 | 0,81 / 0,87 | 0,82 / 0,88 |

: Oracle de tenue de position selon la vitesse du navire.

(À 2 m/s, le navire parcourt 0,54 cellule par pas et ne peut pas quitter sa cellule : il reproduit $v = 0$ ; c'est un artefact de résolution.) En partant de n'importe où, on obtient en moyenne 0,78 (4 m/s) et 0,81 (8 m/s) : **avec prévision parfaite et mobilité, la position de départ n'a plus d'importance** (meilleur point fixe 0,579 contre 0,452 pour la cellule fixe moyenne).

![Oracle de tenue de position selon la vitesse ; oracle confiné à un disque ; relocalisation par persistance et par prévision parfaite.](fig/w_a4_mobility.png)

Part de l'avantage de l'oracle S4 sur le meilleur point fixe (oracle 0,880 ; B0 0,571 ; écart 0,309) expliquée par le seul accès à un meilleur vent (oracle de tenue moins point fixe) :

| Périmètre | $\mathrm{CF}_{hold}$ de l'oracle | Gain vs point fixe | Part de l'écart S4 |
|---|---|---|---|
| $v$ = 4 m/s, portée illimitée | 0,791 | +0,219 | **71 %** |
| $v$ = 8 m/s | 0,820 | +0,248 | **80 %** |
| $v$ = 16 m/s | 0,840 | +0,268 | 87 % |
| $v$ = 8 m/s confiné à 80 km du départ | 0,640 | +0,068 | 22 % |
| 160 km | 0,686 | +0,114 | 37 % |
| 320 km | 0,742 | +0,170 | 55 % |
| 640 km | 0,793 | +0,221 | 72 % |
| 1280 km | 0,818 | +0,246 | 80 % |
| $v$ = 4 m/s, $R$ = 160 / 320 / 640 km | 0,671 / 0,720 / 0,765 | +0,099 / +0,148 / +0,194 | 32 / 48 / 63 % |

: Part de l'écart S4 expliquée par l'atteinte d'un meilleur vent.

Les 20 à 29 % restants (0,06 à 0,09 de facteur de charge) correspondent à ce qu'un oracle de tenue ne peut voir : la production en navigation à 6–9 kn sous le meilleur TWA (la polaire libre est au-dessus de la courbe de tenue), la résolution de 3 h contre 1 h et l'approximation de l'anticipation de 15 jours de l'oracle de S4.

**L'oracle chasse-t-il les systèmes ?** Non. Sur le chemin optimal le navire se déplace dans 94 % des pas (vitesse moyenne de 7,2 kn en réglage 4 m/s, 12,6 kn en 8 m/s) mais seuls 28 à 36 % des pas sont à moins de 45° de la vitesse locale du motif, et 44 % lui sont opposés (cosinus moyen +0,08 à +0,12) ; la composante moyenne de la vitesse le long du système n'est que de +0,6 kn (4 m/s) à +1,2 kn (8 m/s) pour des vitesses de motif de 17 kn. L'oracle zigzague à l'intérieur de la zone productive ; il ne chevauche pas les systèmes.

::: {.cal .key}
[CONSÉQUENCES]{.lab}
(i) La mobilité vaut +0,22 à +0,25 de facteur de charge (+38 à +43 % de B0), dont la moitié est obtenue dans un rayon d'environ 300 km et les trois quarts dans un rayon d'environ 650 km, c'est-à-dire que le gain suit la longueur de corrélation de 500 à 650 km ; passer de 4 à 8 m/s n'ajoute que +0,03 (10 % de l'écart) : ce qui compte est de pouvoir se déplacer à environ 7 kn en continu et de **savoir où**. (ii) L'écart est expliqué à 70–80 % par *être au bon endroit au bon moment* : l'information utile est le temps réalisé à 300–700 km sur 1 à 3 jours, donc la valeur de la prévision est concentrée à 1–3 jours (section 3.6). (iii) La pure persistance (« aller là où il y a du vent maintenant ») ne récupère que 15 à 20 % du gain de la prévision parfaite à 24–72 h (+0,04 contre +0,22 à 4 m/s) : les heuristiques simples fondées sur le vent courant ou l'analyse lissée perdent l'essentiel de la valeur et ont besoin d'une prévision. (iv) Le point fixe B0 de S4 est optimal *a posteriori* sur l'année (biais de sélection, section 3.7) : le bénéfice réel de la mobilité avec un choix de site non rétrospectif est légèrement supérieur à 0,309.
:::

## 3.6 Prévisibilité (proxy du modèle de prévision v2)

**Méthode.** 39 instants d'émission (tous les 9 jours à partir du 6 janvier), 20 membres, échéances de 6 h jusqu'à 10 jours ; événement « $P_{hold} > 2$ MW en la cellule marine $x$ à l'échéance $L$ » ; prévision probabiliste = fraction de membres. Score de Brier (BSS) par rapport à (a) la fréquence climatologique annuelle, (b) la climatologie mensuelle ; comparaison à la persistance calibrée. ACC = corrélation d'anomalie du TWS (par rapport à la moyenne mensuelle).

| Échéance | 0 | 24 h | 48 h | 72 h | 96 h | 120 h | 168 h | 240 h |
|---|---|---|---|---|---|---|---|---|
| BSS prévision vs clim. annuelle | 0,88 | 0,76 | 0,69 | 0,63 | 0,54 | 0,46 | 0,39 | 0,24 |
| BSS prévision vs clim. mensuelle | 0,86 | 0,73 | 0,65 | 0,59 | 0,46 | 0,35 | 0,29 | 0,18 |
| BSS persistance calibrée | 1,00 | 0,02 | −0,03 | −0,05 | −0,05 | −0,02 | −0,02 | −0,05 |
| ACC TWS : contrôle / moyenne d'ensemble | 0,98 / 0,99 | 0,91 / 0,95 | 0,84 / 0,91 | 0,79 / 0,85 | 0,67 / 0,77 | 0,64 / 0,73 | 0,50 / 0,62 | 0,48 / 0,58 |
| ACC persistance | 1,00 | 0,23 | 0,07 | 0,05 | −0,07 | 0,04 | −0,07 | −0,06 |
| RMSE TWS contrôle / moy. ens. / persistance [kn] | 1,4 / 1,0 / 0 | 3,2 / 2,3 / 8,4 | 4,1 / 3,0 / 9,3 | 5,2 / 4,1 / 9,7 | 6,6 / 5,1 / 10,0 | 7,1 / 5,5 / 9,5 | 9,3 / 7,1 / 9,8 | 9,8 / 7,6 / 10,0 |

: Compétence du modèle de prévision v2 pour l'événement « vent productif » et pour l'anomalie de TWS.

![BSS, ACC et RMSE en fonction de l'échéance : prévision v2, persistance, climatologie.](fig/w_a5_predictability.png)

- La persistance de l'événement perd toute compétence par rapport à la climatologie après 24 h (BSS 0,02), ce qui correspond aux temps de décorrélation de 17 à 22 h (ACF 0,25 à 24 h) ; le modèle de prévision garde un BSS ≥ 0,46 (climatologie annuelle) jusqu'au jour 5 et 0,24 au jour 10. L'ACC du contrôle passe sous 0,6 à 144 h, celui de la moyenne d'ensemble à 180 h. Taux de détection de « $p > 0{,}5$ » : 0,93 (24 h), 0,89 (72 h), 0,84 (120 h), 0,77 (240 h), contre 0,63–0,65 en prévoyant toujours le mode climatologique. Par saison, le BSS à 10 jours vaut 0,28 (DJF), 0,19 (MAM), 0,15 (JJA), 0,35 (SON) ; la saisonnalité de la compétence est faible par construction (amplitude de déplacement de ±15 %).
- La prévision reste compétente 5 à 10 jours, soit 5 à 10 fois plus longtemps que le temps d'e-folding de 17 à 22 h et 3 à 5 fois plus longtemps que le temps de passage des taches (1 à 3 jours).

::: {.cal .safe}
[RÉSERVE ESSENTIELLE]{.lab}
**Ce résultat est une propriété du modèle de perturbation, non une mesure indépendante.** La prévision est la vérité déplacée (écart efficace de 40 km à D1 jusqu'à environ 250 km à D7), modulée en amplitude et bruitée : elle contient *toujours* la structure réelle des tempêtes (H-X-1), et la loi d'erreur est étalonnée sur des cibles hypothétiques de RMSE d'un ensemble opérationnel (2 à 3 m/s à D2, etc., H-2-22), non ajustée à de vraies prévisions. Le modèle reproduit donc **par construction** l'horizon utile de la v1 (« D5-6 déterministe, D8-10 probabiliste » : ACC de 0,6 à D6 et D7,5) et ne peut ni le réfuter ni le confirmer (H-2-23 reste ouvert). En réalité, il n'y a pas de compétence sur les systèmes individuels à D8-10 ; un meilleur proxy de la compétence réelle est le BSS à 3-5 jours (0,5 à 0,6) et le gain de la moyenne d'ensemble sur le contrôle (facteur 1,3 à 1,4 en RMSE, artefact du modèle échangeable, H-X-2).
:::

::: {.cal .key}
[CONSÉQUENCES]{.lab}
(i) Le seul horizon où la politique possède un avantage informationnel net sur « climatologie + persistance » est de 1 à 5 jours ; au-delà d'environ 5 jours le modèle (et, plus encore, la réalité) est proche de la climatologie, ce qui soutient une valeur terminale climatologique après 5 jours (S4 : +2,8 %). (ii) L'information de décision optimale (meilleure cellule à 300–700 km pour 1 à 3 jours) est dans la plage de prévision crédible : la valeur physique de la mobilité (section 3.5) est captable avec des prévisions de 24 à 72 h ; la valeur d'ensembles à D5-10 devrait être faible, en accord avec S4 (+1,2 %). (iii) Des archives de prévisions réelles (reprévisions GEFS, ensemble ECMWF) sont nécessaires pour étalonner la courbe de compétence avant toute conclusion sur les horizons (chapitre 9).
:::

## 3.7 Bruit d'échantillonnage et limites d'une seule année

- $\mathrm{CF}_{hold}$ mensuel au meilleur point fixe de S4 : 0,78 (janvier), 0,35 (juillet), 0,63 (décembre) ; écart-type mois à mois de 0,13 brut et 0,055 après retrait d'un cycle saisonnier à deux harmoniques (cellule médiane du bassin : 0,126 brut, 0,058 résiduel ; étendue du $\mathrm{CF}$ mensuel moyen du bassin 0,31–0,60).
- Fenêtres de 30 jours : écart-type résiduel de 0,052 (cellule médiane), 0,056 au point de départ de S4 ; la moyenne de six fenêtres de 30 jours a une erreur standard d'environ 0,021 si elles sont indépendantes : les comparaisons sur 3 à 6 fenêtres ne peuvent donc pas résoudre des écarts inférieurs à 2–4 points (H-4-26).
- $\mathrm{CF}_{hold}$ annuel : erreur standard de 0,015 au point de S4 par bootstrap par blocs mobiles (blocs de 7 jours, stratifiés par mois), 0,016 en médiane par cellule, 0,006 pour la moyenne du bassin. Environ 65 échantillons synoptiques effectifs par saison ($92 \times 24 / (2 \times 17)$) : une moyenne saisonnière n'est déterminée qu'à ±0,02–0,03 par l'échantillonnage seul, et **la variabilité interannuelle** (phase de l'oscillation nord-atlantique, blocages) **n'est pas échantillonnée du tout**.
- Stabilité du motif spatial dans l'année : corrélation de rang de Spearman du $\mathrm{CF}$ par cellule entre DJF et JJA 0,79 ; entre janvier-juin et juillet-décembre 0,87 ; mois pairs contre mois impairs 0,89.
- **Biais de sélection du meilleur point fixe** : la cellule la meilleure les mois pairs réalise 0,521 les mois impairs, alors que la cellule meilleure les mois impairs y atteint 0,605 : choisir la meilleure cellule avec les mêmes données coûte 0,08 d'optimisme en échantillon (demi-années). Sur l'année pleine, l'optimisme de B0 est probablement de 0,02 à 0,04 : la référence de tenue d'un exploitant non clairvoyant est inférieure à 0,571 et l'avantage du routage (+0,31 dans S4) est légèrement *sous-estimé*.

## 3.8 Réserves (relues avec méfiance)

1. **Résolution et lissage (40 km, horaire).** La grille native d'ERA5 est d'environ 31 km (résolution effective de 3 à 4 pas de grille), rééchantillonnée à 40 km. Les échelles inférieures à environ 150 km (fronts, rafales convectives, dépressions polaires) sont absentes ; le vent est une moyenne de maille, donc la puissance évaluée sur celui-ci n'a pas la variance sous-maille. Pour une courbe de puissance convexe (sous le coude) cela *sous-estime* la production (Jensen : +19 % à 14 kn et −15 % à 20 kn pour un écart-type de 4 kn, H-2-9) ; au-dessus du coude (≥ 22 kn) elle la surestime un peu. L'effet net sur $\mathrm{CF}_{hold}$ est de l'ordre de ±0,02 de signe inconnu. Le pas de 40 km ne résout pas les fronts de 3 h/40 km : le nombre d'épisodes courts est biaisé à la baisse.
2. **Biais du vent à 10 m d'ERA5.** ERA5 sous-estime les vents océaniques forts (la v1 avance 5 à 10 % ; à vérifier contre ASCAT et les bouées, non testable ici). Sensibilité à partir de la courbe de tenue (tout le vent mis à l'échelle) : TWS × 0,95 / 1,05 / 1,10 donne un $\mathrm{CF}_{hold}$ de bassin de 0,422 / 0,480 / 0,507 (contre 0,452), un $\mathrm{CF}$ au point de S4 de 0,546 / 0,596 / 0,618 (contre 0,572), une part productive de 33,8 / 42,0 / 45,8 % (38,0 %) et une part de calme de 22,9 / 18,9 / 17,2 % (20,8 %). Un biais de 5 % déplace donc le $\mathrm{CF}_{hold}$ de ±0,03 et la part productive de ±4 points ; la valeur de la mobilité (+0,22 à +0,25) y est peu sensible puisque c'est une différence. Des extrêmes sous-estimés font que la part au-dessus de 26 kn (14 %) est un minorant : **la question de la survie est plus sérieuse que ne le suggère ERA5**.
3. **Une seule année (2015).** Cartes, périodes de retour, vitesses d'advection et sites choisis a posteriori pourraient différer une autre année ; les conclusions relatives (échelles spatiales, part de la mobilité, lagrangien < eulérien) sont attendues plus robustes que les niveaux absolus (CF, saisons).
4. **Hypothèses du modèle de puissance de tenue.** Vent instantané (1 h), pas de vagues ni de courant, pas de coût de manœuvre (pertes de virement/empannage 4 à 15 %, H-4-30), pas de bruit de polaire, pas de plafonnement au-delà de 50 kn. Le plateau de 3 MW n'est pas atteint par la courbe de tenue (2,5 MW à 26 kn) : « productif » ($P_{hold} > 2$ MW) correspond à TWS ≈ 19 kn et non au seuil de 22 kn de la navigation libre. Les oracles DP ne facturent aucune énergie de déplacement, supposent une autonomie illimitée en mer, des pas de 3 h, un disque de rayon $v\,\Delta t$ sur un réseau de 40 km (rayon 1,08 cellule à 4 m/s : grossier ; 2 m/s non résolvable), une côte réduite au masque de mer et aucune contrainte de port ; « atteignable » est une portée en ligne droite, non un chemin routé. **Les gains de mobilité sont donc des bornes supérieures** de ce qu'un navire réel peut capter (coût de manœuvre, branches au près induites par le trajet ; à 4 m/s la production du navire à TWA 90–150° est cependant meilleure qu'en tenue, ce qui compense en partie).
5. **Estimation de l'advection.** Les vitesses de motifs sont obtenues par corrélation croisée d'anomalies dans des blocs de 800 km, non par suivi de cyclones individuels : elles lissent plusieurs objets, mêlent advection et croissance/décroissance et sont limitées à ±12 cellules par pas (43 kn à 6 h). Les tests lagrangiens utilisent cette vitesse locale, dont les erreurs pénalisent le suiveur ; une analyse par objets suivis pourrait donner un résultat plus favorable à 12–24 h (mais la probabilité de rester resterait une référence solide).
6. **Modèle de prévision par perturbation.** La compétence de la section 3.6 est une propriété du modèle et optimiste à D5-10 ; elle ne peut valider les horizons de la v1. Les vraies prévisions devraient perdre les systèmes individuels à D7-8, avec une structure saisonnière peut-être différente. L'ensemble est échangeable par construction.
7. **Biais de sélection** dans les points fixes choisis a posteriori (S4 ; la meilleure cellule de l'analyse au bord de la boîte) et dans les maxima « à prévision parfaite » sur de nombreuses cellules (3.5.1) : les deux gonflent la valeur apparente de la mobilité par rapport à une politique causale ; le routage en boucle fermée de S4 (0,80 contre 0,88 pour l'oracle) est la mesure causale.
8. **Troncature de la boîte.** La boîte ERA5 (32°O–5°E, 38–65°N) coupe la zone productive de la trajectoire des tempêtes (meilleure cellule au bord ouest) ; les gains de mobilité à longue distance (> 1000 km) sont en partie limités par les bords ; la zone de la v1 (45°O–5°E) est plus large.

## 3.9 Verdict sur les affirmations météorologiques de la v1

| Élément de la v1 (paraphrase) | Verdict | Éléments de preuve |
|--------------------------------|----------------------|----------------------------------------------|
| **H-1-1 / H-2-1** : les dépressions se déplacent à 20–35 kn, 4 à 6 fois plus vite que le navire, qui ne peut donc que se trouver sur leur trajectoire, jamais les chasser | **Confirmé en nature, surestimé en facteur** | vitesse médiane des motifs 18,7 kn (productifs), 23 kn en DJF, 13 kn en JJA ; 33 % des motifs > 20 kn ; rapport au navire de 4 m/s ≈ 2,4 (DJF ≈ 3), à 8 m/s ≈ 1,2–1,5 ; suivre un système ≥ 18 h est pire que rester (0,50 contre 0,57 à 24 h ; 0,39 contre 0,52 à 48 h) |
| Récolte « en dérivant vers l'est » (mobilité le long du vent), type H-2-3 | **Réfuté pour l'oracle** | le chemin de l'oracle n'est pas aligné avec le mouvement des systèmes (cos 0,1 ; 44 % à contre-sens) |
| **H-2-17** : vent moyen de la zone de référence (DJF 20–24, MAM 16–20, JJA 11–15, SON 16–22 kn) | **Confirmé** (JJA 15,1 légèrement au-dessus) | 22,9 / 17,2 / 15,1 / 18,1 kn |
| **H-2-18** : modulation saisonnière de l'énergie disponible de 2 à 3 | **Nuancé** | rapport hiver/été du $\mathrm{CF}_{hold}$ de 1,8 à 1,9 (puissance moyenne de tenue 1753 contre 979 kW) |
| **H-2-16** : zone de récolte 42–55°N / 10–35°O | **Réfuté / nuancé** | meilleures cellules à 55–60°N et au bord ouest de la boîte, $\mathrm{CF}$ 0,52 contre 0,46 à 45–50°N |
| **H-2-23** : horizon utile D5-6 déterministe / D8-10 probabiliste | **Non testable / cohérent par construction** | proxy bâti sur la même hypothèse |
| **H-2-22 / H-2-24** : des erreurs de phase de ±6 à 12 h à D2-5 détruisent un rendez-vous | **Non testé directement ; plausible** | temps de passage d'une tache 35 h en médiane (18–89 h) : 6 à 12 h d'erreur = 15 à 30 % |
| **H-2-26** : ERA5 sous-estime les vents forts de 5 à 10 % | **Non testable ici ; impact quantifié** | +5 % de vent = +0,03 de CF, +4 points de part productive |
| **H-1-2** : le routage doit battre le meilleur point fixe largement | **Confirmé** (dans l'environnement) | mobilité avec prévision parfaite +0,22 à +0,25 ; 71 à 80 % de l'avantage de l'oracle S4 |
| **H-2-20** : « le navire doit rester dans la zone productive ; persistance des régimes de 6 à 12 jours » | **Non étayé par la persistance eulérienne à 40 km** | épisodes productifs de 11 h en médiane ; 4 % ≥ 72 h ; e-folding spatial/temporel de 450–650 km / 17–22 h ; mémoire longue uniquement dans la queue (0,1–0,2) de l'autocorrélation de l'indicateur (saisonnière) |

: Verdict sur les éléments météorologiques de la note v1.

**Autres résultats de cette analyse pour le registre.** (a) La valeur de la mobilité est concentrée dans les premiers 300 à 650 km (50 à 70 % du gain). (b) La relocalisation fondée sur la persistance récupère 15 à 20 % du gain de la prévision parfaite à 24-72 h. (c) La DP sur $\mathrm{CF}_{hold}$ reproduit les valeurs mensuelles de B0 dans S4 (validation croisée des deux). (d) L'estimation sur une seule année de la zone optimale est tronquée par la boîte.


# 4. Revue des hypothèses du v1

## 4.1 Méthode

La note v1 contient des centaines d'affirmations, de choix et de chiffres, dont certains conditionnent le dimensionnement et l'architecture. Plutôt que de discuter les plus visibles, nous avons **établi un registre exhaustif** et attribué à chaque entrée un test.

**Construction du registre (WP1).** Chaque affirmation, hypothèse, valeur annoncée, décision de conception et alternative écartée de la note v1 a été extraite et paraphrasée (la note est confidentielle ; aucun passage n'est recopié). Les sources de rapprochement sont les revues et résultats des sprints S0 à S4, le contrat de conventions du dépôt et quelques calculs de revue sur le cache ERA5 2015 et la polaire BETA (vent de la zone de référence, forme et coude de la polaire, rapport de Jensen, première approche des 72 premières heures). Chaque entrée porte les champs suivants :

| Champ | Contenu |
|--------------|--------------------------------------------------------------------------------------|
| Référence | `H-<chapitre v1>-<n>` ; `H-X-<n>` pour les hypothèses sur *notre* environnement |
| Catégorie | météo, prévision, navire/polaire, fonction de valeur, choix d'algorithme, discrétisation, numérique, flottille, opérations, risque, structure du problème |
| Type | hypothèse, valeur annoncée, décision de conception, alternative écartée |
| Criticité | haute, moyenne, faible : l'effet d'une erreur sur l'architecture, le dimensionnement ou la valeur du projet |
| Énoncé | paraphrase de l'affirmation de la v1 |
| Preuve à ce jour | ce que S0-S4 et S5 montrent déjà, avec chiffres et sources |
| Test | l'expérience (E-xx) ou l'analyse qui peut confirmer ou réfuter, avec son coût (peu coûteux, moyen, coûteux) |
| Statut | ouvert, confirmé, contredit, non testable ici ; après la campagne : confirmé, réfuté, nuancé, non testable |

: Structure d'une entrée du registre.

Le registre compte **119 entrées** : 47 hypothèses, 39 valeurs annoncées, 21 décisions de conception, 12 alternatives écartées ; 36 de criticité haute, 67 moyenne, 16 faible ; 52 tests peu coûteux, 56 moyens, 11 coûteux. Vingt-quatre expériences (E-01 à E-24) ont été définies pour couvrir les entrées ouvertes ou contredites de criticité haute ou moyenne (section 5.2).

::: {.cal .req}
[RÈGLES DE LECTURE]{.lab}
(1) « Contredit » signifie *contredit par ce que S0-S4 (ou l'arithmétique de la revue S5) montrent dans notre environnement de test*. Plusieurs entrées contredites (valeur de l'ensemble, affirmation des deux couches, terminal a posteriori) dépendent de notre loi d'erreur de prévision et ont une faible puissance statistique ; elles sont signalées comme telles et re-testées par la campagne. (2) Les chiffres sont toujours donnés avec leur population (nombre de missions, de mois, de graines). (3) Un écart inférieur à 2–3 % est, par la règle de la v1 elle-même, « non significatif » : nous appliquons la même règle à nos propres résultats (section 8).
:::

**Exigence de preuve pour la mise à jour des statuts (WP5).** À l'issue de la campagne, chaque entrée testée recevra un verdict selon la règle « confirmer / réfuter » de son expérience (par exemple : confirmer l'utilité de l'ensemble si l'écart ENS − B1c croît de façon monotone jusqu'à au moins +2 points à échelle d'erreur ≥ 2 et reste ≥ +1 point à l'échelle 1 ; réfuter si l'écart reste inférieur à 0,5 point pour toutes les échelles). Les effets sont rapportés en points de facteur de charge et en kWh, avec intervalles de confiance par bootstrap par blocs hebdomadaires et trois graines de prévision pour tout facteur dépendant de la prévision. Le générateur `tools/hyp_table.py` de ce dépôt relit le registre à chaque construction du document : les tableaux de ce chapitre et des annexes B et C suivent donc automatiquement les nouveaux statuts.

## 4.2 État du registre

{{include: generated/hyp_summary.md}}

Les effectifs ci-dessus intègrent les verdicts de la campagne S5 (WP5) : les 69 entrées encore ouvertes après S0-S4 ont toutes reçu un verdict — 19 confirmées, 7 réfutées, 19 nuancées, 12 reportées faute de données (prévisions réelles, ERA5 pluriannuel, logistique de flottille) et 12 non testables dans notre environnement. Les preuves S5 sont citées dans la langue du registre (anglais) ; elles renvoient aux tableaux du chapitre 5.

## 4.3 Hypothèses de la v1 déjà contredites ou nuancées

Le tableau ci-dessous reprend les contradictions les plus importantes, avec la mesure qui les fonde. Le détail complet de chaque entrée, avec sa preuve, est en annexe B.

| Réf. | Affirmation de la v1 (paraphrase) | Ce que nos mesures montrent |
|-------|--------------------------------------|-------------------------------------------------------|
| **H-2-4** | L'optimum de la polaire est étroit, au travers : plus de 2400 kW seulement entre 75 et 105° de TWA, puissance à 45° égale au tiers ou au quart de celle à 90° | Sur BETA, à 20 kn le pic est de 2756 kW à TWA 95° ; la puissance à 45° est voisine de 0 (non 1/3) ; au-dessus de 24 kn le plateau s'élargit et, à 35 kn, la plus grande partie du demi-plan sous le vent est productive. Étroit seulement sous 22 kn |
| **H-2-5** | Puissance de pointe de 1500 kW à 18 kn, 2100 à 20 kn, plateau de 3 MW vers 24-26 kn | BETA : 2008 kW à 18 kn, 2756 à 20, 2986 à 22, plateau à 2984 jusqu'à 50 kn ; loi cubique confirmée (exposant 3,0 de 14 à 20 kn) ; coude à 21-22 kn |
| **H-2-6** | La puissance nette est fortement négative près du vent, d'où un prix explicite du rappel au vent | Max sur $U$ à TWA ≤ 45° : −1 à −43 kW (≈ 0) ; seuls des nœuds individuels atteignent −3500 kW. Le « prix » est un coût d'opportunité de production perdue, non un prix explicite |
| **H-2-14** | La polaire plafonne ou coupe en vent fort (dès 35 kn, coupure à 42 kn) | La polaire réelle BETA inclut déjà la limite du générateur, sans plafonnement de 22 à 50 kn ; le plafonnement n'existe que dans notre polaire synthétique. Si le navire réel plafonne, les routeurs réglés sur BETA surévaluent les secteurs de tempête |
| **H-2-16** | Zone de récolte naturelle 42–55°N / 10–35°O, meilleur point fixe près de 48–52°N / 12–18°O | Meilleur point hauturier de 2015 : 56,5°N / 21,6°O ; le $\mathrm{CF}$ des cellules à 55–60°N (0,52) dépasse celui de 45–50°N (0,46) ; l'optimum est tronqué par la boîte |
| **H-3-3** | La valeur de l'information parfaite (EVPI) est de 15 à 40 % de l'énergie totale | Meilleur causal (ENS_REF) à 8,3 % de la borne approchée sur 2015 ; 3,4 à 5,7 % en S3 ; 10 à 13 % en synthétique. La borne étant approchée, l'EVPI vraie est supérieure ou égale. Faible parce que le plateau BETA rend le navire peu sensible au moment |
| **H-3-9** | Un petit poids de CVaR est justifié par les queues sous-échantillonnées | S2 : −11 MWh en moyenne, aucun bénéfice de queue ; S3-S4 utilisent $\gamma = 0$. Preuve vide faute d'étalement dépendant du régime |
| **H-4-7** | Le biais de clairvoyance est spatialement hétérogène et déforme la politique | Biais relatif de 11,8 à 23,5 % mais biais absolu de 30 à 43 MWh presque uniforme ; η² = 2,4 % ; le critère de la v1 (« petit et homogène → facteur constant ») est en partie rempli |
| **H-4-8** | Utiliser des valeurs a posteriori en terminal est une erreur de nature ; seule une valeur apprise *policy-consistent* donne des arbitrages non biaisés | Boucle fermée sur 3 mois : $V_\theta$ +0,6 point, apprise a posteriori +0,4 point, par rapport à B1c (tous deux non significatifs) ; classement équivalent dans une même émission. Faible puissance (3 mois, une graine) |
| **H-4-10** | Un terminal climatologique brut est un simple repli | +2,8 % (10 mois sur 12 ; $t = 2{,}6$) par rapport au terminal nul ; $V_\theta$ ajoute +0,6 point (non significatif). Réserve : la climatologie vient de 2015 elle-même (fuite d'année) |
| **H-4-12** | 6 à 8 scénarios avec agrégateur CVaR surpassent nettement le MPC déterministe | S3 : +3,9 % sans raffineur, +1,4 % avec, +0,65 % avec terminal climatologique apparié ; S4 : ENS_REF +1,2 % (9 mois sur 12, $t = 1{,}0$), une seule graine. La valeur dépend de notre loi d'erreur |
| **H-4-14** | L'approximation en deux étages (tronc de 48 h, recours libre ensuite) est conservatrice | Le recours après $T_b$ est une *relaxation* (chaque scénario connaît son futur), donc optimiste en maximisation ; optimisme de plan de +30 % pour ENS, autant que B1 à 15 jours. Le raisonnement de la v1 est inversé |
| **H-4-21** | Le stencil compte environ 55 voisins pour des mailles de 45 km, des pas de 3 h et 8 m/s | $U_{max}\,\Delta t = 86$ km = 2,2 cellules de 40 km : un rayon de 3 cellules est inatteignable ; $K = 21$ (écarts angulaires jusqu'à 26,6°, ≈ 6 % de dépendance à l'orientation), puis arcs macro $K = 49$ (écart maximal de 18,4°) |
| **H-4-26** | Environ soixante hivers indépendants pour entraîner et valider la fonction de valeur | Incohérence interne : reprévisions GEFS 2000-2019 = 20 hivers, ERA5 depuis 1979 ≈ 45 ; nous avons **une** année (12 mois corrélés). Par la règle de la v1, nos effets (ENS +1,2 %, $V_\theta$ +0,6 point, terminal +2,8 %) sont sous le seuil |
| **H-4-35** | Le coefficient de rappel vaut 10–11 kWh par mille et par heure, soit 0,7 % du gain par 100 NM | Arithmétique corrigée : crochet de 1100 kW (non 2100) ; coefficient de 4,2 kWh/NM/h ; 1,3 % du gain de cœur par 100 NM. Erreur d'un facteur 2,5 sur une grandeur qui pilote l'intensité du rappel |
| **H-5-2** | Une passe d'itération de politique coûte de « quelques centaines » à 1500 heures-cœur | Incohérence interne (5000 × 3–10 min = 250–830 heures-cœur ; 1e5 × 10 min = 17 000). Mesuré : B1c_5d_REF ≈ 5 min CPU par mission de 30 j, ENS_REF ≈ 30 min ; avec ENS+REF le jeu d'entraînement coûte ≈ 6 fois l'estimation de la v1 |
| **H-6-3** | L'erreur de discrétisation est de quelques dixièmes de pour cent, négligeable devant l'erreur de prévision | Mesuré : 6 % de dépendance à l'orientation (S1), 3 % de la valeur (le plan DP réalise 97,4 % de la valeur de la DP), raffineur +3 à +7 %, Oracle_REF − Oracle = +47 à +75 MWh/30 j. Si c'était vrai, la priorité « tout est dans la prévision » serait partiellement fausse à 40 km / 3 h |
| **H-8-2** | B1 (MPC déterministe à 5 jours, terminal nul) quantifie la valeur de toute la structure long terme | B1 à 5 jours est déjà anticipatif (regret 11,5 à 11,9 %) ; la structure long terme (terminal, ensemble) n'ajoute que +2,8 % (climatologie) et +1,2 % (ensemble) |
| **H-8-6** | Une DP a posteriori sur la météo réalisée est une borne supérieure de toute politique causale | La DP à 3 h est battue par les politiques raffinées jusqu'à 3,9 % (S3) ; Oracle_REF_H est une borne *approchée* (15 jours + terminal climatologique) : tous les regrets en héritent |

: Principales hypothèses de la v1 contredites ou nuancées par S0-S4 et S5.

::: {.cal .key}
[CE QU'IL FAUT EN RETENIR]{.lab}
Les contradictions se répartissent en trois familles : **(a) la physique du navire** (polaire plus plate que décrite, plateau sans plafonnement, coude à 21-22 kn) ; **(b) l'arithmétique et les dimensionnements** (stencil, coefficient de rappel, coût d'entraînement, nombre d'hivers) ; **(c) la valeur des couches sophistiquées** (ensemble, fonction de valeur apprise, valeur d'information parfaite), dont la contribution mesurée est petite *dans notre environnement* et statistiquement fragile. La famille (c) est celle que la campagne doit trancher.
:::

## 4.4 Hypothèses de la v1 confirmées à ce jour

Douze entrées sont confirmées par S0-S4 :

- **H-1-2** : le routage doit battre le meilleur point fixe de beaucoup (écart d'environ 40 %, 12 mois sur 12) ;
- **H-2-7** : la production exige du mouvement (optimum à 6–9 kn) ; la tenue de position est une suite d'amures au travers ;
- **H-2-17** : vent moyen de la zone de référence (section 3.9) ;
- **H-3-1** : la météo est exogène, le problème est un processus de décision markovien sans couplage action-observation, et la décomposition prévision/replanification perd peu en théorie ;
- **H-3-6** : les décisions ne dépendent de la valeur que par ses différences et gradients (une valeur au bon niveau mais au mauvais gradient est inutile) ;
- **H-4-4** : un raffineur continu sur 0-48 h consommant le champ de valeur stratégique ajoute plus de 1 % (mesuré : +3 à +7 %) ;
- **H-4-6** : la valeur a posteriori est biaisée à la hausse par rapport à une politique causale, avec un biais croissant avec l'horizon (+7 à +16 % à 2-5 jours, saisonnier de 9,5 % en hiver à 19,4 % en juillet) ;
- **H-4-29** : le raffineur converge en 1 à 3 s à chaud ;
- **H-5-7** : les cycles d'ensemble arrivent avec 5 à 7 h de retard, donc chaque replanification utilise le cycle précédent ;
- **H-6-2** : le noyau compilé traite 2 à 5e8 arcs/s sur 16 cœurs ;
- **H-6-11** : sans arc de tenue corrigé des manœuvres et de la dérive, la DP sur-immobilise le navire ;
- **H-8-5** : les quatre tests physiques unitaires (course en vent uniforme à ±1 %, front advecté, invariance à une constante, conservation du rang par raffinement de grille) valident l'implémentation.

## 4.5 Incohérences internes de la note v1 relevées

La revue a relevé, indépendamment de toute mesure, les incohérences suivantes dans la note v1 :

- l'arithmétique du coefficient de rappel (crochet de 2100 kW à corriger en 1100 kW ; 10–11 kWh/NM/h à corriger en ≈ 4,2 ; le « 0,7 % par 100 NM » ne correspond à aucune des deux versions) ;
- le nombre de voisins (≈ 55 dans trois sections, ≈ 30 dans la zone fine, 2,2 cellules de portée à 40 km) ;
- le nombre d'hivers (« une soixantaine » contre 20 hivers de reprévisions GEFS) ;
- le coût de l'apprentissage hors ligne (1e4 à 1e5 missions par passe, contre ≈ 5000 en annexe, contre « quelques centaines d'heures-cœur », contre 600 à 1500 heures-cœur) ;
- l'occupation du quai (60 à 100 % avec rotation de 1 à 2 jours, soit jusqu'à 111 %, contre un objectif de 75 à 85 %) ;
- l'interdiction ferme aux limites de survie contre une pénalité à la place d'une interdiction à 45 kn ;
- l'approximation en deux étages dite conservatrice, qui relâche en fait la non-anticipativité après $T_b$ ;
- la polaire : largeur de pic de ±20–25°, puissance à 45° égale au tiers ou quart de celle à 90°, et sommet plat de ±10–15° ne peuvent être vrais simultanément, et aucun ne correspond à BETA ;
- la reprévision a 5 membres, alors que l'exploitation regroupe 51 membres en 6 à 8 médoïdes ($k > N$ hors ligne).

## 4.6 Les points ouverts les plus critiques

Les entrées de criticité haute encore **ouvertes** ou fragiles les plus lourdes de conséquences sont les suivantes.

| Réf. | Sujet | Pourquoi c'est critique | Test |
|-------|------------------------------|---------------------------------------------|------------------|
| **H-X-1** | La prévision est la vérité perturbée ; elle conserve la structure réelle des dépressions à toute échéance | Peut gonfler l'intérêt des longs horizons et des ensembles | E-01, E-02, E-20 |
| **H-2-22** | La loi d'erreur de prévision (RMSE, phase, horizon de compétence) est hypothétique, jamais ajustée à de vraies prévisions | Tout ce qui touche à l'horizon, à l'ensemble et à la latence en hérite | E-20 (coûteux) |
| **H-4-13** | La moyenne d'ensemble comme champ central n'a jamais été testée ; dans notre modèle elle bat le contrôle d'un facteur 1,38 | Le gain ENS/B1 peut n'être que « moyenne > contrôle » | E-11 |
| **H-2-25** | Aucune information de dispersion dépendante du régime dans notre modèle | Angle mort structurel pour le $k$ adaptatif et le CVaR | E-02 |
| **H-4-1** | La valeur ajoutée de la couche hors ligne sur une DP en ligne unique à terminal climatologique n'est pas établie (0,797 contre 0,807 de CF) | Décision d'architecture à deux couches | E-04, E-08, E-12 |
| **H-4-30** | Le coût de manœuvre (4 à 15 % de pertes de tenue) n'était pas facturé par le simulateur | Biais inégal : B0 (97 % en tenue) et navire routé | E-09 |
| **H-9-1** | Aucune contrainte de survie dans le PoC ; la polaire ne plafonne pas jusqu'à 50 kn | Le CF de 0,80 peut inclure du temps de tempête | E-17 |
| **H-5-1** | Entraînement hors ligne sur reprévisions GEFS à 5 membres contre ensemble en ligne à 51 membres ($k$ = 6–8 > 5) | Rupture de l'ensemble d'information : la cohérence de politique est rompue | E-20 |
| **H-4-26** | Un seul hiver réel contre soixante supposés | La plupart des effets sont sous le seuil de détection | E-18, E-23 |

: Points ouverts critiques du registre (extrait ; la liste complète des 36 entrées de criticité haute est en annexe C).

**Ce que la campagne a tranché sur ces points critiques.** La valeur du routage contre le meilleur point fixe est confirmée et large (+21 points de CF sur les six fenêtres) ; la prévision d'ensemble n'apporte rien de mesurable au niveau d'erreur nominal ; l'horizon déterministe utile est de 3 jours, la valeur terminale prenant le relais ; les pertes de manœuvre sont négligeables (0,3 point, et non 4 à 15 %) ; la fuite de climatologie est réelle mais sans effet (±0,1 point). Restent ouverts faute de données : l'étalonnage du modèle d'erreur sur de vraies prévisions (le facteur dominant) et la généralisation à d'autres années (H-4-26, H-X-6).

## 4.7 Nos propres erreurs possibles

La revue ne s'est pas limitée à la v1. Les entrées `H-X-*` (14 au total) recensent les endroits où *nos* résultats pourraient être des artefacts de l'implémentation ou de l'environnement :

| Sujet | Ce qui pourrait être faux | Sens du biais | Tests |
|----------------------|--------------------------------------|-------------------------|---------------|
| Prévision construite à partir de la vérité (H-X-1, H-X-2, H-X-10) | La prévision conserve la structure réelle ; déplacement de 320 km à D10 pour des systèmes de ≈ 1000 km ; erreurs de phase à D4 de ≈ 3 h contre 6–9 h dans la v1 ; propriété d'échangeabilité (contrôle 1,38 fois moins bon que la moyenne) | Favorise probablement les longs horizons et les ensembles ; pourrait aussi *sous-estimer* l'ensemble si l'étalement réel porte beaucoup d'information | E-01, E-02, E-20 |
| Climatologie, point B0 et $V_\theta$ sur la même année (H-X-3, H-X-13) | Fuite d'information à voisinage mensuel ; la validation croisée « un mois laissé de côté » avec tampon de 5 jours ne retire que la fuite du même mois | Favorise B0 (conservateur pour le routage) et le terminal climatologique (gonfle +2,8 %) | E-18, E-15 |
| Grille de 40 km / 3 h, ERA5 lisse (H-X-4, H-6-3) | Résolution effective d'ERA5 d'environ 100 km ; variabilité méso-échelle absente ; discrétisation ≈ 3 % de la valeur | La vérité est plus facile que la mer réelle | E-07, E-19, E-13 |
| Pas de pertes de manœuvre, de courant ni de dérive (H-X-5, H-2-12) | B0 tient position 86 à 97 % du temps avec l'enveloppe | Inégal : B0 réel probablement pire (gain du routage plus grand), navire routé pénalisé par les changements de cap | E-09, E-24 |
| Une année, 12 mois autocorrélés, une graine d'ensemble (H-X-6, H-X-14) | *t* appariés à 4–11 degrés de liberté ; graine d'ensemble 2 abandonnée ; bruit mensuel de graine jusqu'à 143 MWh | Inconnu : faux positifs (+2,8 % du terminal) et faux négatifs (ensemble) | E-23, E-18 |
| Oracle approché (H-X-7, H-8-6) | Oracle_REF_H : 15 jours + raffineur + terminal climatologique ; la DP à 3 h est battue jusqu'à 3,9 % | Les regrets (8 à 12 %) sont des minorants | E-14 |

: Où nos propres résultats pourraient être des artefacts.

# 5. Sensibilités

La campagne de sensibilité (398 cas, 11-12 novembre 2026, code 54aadcb, données 23ccd01) est terminée. Chaque cas est enregistré dans le suivi d'expériences MLflow avec les versions du code et des données (empreintes SHA-256 des fichiers ERA5 et de la polaire), tous ses paramètres et ses résultats. Le tableau exhaustif est `docs/s5/sensitivity_table.md` ; ce chapitre en donne la lecture.

## 5.1 Protocole commun

**Scénario cible « bench-6 ».** Six fenêtres de 30 jours de 2015 débutant les 1er janvier, mars, mai, juillet, septembre et novembre, à partir du meilleur point hauturier annuel (56,5°N ; 21,6°O), sauf si le facteur étudié modifie le départ. La métrique est le facteur de charge moyen (en %) sur les fenêtres, avec comparaisons *appariées* et écart à Oracle_REF_H en points. Une variante « ens4 » (janvier, mai, juillet, novembre) est utilisée pour les ensembles, plus coûteux. La validation finale de HORIZON v2 est faite sur l'année persistante complète.

**Routeurs de référence.** R0 = B0 (meilleur point fixe) ; R1 = B1c_5d_REF (prévision de contrôle, DP à 5 jours, terminal climatologique, raffineur) ; R2 = ENS_REF (20 membres, 10 jours, $k = 6$, $\gamma = 0$, tronc de 48 h, raffineur) ; R3 = Oracle_REF_H (borne).

**Statistique.** Au moins trois graines de prévision pour tout facteur qui dépend de la prévision ; intervalle de confiance par bootstrap par blocs hebdomadaires ; taille d'échantillon effective tirée de l'autocorrélation ; analyse de puissance par simulation pour des effets de 1, 2 et 3 % (E-23). Les résultats sont donnés en points de facteur de charge **et** en kWh, jamais en regret seul.

**Environnement « v2 » par défaut.** Pertes de manœuvre facturées, paramètres de prévision nominaux, $d_{min}$ = 20 km, grille de 40 km. Les cas identiques après normalisation (valeurs par défaut écartées) sont partagés et calculés une seule fois ; chaque cas est reprenable (points de reprise tous les 10 jours).

## 5.2 Plan d'expériences

Les 24 expériences définies par le registre sont résumées dans le tableau ci-dessous. L'ordre de priorité est : (1) les expériences peu coûteuses et décisives sans nouvelle donnée (E-13, E-14, E-23, E-22, E-15, E-10, E-03, E-24, E-21) ; (2) le cœur de la campagne sur la loi de prévision et les choix de conception (E-01, E-02, E-04, E-09, E-12, E-11 sans raffineur, puis E-06, E-07, E-08, E-05) ; (3) les expériences à lancer en tâche de fond et à terminer en dernier car elles conditionnent la crédibilité de tout le reste (E-18 : ERA5 pluriannuel ; E-20 : prévisions réelles), puis E-16, E-17 et E-19 selon la capacité.

| Réf. | Expérience | Facteurs principaux | Hypothèses visées | Coût |
|------|----------------------|----------------------------------------|----------------------|----------|
| E-01 | Échelle d'erreur de prévision | échelle de déplacement, d'amplitude et de bruit {0, 0,5, 1, 1,5, 2, 3}, 3 graines | H-2-22, H-3-3, H-4-12, H-X-1 | moyen |
| E-02 | Structure du modèle de prévision (chasse aux artefacts) | dispersion dépendante du régime, rapport contrôle/moyenne, rétention de structure à $\ge$ 5 jours, amplitude saisonnière, cohérence d'émission | H-2-25, H-X-1, H-X-2 | moyen |
| E-03 | Latence et intervalle de cycle | latence d'ensemble {0 à 12 h}, de contrôle {0 à 6 h}, cycle {6, 12, 24 h} | H-5-7 | peu coûteux |
| E-04 | Échelle horizon × terminal | horizon {1 à 15 j} × terminal {nul, clim ×1 à ×3, $V_\theta$, valeur d'oracle} × prévision {contrôle, moyenne, scénarios} | H-2-23, H-4-1, H-4-10, H-8-2 | moyen |
| E-05 | Période de replanification et hystérésis | replanification {1 à 24 h}, seuil d'hystérésis {0 à 3 %} | H-5-8, H-8-4 | moyen |
| E-06 | Conception du raffineur et interface | fenêtre {0 à 72 h}, pas {15 à 60 min}, terminal {champ de valeur, point de passage, aucun}, DP fine sans raffineur | H-4-4, H-4-5, H-4-23 | moyen |
| E-07 | Convergence de discrétisation | $\Delta x$ {20 à 80 km}, $\Delta t$ {1 à 6 h}, portée du stencil, quadrature d'arc | H-1-4, H-4-21, H-6-3 | moyen |
| E-08 | Échelle de la fonction de valeur et robustesse | terminal {nul, clim, clim × $k$, a posteriori, $V_\theta$ itérations 1 et 2, oracle S2S}, bruit de niveau et de gradient | H-3-6, H-4-1, H-4-7 | moyen |
| E-09 | Coût de manœuvre | durée de manœuvre {0 à 10 min}, fraction perdue {0 à 0,6}, routeur nominal ou nul, longueur de branche | H-4-30, H-4-31, H-6-11 | moyen |
| E-10 | Erreurs de polaire et d'étalonnage du vent | échelle de puissance {0,9 à 1,1}, biais de vent {−1 à +1 kn ; ×0,9 à ×1,05}, décalage de TWA ±5° | H-2-15, H-2-26, H-X-8 | peu coûteux |
| E-11 | Conception de l'ensemble | membres {5 à 50}, $k$ {1 à $N$}, réduction, champ central, $\gamma$, tronc | H-2-9, H-4-12, H-4-13 | moyen |
| E-12 | Routeurs alternatifs et lignes de base | vorace sur puissance de tenue, climatologie lente, isochrones, NLP seul, DP à une couche, myope | D5 de la v1 | moyen |
| E-13 | Phénoménologie de la météo océanique | (chapitre 3 : *réalisée*) | H-1-1, H-2-1, H-2-20 | peu coûteux |
| E-14 | Qualité de l'oracle et EVPI | anticipation de l'oracle {5 à 30 j, année}, DP 3 h contre 1 h, optimisme plan-réalisé | H-3-3, H-4-6, H-8-6 | moyen |
| E-15 | Point de départ, B0 et domaine | départ {meilleur point annuel, 50°N 15°O, Lorient, 10 cellules aléatoires}, variantes de B0 | H-1-2, H-2-16, H-X-3 | peu coûteux |
| E-16 | Proxys de logistique de flottille | branches Lorient–cœur et retour, coefficient de rappel recalculé, décalage des départs | H-3-5, H-4-35, H-4-36 | moyen |
| E-17 | Sécurité et exposition au risque | heures par an au-dessus de 35, 40, 45 kn le long des trajectoires, rampe de pénalité | H-2-14, H-9-1 | moyen |
| E-18 | ERA5 pluriannuel | $\ge$ 10 années supplémentaires (au moins DJF et JJA) sur la grille de 40 km | H-4-26, H-X-3, H-X-6 | coûteux |
| E-19 | Résolution et échantillonnage temporel du vent | vérité à 0,25° natif, interpolation à 3 h/6 h, turbulence synthétique | H-7-1, H-X-4 | moyen |
| E-20 | Étalonnage sur de vraies prévisions | reprévisions GEFS v12 ou archive ECMWF, $\ge$ 8 dates de 2015 | H-2-22, H-2-25, H-X-1 | coûteux |
| E-21 | Échelle de calcul et modèle de coût | arcs/s par cœur, $N = 51$, zone fine de 10 km | H-1-3, H-5-2, H-6-2 | peu coûteux |
| E-22 | Audit d'intégrité du code et du simulateur | test de non-fuite, reproductibilité à 1 et 2 processus, pas contraints, repli IPOPT | H-6-10, H-X-11 | peu coûteux |
| E-23 | Protocole statistique | taille effective, bootstrap par blocs, puissance par simulation | H-4-26, H-8-1, H-X-6 | peu coûteux |
| E-24 | Dérive, abattement, courant | $k_L$ {0 à 0,05}, courant synthétique, biais de TWA de tenue | H-2-12, H-4-32 | peu coûteux |

: Les 24 expériences du plan S5 (E-13 est le chapitre 3 ; les autres sont en campagne ou en attente de données).

## 5.3 La campagne exécutée

La campagne WP4 est pilotée par un fichier de description (`scripts/s5/campaign.yaml`) relu à chaque cycle par la file de calcul, par niveaux de priorité (A : cœur ; B ; C ; D). Les expériences du niveau A comprennent : la base B1c et ENS (avec oracle et B0 dans le même environnement), l'échelle d'erreur de prévision (0, 0,5, 1,5, 2 pour B1c ; 0,5 et 1,5 pour ENS), la latence (0 et 12 h), les manœuvres (désactivées ; durée × 2,5), le raffineur (désactivé, 24 h, 72 h), l'horizon de la DP (3, 7, 10 jours), le terminal nul, le routeur à moyenne d'ensemble (10 membres et mélange de 72 h), les routeurs simples (vorace sur la puissance de tenue à 24 h de portée, vorace sur le vent maximal, DP à 10 jours sans raffineur) et la grille horizon × terminal. Les niveaux B et C ajoutent la période de replanification, la cohérence et la saisonnalité de la prévision, les erreurs de polaire, la marge côtière, l'étalement de l'ensemble, le nombre de membres, $k$, $\gamma$, la portée du stencil, le point de départ et la grille de 20 km ; les expériences de structure de prévision (E-02), d'évitement des tempêtes et d'anticipation de l'oracle à 30 jours sont ajoutées par l'orchestrateur.

## 5.4 Résultats par facteur

**Lecture.** Chaque variante change *un seul* réglage du routeur R1 (B1c) ou de l'environnement simulé. L'effet est la différence **appariée** de facteur de charge (mêmes fenêtres, même tirage de prévision), donnée en points avec son erreur-type ; $z$ = effet / erreur-type. Nous lisons $|z| \ge 2$ comme un effet réel et $|z| < 1$ comme du bruit. Plancher de bruit : deux tirages de prévision du même routeur donnent 79,9 % et 80,7 % ; d'une fenêtre à l'autre le CF varie de 70 à 92 %. Références : Oracle_REF_H **86,2 %**, R1 **79,9 %**, R2 (ENS) 80,2 %, moyenne d'ensemble 79,7 %, B0 **58,8 %**.

![Effet apparié de chaque réglage sur le CF de R1, en points (6 fenêtres de 30 jours de 2015 ; barre : intervalle de confiance à 95 % ; couleur : effet significatif, gris : dans le bruit).](fig/s5_tornado.png)

### 5.4.1 Qualité des prévisions (échelle d'erreur, structure, dispersion)

![Facteur de charge de R1 et R2 selon l'échelle de l'erreur de prévision (1 = nominale), avec l'oracle et le poste fixe optimal.](fig/s5_error_curve.png)

| Erreur de prévision | CF R1 [%] | Effet [pts] | $z$ | Écart à l'oracle [pts] |
|---|---|---|---|---|
| ×0 (prévision parfaite) | 85,0 | +5,2 | 5,0 | 1,1 |
| ×0,5 | 83,7 | +3,8 | 4,3 | 2,5 |
| ×1 (nominale) | 79,9 | — | — | 6,3 |
| ×1,5 | 76,0 | −3,9 | −4,0 | 10,2 |
| ×2 | 72,2 | −7,7 | −4,1 | 14,0 |
| déplacement / calage seul (même variance) | 81,3 | +1,7 | 1,5 | — |
| intensité + bruit seuls (même variance) | 69,2 | −10,4 | −2,9 | — |
| erreurs « analogues » (écarts ERA5 réels réutilisés) | 79,4 | −0,2 | −0,2 | — |

: Sensibilité de R1 à l'erreur de prévision.

**La prévision est le goulot, pas l'optimiseur.** Avec une prévision parfaite, R1 arrive à 1,1 point de l'oracle ; chaque « erreur nominale » supplémentaire coûte 7 à 8 points. **La nature de l'erreur compte autant que sa taille** : à variance égale, une erreur qui décale ou retarde les systèmes coûte peu (le navire peut attendre ou se repositionner), une erreur sur l'*intensité* du vent coûte 12 points de plus (le navire planifie sur un vent qui n'existe pas). R2 suit R1 point par point (83,9 / 80,2 / 76,4 % à ×0,5 / ×1 / ×1,5) ; il ne gagne que dans le régime d'erreurs d'intensité (+1,9 point). La cohérence d'une émission à l'autre ($-0,3$ point) et la modulation saisonnière de l'erreur ($+0,5$ point) sont dans le bruit ; la dispersion de l'ensemble (×0,6 / ×1,4) aussi, sur 4 fenêtres.

**Conséquence.** Les chiffres absolus de CF sont conditionnels au modèle d'erreur synthétique. L'étalonnage du partage *intensité / déplacement* sur de vraies prévisions archivées (reprévisions GEFS, ENS de l'ECMWF) est la première priorité de S5.x (E-20).

### 5.4.2 Latence et cycle de prévision

Latence nulle : +1,3 point ($z$ = 2,2) ; latence de 12 h : −0,5 point (bruit). La perte est de l'ordre de 0,1 à 0,3 point par heure au voisinage du nominal (4-6 h) : la latence n'est pas un levier majeur.

### 5.4.3 Horizon, valeur terminale, raffineur

| Variante de R1 | Effet [pts] | $z$ |
|---|---|---|
| horizon 3 j / 7 j / 10 j (nominal 5 j) | 0,0 / +0,9 / +0,4 | 0,0 / 2,1 / 0,8 |
| terminal nul, horizon 3 j / 5 j / 7 j / 10 j | −2,7 / −2,6 / −0,5 / +0,5 | −4,2 / −5,8 / −0,5 / 0,5 |
| sans raffineur | −2,9 | −7,7 |
| raffineur 24 h / 72 h (nominal 48 h) | +0,2 / +0,5 | 0,8 / 0,7 |
| replanification 3 h / 12 h / 24 h (nominal 6 h) | +0,3 / −0,7 / −1,4 | 0,7 / −1,7 / −2,1 |
| portée d'arc 1 / 3 (nominal 2) | +0,5 / +0,1 | 0,7 / 0,2 |

: Architecture du routeur.

Au-delà de 3 jours, la prévision déterministe n'apporte plus rien ; la **valeur terminale climatologique et l'horizon sont substituables** : avec 10 jours d'horizon, la valeur terminale est inutile, avec 3 à 5 jours elle vaut 2,6 points. Le **raffineur continu** vaut 2,9 points et une fenêtre de 24 h suffit. Replanifier toutes les 6 h est le bon compromis.

### 5.4.4 Manœuvres, polaire et vent

Facturer les manœuvres coûte **0,3 point** à R1 (2,5 manœuvres par jour) ; des manœuvres 2,5 fois plus longues, 0,4 point. B0 n'en fait aucune : l'avantage du routage n'en est pas affecté. Une erreur d'**échelle de la polaire réelle** de ±10 % déplace le CF de R1 de ±8,1 points ($|z|$ ≈ 20) mais laisse l'écart à l'oracle inchangé (5,7 à 6,9 points) : c'est un risque sur la *production*, pas sur le *routage*. Un décalage de ±10° de l'angle au vent coûte 2,2 à 3,5 points, à l'oracle aussi (−3,7 points).

### 5.4.5 Ensemble : membres, scénarios, risque

Sur 4 fenêtres : 10 membres +0,8 point ($z$ = 3,1), 40 membres +0,6 ; 3 ou 10 scénarios +0,9 / +0,5 ; aversion au risque $\gamma$ = 0,3 : +1,7 point ($z$ = 1,3). Aucun réglage ne change la conclusion : **au niveau d'erreur nominal, l'ensemble à deux étapes n'apporte rien de mesurable par rapport à la prévision de contrôle** et coûte 5 fois plus de calcul. Il reste l'outil adapté si les vraies prévisions s'avèrent dominées par les erreurs d'intensité.

### 5.4.6 Routeurs simples et alternatives

Les règles voraces sur la prévision (aller vers la meilleure cellule de puissance de tenue à 24 h ; chasser le vent maximal) donnent **33 à 34 %**, très en dessous du poste fixe (58,8 %). Le routage sur la moyenne d'ensemble (79,7 %) égale le contrôle. La DP à 10 jours sans raffineur fait 76,8 % (−3,1 points). La pile « DP + valeur terminale + raffineur » est donc justifiée, mais rien de plus sophistiqué ne l'est à ce stade.

### 5.4.7 Départ, discrétisation, sécurité, résolution

Grille de 20 km : +0,9 point (bruit) pour 3 fois plus de calcul. Marge côtière de 10 / 40 km : −0,3 / +0,7 point (bruit) ; aucune violation côtière dans l'ensemble des cas. Exposition au-dessus de 45 kn : 1 à 2 heures par fenêtre de 30 jours ; une pénalité au-delà de 45 kn ne change rien (+0,3). Départ de Lorient : −2,0 points sur 30 jours (transit) ; départ au milieu de l'Atlantique : +1,9 point, ce qui confirme que la boîte ERA5 (limite 32°O) tronque la zone utile.

## 5.5 Ce que nous attendons *avant* les résultats

Pour que les résultats puissent nous contredire, nous consignons ici les attentes tirées du chapitre 3 et de S0-S4, **avant** de voir les résultats de la campagne.

1. La valeur de la mobilité vient de l'accès au bon endroit dans un rayon de 300 à 700 km sur 1 à 3 jours : le CF devrait être **plus sensible à l'erreur de prévision aux échéances de 1 à 3 jours qu'à celle de 5 à 10 jours** ; l'ensemble à D5-10 devrait apporter peu.
2. Les heuristiques fondées sur le vent courant (« aller où il y a du vent ») devraient récupérer 15 à 20 % du gain de la prévision parfaite et être nettement battues par R1 ; un vorace sur une *prévision* de 48-72 h devrait être beaucoup plus proche.
3. Le terminal climatologique (+2,8 % mesuré) devrait rester utile ; sa valeur pourrait être gonflée par la fuite d'année.
4. La facturation des manœuvres devrait pénaliser davantage B0 (97 % du temps en tenue) que R1 : l'avantage du routage devrait **augmenter** légèrement.
5. Une erreur de polaire de ±10 % sur la puissance devrait déplacer les niveaux de CF mais peu le classement des routeurs.

## 5.6 Confrontation aux attentes

1. *Sensibilité aux échéances courtes plutôt qu'à D5-10* : **confirmée indirectement** (horizon au-delà de 3 jours inutile ; ensemble sans effet) ; l'échéance de l'erreur n'a pas été scannée séparément.
2. *Le vorace sur prévision serait proche de R1* : **réfutée** (33-34 % contre 80 %).
3. *Le terminal climatologique reste utile, peut-être gonflé par la fuite* : **confirmée** (+2,6 points) ; la part de la fuite est mesurée au chapitre 6.
4. *La facturation des manœuvres augmenterait l'avantage du routage* : **réfutée** (effet de 0,3 point ; la tenue de B0 n'entraîne pas de manœuvres facturées dans notre modèle).
5. *Une erreur de polaire déplace les niveaux, pas le classement* : **confirmée**.

# 6. HORIZON v2 : algorithme affiné

HORIZON v2 est un **affinement par élagage** du routeur v1 : il garde ce qui est mesuré utile, simplifie ce qui ne l'est pas et corrige ce qui était fragile. Aucune couche n'est ajoutée (le brief réserve les nouveautés à S6). Le routeur v2 est implémenté (`HORIZON_V2` dans `scripts/s5/s5lib.py`, construit par `horizon.config.HorizonConfig` / `make_policy`) et validé sur les six fenêtres (`docs/s5/v2_validation.md`) et sur l'année.

## 6.1 Principe de l'affinement

Chaque décision s'appuie sur une mesure appariée du chapitre 5 : on retire ou on raccourcit un élément si son effet est dans le bruit ($|z| < 1$ à 2) et si le retrait fait gagner en calcul ou en simplicité ; on garde un élément dont le retrait coûte un effet significatif ; on corrige ce qui rendait les résultats dépendants de la machine ou d'une information a posteriori.

## 6.2 Décisions

| Élément | v1 | v2 | Mesure qui fonde la décision |
|---|---|---|---|
| Horizon de la DP | 5 j | **3 j** | 3 / 5 / 7 / 10 j : 0,0 / réf. / +0,9 / +0,4 pt (bruit) |
| Valeur terminale | climatologie annuelle (fenêtre testée incluse) | **climatologie hors fenêtre** (*leave-window-out*) | sans terminal : −2,7 pt ($z$ = −4,2) ; fuite mesurée : ±0,1 pt |
| Raffineur continu | 48 h | **24 h** | sans raffineur : −2,9 pt ; 24 / 72 h : +0,2 / +0,5 (bruit) |
| Limites IPOPT | 200 itérations **et** 20 s CPU | **500 itérations, sans limite CPU** | convergence 100 % ; résultats indépendants de la charge |
| Replanification | 6 h | 6 h | 24 h : −1,4 pt ($z$ = −2,1) ; 3 h : rien |
| Prévision utilisée | contrôle | contrôle | ensemble = contrôle au niveau nominal, 5× plus coûteux |
| Fonction de valeur apprise $V_\theta$ | option | **retirée du défaut** | +0,6 pt non significatif (S4), coût hors ligne élevé |
| Grille, stencil | 40 km / 3 h, portée 2 | inchangés | 20 km : +0,9 pt (bruit) pour 3× le calcul ; portée 1/3 : bruit |
| Manœuvres, tempêtes | non modélisées dans le routeur | inchangé | pertes 0,3 pt ; > 45 kn : 1-2 h/mois, pénalité sans effet |
| Marge côtière | 20 km | 20 km en évaluation ; **30-40 km recommandés en exploitation** | 40 km : +0,7 pt (bruit), aucune violation |

: Décisions d'affinement HORIZON v2.

**Pistes de la révision précédente écartées.** Le champ central « moyenne d'ensemble » (79,7 % contre 79,9 % pour le contrôle) n'apporte rien ; le tronc de l'approximation à deux étages et les réglages de l'ensemble (membres, scénarios, $\gamma$) n'ont pas d'effet mesurable ; l'heuristique vorace (33-34 %) ne peut servir ni de routeur ni de repli, seulement de garde-fou en cas de perte de lien (à étudier en S6).

## 6.3 Spécification de HORIZON v2

**Entrées.** Prévision déterministe de contrôle (champ de vent à 10 m, horaire, au moins 3 jours d'échéance) ; polaire de puissance nette BETA (avec masques et réparation des trous, chapitre 2) ; enveloppe de puissance à cap mixte ; carte de distance à la côte ; climatologie de puissance de tenue $\bar P_{hold}(x)$ calculée sur les mois *hors* fenêtre d'exploitation.

**Toutes les 6 h :**

1. **DP déterministe** sur la grille LAEA de 40 km et des pas de 3 h, sur 3 jours, avec arcs macro de portée 2 (49 directions) et contrôle exact des cordes côtières ($d \ge d_{min}$). Valeur terminale à $T$ : $V_T(x) = \bar P_{hold}(x)\cdot \min(5\ \mathrm{j},\ \text{temps de mission restant})$.
2. **Raffineur continu** (CasADi / IPOPT, tir multiple, pas de 30 min) sur les 24 premières heures, initialisé par la trajectoire DP et terminé sur le champ de valeur DP à 24 h ; contraintes : enveloppe de vitesse, distance côtière (vérification bilinéaire exacte et resserrement local), 500 itérations au plus, aucune limite de temps. Si le raffineur n'améliore pas l'amorce, la trajectoire DP est exécutée telle quelle (compteur).
3. **Exécution** des 6 premières heures ; le simulateur facture les manœuvres et applique la garde côtière.

**Budget de calcul.** 2,4 min de CPU (un cœur) par fenêtre de 30 jours, soit environ 1,2 s par replanification, dont l'essentiel pour IPOPT. v1 : 5,8 min. Le chemin critique restant est le hessien exact du raffineur (65 % du temps IPOPT) ; la génération de code CasADi est la piste d'accélération suivante (3 à 5×, non tentée).

**Comportement de repli.** Pas de départ réalisable : maintien en position (compteur `n_hold_fallback`) ; raffineur non amélioré : trajectoire DP (`n_warm_start`) ; commande infaisable : vitesse réduite par le modèle de puissance (`n_clamped`) ; approche côtière : garde du simulateur (environ une intervention par fenêtre, aucune violation).

## 6.4 Réglage : simplicité et robustesse

| Paramètre | Défaut v2 | Plage sûre mesurée | Sensibilité dans la plage |
|---|---|---|---|
| Horizon DP | 3 j | 3 à 10 j | < 1 pt |
| Terminal | climatologie, 5 j | requis si horizon < 7 j | −2,7 pt sans |
| Raffineur | 24 h, 500 it. | 24 à 72 h ; 200 à 1000 it. | < 0,5 pt |
| Replanification | 6 h | 3 à 12 h | < 1 pt (24 h : −1,4) |
| Grille / portée | 40 km / 2 | 20-40 km ; 1-3 | < 1 pt |
| Marge côtière | 20-40 km | 10 à 40 km | < 1 pt |

: Paramètres de HORIZON v2 et robustesse.

Trois paramètres seulement portent un effet significatif hors de leur plage (valeur terminale, raffineur, période de replanification) ; tous les autres sont figés à leur défaut.

**Revue critique externe** (branche `s5-review`, intégrée) : treize constats, dont un de sévérité élevée sur la validité (raffineur non convergé accepté, limite de temps CPU) et quatre moyens (couverture d'horizon de la prévision, compteurs perdus à la reprise, replis silencieux, fuite de climatologie), tous corrigés ou neutralisés ; aucune erreur de convention (u/v, TWA, caps, unités). Mesure a posteriori : la limite CPU ne s'est jamais déclenchée pendant la campagne (résultats S5 identiques sans elle) et la fuite vaut ±0,1 point. Accélérations exactes intégrées : cache de faisabilité des arcs, sommes latentes en place, cache LRU des séries latentes (×1,2 sur B1c, plans identiques au bit près). Refactorisation : configuration unique `HorizonConfig` et fabrique `make_policy` pour tous les scripts.

# 7. Résultats typiques

## 7.1 Référence : le PoC v1 (S4)

La référence est la preuve de concept telle que close en S4 : navire médian de la flottille, **persistant toute l'année 2015** depuis le meilleur point hauturier (56,49°N ; 21,6°O), sans transit au port, prévision v2 (cohérence, latence, saisonnalité), grille de 40 km, pas de DP de 3 h, replanification toutes les 6 h, $d_{min}$ = 20 km. `Oracle_REF_H` est la borne approchée (anticipation de 15 jours, raffineur, terminal climatologique). Les erreurs de prévision sont un modèle de perturbation, non de la prévision numérique.

| Politique | Énergie [MWh] | CF annuel | Regret / Oracle_REF_H [%] | Durée [h] |
|------------------------------|----------------|--------------|------------------------|----------------|
| Oracle_REF_H | 23117 | 0,880 | 0,00 | 1,20 |
| B0 (meilleur point fixe) | 15008 | 0,571 | 35,08 | — |
| B1_5d_REF (graine 1) | 20376 | 0,775 | 11,86 | 1,09 |
| B1c_5d_REF (graine 1) | 20946 | 0,797 | 9,39 | 1,11 |
| B1c_5d_REF (graine 2) | 21002 | 0,799 | 9,15 | 1,11 |
| ENS_REF (graine 1) | 21199 | 0,807 | 8,30 | 6,14 |

: Référence S4 : facteur de charge annuel et regret, année persistante 2015 (durées sur une machine à 2 cœurs, 2 processus).

Pour toutes les exécutions : 0 violation de côte, 0 intervention de garde, 0 repli de la DP.

| Politique | Jan | Fév | Mar | Avr | Mai | Juin | Juil | Août | Sep | Oct | Nov | Déc | Année |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Oracle_REF_H | 0,943 | 0,920 | 0,918 | 0,898 | 0,904 | 0,836 | 0,769 | 0,819 | 0,848 | 0,843 | 0,917 | 0,946 | 0,880 |
| B0 | 0,784 | 0,691 | 0,701 | 0,557 | 0,593 | 0,461 | 0,352 | 0,418 | 0,437 | 0,566 | 0,675 | 0,626 | 0,571 |
| B1_5d_REF s1 | 0,896 | 0,755 | 0,827 | 0,771 | 0,835 | 0,722 | 0,670 | 0,667 | 0,766 | 0,761 | 0,836 | 0,797 | 0,775 |
| B1c_5d_REF s1 | 0,920 | 0,799 | 0,860 | 0,778 | 0,827 | 0,738 | 0,671 | 0,694 | 0,791 | 0,749 | 0,846 | 0,891 | 0,797 |
| B1c_5d_REF s2 | 0,894 | 0,870 | 0,883 | 0,776 | 0,835 | 0,726 | 0,607 | 0,683 | 0,812 | 0,774 | 0,867 | 0,871 | 0,799 |
| ENS_REF s1 | 0,922 | 0,866 | 0,891 | 0,801 | 0,844 | 0,673 | 0,676 | 0,746 | 0,753 | 0,765 | 0,843 | 0,902 | 0,807 |

: Facteur de charge mensuel des politiques de S4 (année 2015).

![Facteur de charge mensuel de S4 (graphique d'analyse S4).](fig/s4_monthly_cf.png)

**Comparaisons appariées** (écart d'énergie mensuelle, positif si la première politique est meilleure ; $n = 12$ mois) :

| Comparaison | Moyenne [MWh/mois] | Somme [MWh] | $t$ | Moyenne [%] | Victoires |
|---|---|---|---|---|---|
| ENS_REF − B1c_5d_REF | +21,0 | +252 | +1,0 | +1,23 | 9/12 |
| Terminal climatologique (B1c − B1) | +47,5 | +571 | +2,6 | +2,80 | 10/12 |
| Routage − B0 (B1c) | +494,9 | +5939 | +10,2 | +44,41 | 12/12 |
| Routage − B0 (B1) | +447,3 | +5368 | +8,6 | +40,70 | 12/12 |
| Routage − B0 (ENS) | +515,9 | +6191 | +12,1 | +45,78 | 12/12 |
| Effet de graine (B1c graine 2 − graine 1) | +4,6 | +56 | +0,2 | +0,23 | 6/12 |
| A posteriori − B1c | +180,9 | +2170 | +9,3 | +10,76 | 12/12 |

: Comparaisons appariées S4 (le « routage − B0 » est la moyenne des écarts relatifs mensuels).

![Résultats 2015 : facteur de charge mensuel, écart à l'oracle, bilan énergétique annuel, manque à gagner cumulé (graine 1).](fig/tech_results.svg)

**Départs de Lorient.** Missions de 14 jours le 1er de chaque mois à partir de Lorient (47,7°N ; 3,4°O) par le couloir portuaire : le CF moyen est de 0,713 avec B1c contre 0,780 pour le même navire déjà en mer sur les mêmes fenêtres, soit **68 MWh perdus par départ** ; le navire est à 50 km de la côte en moins de 5 h en médiane.

::: {.cal .note}
[À LIRE AVEC PRUDENCE]{.lab}
Les regrets mensuels d'une graine unique sont bruités : B1c graines 1 et 2 diffèrent jusqu'à 143 MWh en un mois alors que les totaux annuels s'accordent à 0,3 %. L'avantage annuel d'ENS_REF (+1,2 %, 9 mois sur 12, $t$ = 1,0) est dans le bruit de graine. La climatologie terminale est celle de 2015 elle-même (fuite d'année), comme le point B0. Les regrets d'un navire persistant (8 à 12 % par an) dépassent ceux des missions de 30 jours de S3 (3 à 6 %) : latence de la prévision, saison de vent faible (juin–septembre, CF de 0,67 à 0,80 même pour l'oracle) et nature approchée de l'oracle.
:::

## 7.2 HORIZON v2 sur le scénario cible

Environnement réaliste de S5 (pertes de manœuvre facturées, prévisions synthétiques nominales, $d_{min}$ = 20 km), six fenêtres de 30 jours de 2015, deux tirages de prévision pour les routeurs causaux. Écarts appariés sur les mêmes fenêtres.

| Routeur | CF bench-6 [%] | Écart à l'oracle [points] | Écart à v1-PoC [points] | Calcul par fenêtre |
|---|---|---|---|---|
| B0 (poste fixe optimal) | 58,8 | 27,4 | −21,1 | — |
| v1-PoC (B1c_5d_REF), tirages 1 / 2 | 79,9 / 80,7 | 6,3 / 5,4 | référence | 5,8 min |
| v1-PoC (ENS_REF), tirage 1 | 80,2 | 6,0 | +0,3 ± 0,7 (4 fenêtres) | 26 min |
| **HORIZON v2**, tirages 1 / 2 | **79,8 / 80,9** | 6,4 / 5,2 | **−0,1 ± 0,6 / +0,2 ± 0,6** | **2,4 min** |
| Oracle_REF_H (sans fuite, raffineur déterministe) | 86,3 | 0 | — | 4,8 min |

: Scénario cible bench-6.

HORIZON v2 égale v1 à 0,2 point près, en 2,4 à 3,9 fois moins de calcul, avec des résultats indépendants de la charge de la machine et sans information a posteriori dans la valeur terminale. Le raffineur converge dans 100 % des replanifications (v1 : 72 à 97 % selon la fenêtre).

## 7.3 HORIZON v2 sur l'année persistante

<span class="todo">[À COMPLÉTER S5-campagne]</span> Validation finale sur l'année complète 2015 : CF mensuel et annuel, comparaison appariée à la référence S4 du tableau ci-dessus, exposition aux vents forts (heures au-dessus de 35, 40 et 45 kn), départs de Lorient.

## 7.4 Lecture du comportement

<span class="todo">[À COMPLÉTER S5-campagne]</span> Trajectoires typiques (hiver, été), comportement dans un calme étendu, dans un coup de vent, à l'approche des limites de la boîte, et décisions de la replanification.

# 8. Limites, biais, et ce qui reste à prouver

Ce chapitre est volontairement sévère. Un résultat de routage obtenu en simulation est plus fragile qu'il n'en a l'air ; nous dressons ici la liste de ce qui, dans notre démarche, pourrait le rendre trop beau, trop laid, ou simplement indécidable.

::: {.cal .safe}
[CE QUE NOUS NE POUVONS PAS ENCORE AFFIRMER]{.lab}
Nous ne pouvons pas affirmer, aujourd'hui, que HORIZON produit un facteur de charge de 0,80 *en mer réelle*. Nous pouvons affirmer que, **dans un environnement simulé construit sur ERA5 2015, la polaire BETA et des prévisions perturbées**, un routeur causal obtient 0,78 à 0,81 contre 0,57 pour le meilleur point fixe, et que cet ordre de grandeur de l'avantage (+36 à +41 %) est robuste aux incertitudes que nous savons quantifier (biais de sélection de B0, biais de vent de 5 %) mais **pas** à celles que nous ne savons pas encore quantifier (loi d'erreur des vraies prévisions, plafonnement de la puissance en vent fort, manœuvres, état de mer).
:::

## 8.1 Limites de l'environnement de test

1. **Les prévisions ne sont pas des prévisions.** Elles sont la vérité ERA5 perturbée par une loi *hypothétique* (déplacement, amplitude, bruit), qui conserve la vraie structure des systèmes à toute échéance. Toute conclusion sur l'horizon utile, la valeur de l'ensemble, la latence et le terminal en hérite (H-X-1, H-2-22). Les vraies prévisions perdent les systèmes individuels vers D7-8, ont une dispersion qui dépend du régime (absente chez nous, H-2-25) et des erreurs de phase de 6 à 9 h dès D4 (nous : ≈ 3 h).
2. **Une seule année météorologique.** 2015 ne dit rien de la variabilité interannuelle (phase de l'oscillation nord-atlantique, blocages). Les 12 mois sont autocorrélés ; les tests appariés ont 4 à 11 degrés de liberté ; une moyenne saisonnière n'est connue qu'à ±0,02–0,03 de CF par échantillonnage seul.
3. **ERA5 est lisse.** Résolution effective de l'ordre de 100 km, vent de maille, rafales et fronts absents, extrêmes sous-estimés (5 à 10 % selon la v1, non vérifié). La vérité est plus facile que la mer réelle ; la part de temps au-dessus de 26 kn (14 %) est un minorant.
4. **Navire idéalisé.** Pas de vagues, pas de courant, pas de dérive prise en compte dans la plupart des essais, pas de bruit de polaire ; la polaire BETA est une sortie de VPP, non une mesure ; le secteur masqué comme bogue du VPP est un choix de l'équipe ; **la puissance ne plafonne pas jusqu'à 50 kn**.
5. **Pertes de manœuvre.** Absentes de S1-S4 (le simulateur n'a facturé ni virement ni empannage), introduites en S5 : tous les résultats de S4 sont à relire en conséquence. B0 (tenant 86 à 97 % du temps) et le navire routé sont affectés de façon inégale.
6. **Marge côtière.** Les violations résiduelles de S3 (18,9 et 16,8 km contre 20 km) ont été corrigées en S4 (0 violation) ; la marge est mesurée sur le modèle de côte à 10 km (Natural Earth 10 m), sans garde de navigation réelle.

## 8.2 Limites de la mesure

1. **L'oracle est approché.** Oracle_REF_H (15 jours + terminal climatologique) n'est pas une borne supérieure stricte : la DP à 3 h est battue par les politiques raffinées jusqu'à 3,9 %. Les regrets de 8 à 12 % sont donc des **minorants**.
2. **Biais de sélection et fuites d'année.** Le point B0, la climatologie du terminal et $V_\theta$ sont construits sur 2015 ; le point optimal est choisi a posteriori (optimisme probable de 0,02 à 0,04 de CF, ce qui sous-estime l'avantage du routage) ; la climatologie de 2015 sert de terminal à 2015 (ce qui surestime les +2,8 %).
3. **Faible puissance statistique.** Un écart de 1 à 3 % est sous le seuil de détection de nos données : effet de l'ensemble (+1,2 %), de $V_\theta$ (+0,6 point), du terminal (+2,8 %), du CVaR (non mesuré). Nous ne devons ni « confirmer » ni « réfuter » ces effets sur la base de S0-S4.
4. **Une seule graine d'ensemble.** La graine 2 d'ENS_REF a été abandonnée (budget CPU) ; la sensibilité à la graine n'est mesurée que sur B1c (0,27 % en annuel, jusqu'à 143 MWh en mensuel).
5. **L'année simulée a 8759 heures** (l'archive s'arrête à 23 h UTC), détail sans conséquence mais à connaître.

## 8.3 Limites de l'algorithme tel que prototypé

1. **L'approximation en deux étages est optimiste**, non conservatrice : chaque scénario connaît son futur après 48 h (optimisme de plan de +30 %).
2. **La valeur de la couche hors ligne ($V_\theta$) n'est pas établie** ; son coût d'entraînement est environ six fois celui annoncé par la v1.
3. **Le CVaR n'a pas de contenu** tant que la dispersion de nos ensembles n'a pas de dépendance au régime (H-3-9, H-2-25).
4. **Le raffineur peut être légèrement optimiste** quand il commande une vitesse non faisable (observé une fois, 4 pas, `FeasiblePowerModel`).
5. **Fuite structurelle potentielle.** L'objet de prévision expose l'objet météo aux politiques (inutilisé, mais à durcir avant de brancher un routeur externe).
6. **Discrétisation.** À 40 km / 3 h, 3 à 7 % de la valeur sont liés à la discrétisation (dépendance à l'orientation de 6 % à $K = 21$ ; raffineur +3 à +7 %) ; ce n'est pas négligeable devant le gain de l'ensemble.
7. **Pas de contrainte de survie ni de port.** Le PoC n'a ni plafonnement de puissance, ni contrainte de tempête, ni gestion des fenêtres de port, ni logistique de flottille (rotations, occupation du quai, coefficient de rappel).

## 8.4 Ce qui reste à prouver

| À prouver | Pourquoi ce n'est pas encore prouvé | Ce qui le prouverait |
|------------------------------|-----------------------------------|-----------------------------------|
| Le CF de 0,8 est atteignable avec de **vraies** prévisions | Prévisions simulées | Étalonnage de la loi d'erreur sur reprévisions réelles (E-20), puis rejeu des essais E-01 à E-04 |
| L'avantage du routage tient **d'une année à l'autre** | Une seule année | ERA5 pluriannuel (E-18) |
| L'ensemble vaut son coût de calcul | +1,2 %, non significatif, loi d'erreur hypothétique | E-01, E-02, E-11, puis E-20 |
| La fonction de valeur apprise est utile | +0,6 point, non significatif | E-08, E-18 |
| Le navire survit et produit en vent très fort | Pas de contrainte ni de plafonnement | Confirmation client de la polaire au-dessus de 35 kn ; E-17 |
| La zone optimale | Boîte tronquée à 32°O et 65°N ; une année | Extension à l'ouest jusqu'à 45–50°O (chapitre 9) |
| L'avantage tient avec manœuvres, courant, dérive | Absents ou partiels | E-09, E-24 |
| Les budgets de calcul de la v1 pour l'exploitation | ENS_REF à 20 membres coûte environ 15 fois le « cycle » de la v1 ; zone fine de 10 km jamais construite | E-21 |

: Affirmations que nous ne pouvons pas encore faire.

# 9. Données à acquérir

La plupart des questions ouvertes du chapitre 8 se résument à un manque de **données**, non de code. Les priorités sont les suivantes.

| Priorité | Donnée | Objet | Expériences |
|--------|------------------------------------|----------------------------------------|----------------|
| **1** | **ERA5 pluriannuel** (au moins 10 années supplémentaires, DJF et JJA à défaut du reste), vent horaire à 10 m | Variabilité interannuelle, climatologie *hors échantillon* (suppression de la fuite d'année), puissance statistique des effets de 1 à 3 % | E-18 |
| **1** | **Extension de la boîte vers l'ouest : au moins 45°O, et 50°O si possible**, et vers le nord au-delà de 65°N | La meilleure cellule de 2015 est au bord ouest de la boîte actuelle (32°O) ; la zone de la v1 s'étend à 45°O ; les gains de mobilité à plus de 1000 km sont tronqués | E-15, E-13 |
| **1** | **Reprévisions** : GEFS v12 (reprévision de 2000 à 2019, à 5 membres) et archive ECMWF (ensemble à 51 membres, contrôle) pour au moins 8 dates de 2015, puis pour des dates de plusieurs années | Étalonner la loi d'erreur (RMSE, phase, ACC à D5-D10, rapport dispersion/erreur, écart contrôle/moyenne) ; mesurer la compétence réelle aux échéances de 5 à 10 jours | E-20 |
| 2 | ERA5 à la grille native (0,25°) sur la zone | Variance sous-maille, différences de vent à 5-20 km (Jensen, turbulence) | E-19 |
| 2 | Mesures de vent en mer (diffusiomètre ASCAT, bouées) | Biais d'ERA5 en vent fort (5 à 10 % annoncés) | E-10 |
| 2 | Polaire BETA : confirmation du comportement au-dessus de 35 kn, des bornes du masque de bogue, de la symétrie bâbord/tribord | Plafonnement éventuel, survie | E-17, E-10 |
| 3 | Données de manœuvre du navire (durée et perte de virement, empannage, dérive, abattement) | Remplacer les valeurs de travail (4 min, 0,3 ; $k_L$ = 0,03) | E-09, E-24 |
| 3 | État de mer et courants (si disponibles) | Au-delà du périmètre actuel ; effet sur la polaire et la dérive | — |
| 3 | Données de port (fenêtres, occupation de quai) | Logistique de flottille | E-16 |

: Données à acquérir, par priorité.

**Ordres de grandeur.** À la résolution native d'ERA5 (0,25°), une zone de 50°O–5°E par 35–65°N compte environ 221 × 121 ≈ 27 000 points ; le vent horaire sur un an représente environ 1,9 Go en simple précision non compressée, avant régrillage à 40 km (qui le réduit d'un ordre de grandeur). Dix années représentent donc de l'ordre de 20 Go à la grille native. Ces volumes, la disponibilité des reprévisions GEFS en accès libre et les conditions d'utilisation des archives ECMWF et Copernicus (licence, usage commercial) sont à vérifier avant lancement.

::: {.cal .open}
[POINT OUVERT]{.lab}
Les reprévisions GEFS n'ont que 5 membres : elles ne permettent pas d'étalonner un ensemble de 51 membres réduit à 6–8 médoïdes (H-5-1). L'archive ECMWF opérationnelle, qui a 51 membres, couvre une période plus courte et un modèle qui a évolué ; le choix de la source d'étalonnage est une décision à prendre avec l'équipe météorologie.
:::

# Annexe A. Conventions et définitions

**Unités internes.** Vitesses en m/s ; distances en m (projetées) ; durées en s ; instants en UTC ; puissances en kW ; énergies en kWh ; angles en degrés dans les API publiques. Les nœuds ($1\ \mathrm{kn} = 1852/3600$ m/s exactement) ne servent qu'aux entrées-sorties et aux rapports.

**Vent.** Les composantes $(u, v)$ sont stockées en m/s dans le sens *vers lequel* souffle le vent (convention d'ERA5) ; la direction météorologique est celle *d'où* il vient (degrés dans le sens horaire depuis le nord vrai). Les champs sont interpolés en composantes, jamais en (vitesse, direction).

**Cap et angle de vent vrai.** Le cap $\psi$ est le cap sol, en degrés dans le sens horaire depuis le nord vrai. Le TWA, dans $[0°, 180°]$, est l'angle entre le cap et la direction d'où vient le vent (0° : vent debout ; 90° : vent de travers ; 180° : vent arrière) :

::: {.cal .eq}
[ÉQUATION]{.lab}
$$\mathrm{TWA} = \arccos\!\left(-\frac{\mathbf{W}\cdot\hat{\mathbf{e}}_\psi}{|\mathbf{W}|}\right),$$
où $\mathbf{W}$ est le vecteur vent « vers » et $\hat{\mathbf{e}}_\psi = (\sin\psi, \cos\psi)$ le vecteur unitaire du cap. La formule de la note v1, écrite sans le signe moins avec $\mathbf{W}$ en convention « vers », donne 0° pour le vent arrière : **c'est une erreur de 180°**, corrigée dans le code.
:::

**Polaire.** La polaire $P[\mathrm{TWS}, \mathrm{TWA}, U]$ est la puissance **nette** (production de l'éolienne moins consommation de la propulsion), en kW, pouvant être négative ; dans les fichiers BETA, $\Psi$ est le TWA de la convention ci-dessus.

**Dérive.** $\dot{\mathbf{x}} = U(\sin\psi, \cos\psi) + \mathbf{c} + k_L |\mathbf{W}| \sin(\mathrm{TWA})\,\mathbf{n}_{lee}$, avec $k_L = 0{,}03$ par défaut ; la forme en $\sin(\mathrm{TWA})$ remplace la forme de la v1, discontinue lorsque le vent est dans l'axe du cap.

**Indicateurs.**

- *Facteur de charge* : $\mathrm{CF} = E / (P_n\,T)$, avec $E$ l'énergie nette produite sur la durée $T$ et $P_n = 3000$ kW la puissance nominale de référence.
- *Regret* par rapport à un oracle : $(E_{oracle} - E)/E_{oracle}$ ; l'« écart à l'oracle » en points est la différence des facteurs de charge.
- *Puissance de tenue de position* $P_{hold}(\mathrm{TWS})$ et $\mathrm{CF}_{hold} = P_{hold}/3000$ : voir la section 3.1.
- *Vent productif* : $P_{hold} > 2$ MW (TWS ≳ 19 kn) ; *calme* : TWS < 10 kn.
- *Comparaison appariée* : différence, mission par mission ou mois par mois, de deux politiques évaluées sur la même météo et la même graine de prévision.

**Statuts du registre.** *Ouvert* : aucune mesure ne tranche. *Confirmé / contredit (S0-S4)* : confirmé ou contredit dans notre environnement de test. *Non testable ici* : exige des données ou un composant qui n'existent pas dans le PoC. Après la campagne : *confirmé*, *réfuté*, *nuancé*.

# Annexe B. Registre : hypothèses par statut, avec preuves

Les tables ci-dessous sont **générées automatiquement** par `tools/hyp_table.py` à partir de `docs/s5/hypotheses.yaml` : elles suivent les statuts du registre. Les énoncés et preuves sont ceux du registre de travail (en anglais).

{{include: generated/hyp_verdicts.md}}

# Annexe C. Registre complet par catégorie

Le registre de 119 entrées, par catégorie, puis statut. « Exp. » est l'expérience du plan S5 qui teste l'entrée (E-xx) ; « · » signifie qu'aucune expérience dédiée n'est définie (analyse documentaire ou arithmétique).

{{include: generated/hyp_register.md}}

# Annexe D. Glossaire

| Terme | Définition |
|--------------------|--------------------------------------------------------------------------------|
| **ACC** | *Anomaly correlation coefficient* : corrélation entre anomalie prévue et anomalie observée |
| **B0 / B1 / B1c** | Routeurs de référence : meilleur point fixe ; MPC déterministe à 5 jours ; idem avec terminal climatologique (c) |
| **BETA** | Jeu de polaires de puissance fourni par le client (sortie de VPP) |
| **BSS** | *Brier skill score* : score de Brier relatif à une référence (1 = parfait, 0 = pas mieux que la référence) |
| **CF** | Facteur de charge (*capacity factor*) |
| **CVaR** | *Conditional value at risk* : moyenne de la queue de la distribution au-delà d'un quantile |
| **DP** | Programmation dynamique (récursion arrière sur le graphe espace-temps) |
| **E0** | Étude du biais de clairvoyance de la valeur a posteriori (S4) |
| **ENS_REF** | Routeur à ensemble (20 membres, 10 jours, raffineur) |
| **ERA5** | Réanalyse atmosphérique du centre européen (ECMWF/Copernicus) |
| **EVPI** | *Expected value of perfect information* : gain attendu d'une prévision parfaite |
| **GEFS** | Système de prévision d'ensemble global américain ; reprévisions de 2000 à 2019 à 5 membres |
| **Hold / tenue de position** | Fonctionnement d'un navire qui maintient sa position par amures successives |
| **IPOPT / CasADi** | Solveur et cadre de contrôle optimal du raffineur (licences LGPL et EPL ; reportées) |
| **LAEA** | Projection azimutale équivalente de Lambert (grille de planification) |
| **MPC** | Commande prédictive (horizon glissant) : replanifier à intervalles réguliers |
| **Oracle_REF_H** | Routeur à météo réalisée connue sur 15 jours, borne approchée |
| **PAM** | *Partitioning around medoids* (k-médoïdes) |
| **Raffineur** | Couche de contrôle optimal continu sur 0-48 h au pas de 30 min |
| **SDF** | *Signed distance function* : distance signée à la côte |
| **TWA / TWS** | Angle et vitesse du vent vrai |
| **$V_\theta$** | Fonction de valeur terminale apprise (LightGBM), *policy-consistent* |
| **VPP** | *Velocity prediction program* : modèle de performance du navire |

: Glossaire.

# Annexe E. Reproductibilité

Toutes les commandes se lancent depuis la racine du dépôt (`horizon/`), sauf indication. Les données client (ERA5, polaires BETA) ne sont pas dans le dépôt ; leurs chemins sont configurés dans le code (`horizon.viz.tech_figures`, `horizon.weather.era5`, `horizon.polar.beta`). Pendant la campagne, préfixer chaque commande lourde par `nice -n 15`.

| Étape | Commande |
|----------------------|------------------------------------------------------------------------------|
| Installation | `pip install -e ".[dev,value,data]"` |
| Tests | `pytest` (environ 260 fonctions de test) |
| Cache ERA5 (grille de 40 km) | `python3 scripts/prepare_era5.py [--grib-dir DIR] [--dx-km 40]` |
| Sprint S3 (10 missions de 30 j) | `python3 scripts/run_s3_backtest.py [--members 10]` |
| Sprint S4 : année persistante | `python3 scripts/run_s4_year.py --policy B1c_5d_REF --days 365 --out outputs/s4_runs/<run>` ; file reprenable : `python3 scripts/s4_queue.py <fichier de jobs> --par 2` |
| Analyse S4 (tableaux et figures du chapitre 7) | `python3 scripts/analyze_s4.py` |
| Fonction de valeur $V_\theta$ | `python3 scripts/value_collect.py` puis `python3 scripts/value_train.py` |
| Inspecteur | `python3 scripts/export_s4_inspector.py` puis `python3 scripts/build_inspector.py --results ...` |
| Météo océanique (chapitre 3) | `python3 scripts/s5_weather/w0_prepare.py` puis `w1_climatology.py`, `w2_persistence.py`, `w3a_acf.py`, `w3b_advection.py`, `w3c_adv_stats.py`, `w3d_lagrangian.py`, `w4a_reach.py`, `w4b_dp.py`, `w4c_dp_radius.py`, `w5_predictability.py`, `w6_sampling.py` ; figures : `plot_a1.py`, `plot_rest.py` (sorties dans `outputs/s5/weather/`, figures dans `docs/s5/fig/`) |
| Campagne de sensibilité | `bash scripts/s5/supervise.sh [--tiers A,B]` (relance idempotente de la file) ; état : `python3 scripts/s5/status.py` ; agrégation : `python3 scripts/s5/aggregate.py` |
| Document (cette note) | depuis `docdev/` : `make figures && make && make check` |

: Commandes pour tout rejouer.

**Chaîne documentaire.** Le document est produit par `docdev/` : Markdown → pandoc → HTML/CSS + KaTeX → Chrome en mode sans interface → PDF. `make figures` exécute `figures/gen_figures.py`, qui importe le paquet `horizon` en lecture seule, produit les figures techniques en SVG et recopie les figures d'analyse S5 et S4 dans `docdev/fig/` ; `make` régénère les tables du registre (`tools/hyp_table.py`), assemble et imprime ; `make check` contrôle la pagination, le sommaire, la numérotation, les polices embarquées, les images manquantes et dénombre les marqueurs « À COMPLÉTER ». Le fichier `docdev/README.md` détaille la chaîne.
