# ruff: noqa: E501
"""Texts (FR / EN) of the technical Guide figures.

``caption_*`` and ``body_*`` are ``str.format`` templates filled with the statistics each figure
function returns, so every number quoted comes from the same run as the picture.  Body texts are
a small markdown subset (bold lead-ins, bullet lists, paragraphs) rendered by the inspector.
"""

TEXTS = {}
TEXTS["architecture"] = {k: "" for k in ("title_en","title_fr","caption_en","caption_fr","body_en","body_fr")}

# --------------------------------------------------------------------------------- 1. polar
TEXTS["polar"] = {
    "title_en": "1. The ship and its power polar (BETA, client VPP data)",
    "title_fr": "1. Le navire et sa polaire de puissance (BETA, données VPP du client)",
    "caption_en": "Net power P_net [kW] as a function of wind angle (TWA, around the circle) and ship speed through "
                  "the water (U, radius, m/s), at three wind speeds; below, the best power over U for each angle.",
    "caption_fr": "Puissance nette P_net [kW] selon l'angle de vent (TWA, sur le cercle) et la vitesse du navire "
                  "dans l'eau (U, rayon, m/s), pour trois vitesses de vent ; en bas, la meilleure puissance sur U "
                  "pour chaque angle.",
    "body_en": """**What it shows.** Everything the routers optimise starts from this table: for a true wind speed (TWS), a true wind angle (TWA) and a speed through the water U, the vessel model (VPP) gives the net power, i.e. what the wind turbine produces minus what the propulsion consumes. Each disc is one wind speed (10, 18 and 26 kn); the angle is the wind angle with the top of the disc being head to wind, and the radius is U from 0 to 8 m/s. The two tacks are mirror images.

**How to read it.** Red = the ship is a net producer, blue = it burns more than it makes. Hatched areas are combinations the model could not reach (a speed that is not attainable at that angle). The purple outline is a sector that is masked on purpose: the client told us the high power of a nearly stopped ship sailing downwind is a flaw of the VPP, so it is removed. The dashed line is U*(TWA), the speed that gives the best power where it is positive. Panel (d) keeps only that best value per angle, P-dagger(TWA), for six wind speeds.

**What to notice.**
- At 18 kn the optimum is {pmax_18:.0f} kW at TWA {twa_pmax_18:.0f} deg and U = {u_pmax_18:.1f} m/s: a beam reach, the same band that the guide calls productive (75-105 deg).
- At 26 kn the ceiling of about {pmax_26:.0f} kW (the generator limit) is reached from TWA 90 deg to about 135 deg, so strong wind widens the good sector rather than raising the peak. At 10 kn the best is only {pmax_10:.0f} kW.
- Head to wind the best net power is {p_dag_head_18:.0f} kW at 18 kn: you can at best break even. In the worst corner the ship consumes about {pmin_18:.0f} kW.

**Why it matters for routing.** The router does not chase wind speed alone: the same wind is worth anything from a loss to the full 3 MW depending on the heading, so a route is a trade between where the wind is strong and which headings are possible there. The plateau at high wind explains why the best places are not the stormiest ones.

**Limits.** Below 10 kn there is no data: production is extrapolated with a cut-in at 7 kn (a hypothesis to be confirmed). The masked sector and the repaired holes (optimiser failures) are client decisions; U above 8 m/s is treated as unreachable.""",
    "body_fr": """**Ce que montre la figure.** Tout ce que les routeurs optimisent part de cette table : pour une vitesse de vent vrai (TWS), un angle de vent vrai (TWA) et une vitesse dans l'eau U, le modèle de navire (VPP) donne la puissance nette, c'est-à-dire ce que produit l'éolienne moins ce que consomme la propulsion. Chaque disque correspond à un vent (10, 18 et 26 nœuds) ; l'angle est l'angle du vent, le haut du disque étant le vent debout, et le rayon est U de 0 à 8 m/s. Les deux amures sont symétriques.

**Comment lire.** Rouge = le navire produit net, bleu = il consomme plus qu'il ne produit. Les zones hachurées sont des combinaisons que le modèle n'a pas pu atteindre (vitesse inaccessible sous cet angle). Le contour violet est un secteur masqué volontairement : le client nous a indiqué que la forte puissance d'un navire quasi arrêté vent arrière est un défaut du VPP, on l'écarte. Le tireté est U*(TWA), la vitesse qui donne la meilleure puissance là où elle est positive. Le panneau (d) ne garde que cette meilleure valeur par angle, P-dagger(TWA), pour six vitesses de vent.

**À retenir.**
- À 18 nœuds l'optimum est de {pmax_18:.0f} kW pour un TWA de {twa_pmax_18:.0f} degrés et U = {u_pmax_18:.1f} m/s : un vent de travers, la bande que le guide appelle productive (75-105 degrés).
- À 26 nœuds le plafond d'environ {pmax_26:.0f} kW (limite du générateur) est atteint de 90 à 135 degrés environ : plus de vent élargit le bon secteur plutôt que d'élever le pic. À 10 nœuds le meilleur n'est que {pmax_10:.0f} kW.
- Vent debout, la meilleure puissance nette est de {p_dag_head_18:.0f} kW à 18 nœuds : au mieux on est à l'équilibre. Dans le pire coin, le navire consomme environ {pmin_18:.0f} kW.

**Pourquoi c'est important pour le routage.** Le routeur ne cherche pas seulement le vent fort : le même vent vaut de la perte au plein 3 MW selon le cap, donc une route est un compromis entre l'endroit où le vent est fort et les caps possibles à cet endroit. Le plateau par vent fort explique pourquoi les meilleures zones ne sont pas les plus tempétueuses.

**Limites.** Sous 10 nœuds il n'y a pas de données : la production est extrapolée avec un seuil de démarrage à 7 nœuds (hypothèse à confirmer). Le secteur masqué et les trous réparés (échecs de l'optimiseur) sont des décisions du client ; U au-delà de 8 m/s est considéré inaccessible.""",
}

# ------------------------------------------------------------------------------ 2. envelope
TEXTS["envelope"] = {
    "title_en": "2. Power envelope: why zig-zagging beats any single heading",
    "title_fr": "2. Enveloppe de puissance : pourquoi le zig-zag bat tout cap unique",
    "caption_en": "At TWS = 18 kn, mean net power [kW] over the plane of ground velocities [m/s] (wind frame): "
                  "single heading (a), best mixture of headings (b), gain (c), a cut along the wind axis (d) "
                  "and the two tacks that build a hold (e).",
    "caption_fr": "À TWS = 18 nœuds, puissance nette moyenne [kW] sur le plan des vitesses sol [m/s] (repère du "
                  "vent) : cap unique (a), meilleur mélange de caps (b), gain (c), coupe le long de l'axe du vent (d) "
                  "et les deux amures qui forment une tenue de position (e).",
    "body_en": """**What it shows.** The DP chooses, for each time step, an average ground velocity (how fast and in which direction the ship makes good). A ship can reach the same average velocity with a single steady heading, or by alternating between headings (tacking, zig-zag). Panel (a) maps the power of the best single heading for each ground velocity; panel (b) maps the best power obtainable by mixing headings, i.e. the upper concave envelope of all polar points (computed with a 3-D convex hull), after charging the cost of the manoeuvres. Panel (c) is the difference.

**How to read it.** Axes are the ground velocity components in the wind frame, in m/s: vertical = towards the wind source (up = upwind), horizontal = across the wind. The star is v = 0: the ship holding its position. Colour is mean net power in kW.

**What to notice.**
- Station keeping is the striking case. With one heading, holding position yields {hold_direct_kw:.0f} kW. By alternating two beam tacks (panel e: TWA {hold_twa:.0f} deg, U = {hold_u:.2f} m/s, {hold_p:.0f} kW each) the mean velocity cancels and the mean power is {hold_e_kw:.0f} kW, or {hold_env_kw:.0f} kW once manoeuvres are paid for.
- The manoeuvre factor is {f_avail:.3f}: 4 minutes of manoeuvre every 45 minutes leg, with 30 % of the production kept meanwhile (hypotheses). It is applied to every mixture, which is slightly pessimistic for nearly straight arcs.
- The gain of mixing reaches {gain_max_kw:.0f} kW and is concentrated around v = 0, i.e. slow progress and station keeping, where no single heading can produce power. Far from v = 0 (fast transit) the envelope and the single heading nearly coincide.

**Why it matters for routing.** Without the envelope the DP would treat holding position, or moving slowly, as worthless and would always run. With it, the router knows that waiting on a good wind patch, or drifting slowly across it, is productive. It is also why the hold power is a function of wind speed only.

**Limits.** The envelope assumes legs long enough to reach steady state and equal times on both tacks; the leeway (drift) is a simple law (3 % of TWS times the sine of TWA); currents are ignored.""",
    "body_fr": """**Ce que montre la figure.** À chaque pas de temps, la DP choisit une vitesse sol moyenne (à quelle vitesse et dans quelle direction le navire fait route). Un navire peut obtenir la même vitesse moyenne avec un cap unique, ou en alternant les caps (louvoyage, zig-zag). Le panneau (a) cartographie la puissance du meilleur cap unique pour chaque vitesse sol ; le panneau (b) celle du meilleur mélange de caps, c'est-à-dire l'enveloppe concave supérieure de tous les points de la polaire (calculée par enveloppe convexe 3-D), après prise en compte du coût des manœuvres. Le panneau (c) en est la différence.

**Comment lire.** Les axes sont les composantes de la vitesse sol dans le repère du vent, en m/s : vertical = vers la source du vent (haut = au vent), horizontal = en travers. L'étoile est v = 0 : le navire tient sa position. La couleur est la puissance nette moyenne en kW.

**À retenir.**
- La tenue de position est le cas frappant. Avec un cap unique, tenir la position donne {hold_direct_kw:.0f} kW. En alternant deux amures de travers (panneau e : TWA {hold_twa:.0f} degrés, U = {hold_u:.2f} m/s, {hold_p:.0f} kW chacune) la vitesse moyenne s'annule et la puissance moyenne est de {hold_e_kw:.0f} kW, soit {hold_env_kw:.0f} kW une fois les manœuvres payées.
- Le facteur de manœuvre vaut {f_avail:.3f} : 4 minutes de manœuvre toutes les 45 minutes de bord, avec 30 % de la production conservée pendant ce temps (hypothèses). Il est appliqué à tout mélange, ce qui est un peu pessimiste pour les arcs presque rectilignes.
- Le gain du mélange atteint {gain_max_kw:.0f} kW et se concentre autour de v = 0, c'est-à-dire progression lente et tenue de position, là où aucun cap unique ne produit. Loin de v = 0 (transit rapide), l'enveloppe et le cap unique coïncident presque.

**Pourquoi c'est important pour le routage.** Sans l'enveloppe, la DP jugerait sans valeur la tenue de position ou une progression lente, et courrait toujours. Avec elle, le routeur sait qu'attendre sur une bonne plage de vent, ou la traverser lentement, est productif. C'est aussi pourquoi la puissance de tenue de position ne dépend que de la vitesse du vent.

**Limites.** L'enveloppe suppose des bords assez longs pour atteindre le régime établi et des durées égales sur les deux amures ; la dérive est une loi simple (3 % de TWS fois le sinus de TWA) ; les courants sont ignorés.""",
}

# ------------------------------------------------------------------------------------ 3. DP
TEXTS["dp"] = {
    "title_en": "3. Dynamic programming on the space-time graph",
    "title_fr": "3. Programmation dynamique sur le graphe espace-temps",
    "caption_en": "Real 40 km ERA5 grid around the ship with the {n_arcs}-arc stencil to scale (a); value field V of "
                  "a real 5-day solve [MWh] and its optimal path (b, c); V along the path (d). Start {date} 00 UTC.",
    "caption_fr": "Grille ERA5 réelle de 40 km autour du navire avec le stencil de {n_arcs} arcs à l'échelle (a) ; "
                  "champ de valeur V d'une vraie résolution à 5 jours [MWh] et son chemin optimal (b, c) ; V le "
                  "long du chemin (d). Départ le {date} à 00 UTC.",
    "body_en": """**What it shows.** The ocean is a grid of {n_nodes} nodes spaced 40 km apart; time is cut into 3-hour steps, {n_steps} of them here (5 days). A route is a chain of moves, each one picked from a fixed list, the stencil. The stencil of panel (a) has {n_arcs} entries, drawn to scale: hold, {n_one} one-step arcs (3 h) and {n_two} two-step arcs (6 h, dashed) reaching up to about {span_max_km:.0f} km, with the ground speed of each arc in colour (0.5 to 8 m/s). Grey arrows are the real wind (direction it blows towards) at the start.

**How it is solved: backward induction.** Let V be the best energy still collectable from a node at a given time. At the end of the horizon V is the terminal value (zero here). Going backwards in time, for every node the solver tries all arcs and keeps the best sum of the arc's energy (from the polar envelope and the wind along the arc) and the value of the arrival node: V_k(c) = max over arcs a of [ E(a; wind) + V at (k + span of a) of (c + a) ]. Land and waters closer than 20 km to the coast are excluded (V = minus infinity). Reading the best arc at each node forwards from the start gives the optimal path.

**How to read panels (b)-(d).** (b) is V at the start time in MWh: the dark areas are where the 5 days ahead are worth most (up to {vmax_mwh:.0f} MWh, close to 5 days at 3 MW). Grey is land, coast buffer or outside the ERA5 box. (c) is V on one row of the grid against time; the red line is the optimal path projected on that row, and V fades to zero at the top. (d) shows V along the optimal path: it falls by the energy harvested, so the slope is the power.

**What to notice.** V at the start is {v0_mwh:.0f} MWh, i.e. a mean {mean_kw:.0f} kW over 120 h, along {dist_km:.0f} km of route. The stencil's two-step arcs give about 18 deg angular resolution and reduce the dependence of results on grid orientation.

**Limits.** Because arcs end on nodes, paths are polylines on a 40 km lattice (the refiner of figure 6 smooths them); the wind is the truth here whereas routers see forecasts; there is no current.""",
    "body_fr": """**Ce que montre la figure.** L'océan est une grille de {n_nodes} nœuds espacés de 40 km ; le temps est découpé en pas de 3 heures, {n_steps} ici (5 jours). Une route est une chaîne de déplacements, chacun pris dans une liste fixe, le stencil. Celui du panneau (a) compte {n_arcs} entrées, dessinées à l'échelle : tenue de position, {n_one} arcs d'un pas (3 h) et {n_two} arcs de deux pas (6 h, en tireté) allant jusqu'à environ {span_max_km:.0f} km, avec la vitesse sol de chaque arc en couleur (0,5 à 8 m/s). Les flèches grises sont le vent réel (direction vers laquelle il souffle) au départ.

**Comment on résout : induction arrière.** Soit V la meilleure énergie encore récoltable depuis un nœud à un instant donné. En fin d'horizon V est la valeur terminale (nulle ici). En remontant le temps, pour chaque nœud le solveur essaie tous les arcs et garde la meilleure somme entre l'énergie de l'arc (enveloppe de la polaire et vent le long de l'arc) et la valeur du nœud d'arrivée : V_k(c) = max sur les arcs a de [ E(a ; vent) + V à (k + durée de a) de (c + a) ]. La terre et les eaux à moins de 20 km de la côte sont exclues (V = moins l'infini). Lire vers l'avant, depuis le départ, le meilleur arc de chaque nœud donne le chemin optimal.

**Comment lire les panneaux (b)-(d).** (b) est V à l'instant initial en MWh : les zones sombres sont celles où les 5 jours à venir valent le plus (jusqu'à {vmax_mwh:.0f} MWh, proche de 5 jours à 3 MW). Le gris est la terre, la bande côtière ou l'extérieur de la boîte ERA5. (c) est V sur une rangée de la grille en fonction du temps ; la ligne rouge est le chemin optimal projeté sur cette rangée, et V tombe à zéro en haut. (d) montre V le long du chemin optimal : il baisse de l'énergie récoltée, la pente est donc la puissance.

**À retenir.** V au départ vaut {v0_mwh:.0f} MWh, soit {mean_kw:.0f} kW en moyenne sur 120 h, sur {dist_km:.0f} km de route. Les arcs de deux pas donnent environ 18 degrés de résolution angulaire et réduisent la dépendance des résultats à l'orientation de la grille.

**Limites.** Les arcs finissant sur des nœuds, les chemins sont des polylignes sur un réseau de 40 km (le raffineur de la figure 6 les lisse) ; le vent est ici la vérité alors que les routeurs voient des prévisions ; pas de courant.""",
}

# ----------------------------------------------------------------------------------- 4. MPC
TEXTS["mpc"] = {
    "title_en": "4. Receding horizon (MPC): plans change as forecasts are renewed",
    "title_fr": "4. Horizon glissant (MPC) : les plans changent au rythme des prévisions",
    "caption_en": "Eight successive 6-hourly plans of B1 (5 d DP on the newest control forecast) from {date} 00 UTC, "
                  "overlaid on the track really sailed (km); distance between plans and track; energy promised vs "
                  "delivered [MWh].",
    "caption_fr": "Huit plans successifs de B1 toutes les 6 h (DP à 5 j sur la prévision de contrôle la plus récente) "
                  "à partir du {date} à 00 UTC, superposés à la trajectoire réellement navigée (km) ; distance "
                  "plans-trajectoire ; énergie promise et livrée [MWh].",
    "body_en": """**What it shows.** A router never sails a whole plan. Every 6 hours it takes the newest forecast, solves a fresh 5-day DP from where the ship actually is, executes the first 6 hours and starts again. This is model-predictive control (MPC). The figure replays that loop with the real code and forecast model on a real excerpt of the B1 year run (UTC time, from {date} 00 UTC): the thick black line is the track sailed, the coloured lines are the first 48 hours of each plan, from dark (first plan) to light (last).

**How to read it.** Panel (a) is in km on the planning grid. Each circle is where the ship stood when the plan was made; each square is where that plan expected it to be 48 h later. Panel (b) gives, for each plan, the distance between the planned position and the position actually reached at the same lead time. Panel (c) compares, for each replanning, the energy promised over the 5 days ahead (bars) with the energy the ship really harvested over those 5 days (dots).

**What to notice.**
- Plans disagree with each other: the end points move by {end_shift_km:.0f} km on average from the first plan to the others. Successive forecasts for the same days differ, so successive optimal routes differ.
- Plans are reliable only for the first hours: the median distance between plan and reality is {dev12_km:.0f} km at +12 h, {dev24_km:.0f} km at +24 h and {dev48_km:.0f} km at +48 h. A few plans (light orange) are off by several hundred km.
- The plans promise {val_min_mwh:.0f}-{val_max_mwh:.0f} MWh per 5 days and the ship delivered about {real_mean_mwh:.0f} MWh: the DP is optimistic because it believes its forecast.

**Why it matters.** The value of a forecast lies in its first days; replanning is what turns an imperfect long-range forecast into a useful short-range decision. It is also why optimism (promised minus delivered) is tracked in the Explorer.

**Limits.** The plans are recomputed from the track positions with B1 and the seed-1 forecast model; the real run used the refiner too. The 5-day window is not the 15 days of the other routers.""",
    "body_fr": """**Ce que montre la figure.** Un routeur ne navigue jamais un plan en entier. Toutes les 6 heures il prend la prévision la plus récente, résout une nouvelle DP à 5 jours depuis la position réelle du navire, exécute les 6 premières heures et recommence. C'est la commande prédictive (MPC). La figure rejoue cette boucle avec le vrai code et le vrai modèle de prévision sur un extrait réel de la simulation annuelle de B1 (temps UTC, à partir du {date} à 00 UTC) : le trait noir épais est la trajectoire navigée, les traits colorés sont les 48 premières heures de chaque plan, du sombre (premier plan) au clair (dernier).

**Comment lire.** Le panneau (a) est en km sur la grille de planification. Chaque cercle est la position du navire à la création du plan ; chaque carré est l'endroit où ce plan l'attendait 48 h plus tard. Le panneau (b) donne, pour chaque plan, la distance entre la position planifiée et celle réellement atteinte à la même échéance. Le panneau (c) compare, à chaque replanification, l'énergie promise sur les 5 jours à venir (barres) et celle réellement récoltée sur ces 5 jours (points).

**À retenir.**
- Les plans se contredisent : les points d'arrivée se déplacent en moyenne de {end_shift_km:.0f} km du premier plan aux suivants. Les prévisions successives pour les mêmes jours diffèrent, donc les routes optimales successives aussi.
- Les plans ne sont fiables que les premières heures : la distance médiane entre plan et réalité est de {dev12_km:.0f} km à +12 h, {dev24_km:.0f} km à +24 h et {dev48_km:.0f} km à +48 h. Quelques plans (orange clair) s'écartent de plusieurs centaines de km.
- Les plans promettent {val_min_mwh:.0f}-{val_max_mwh:.0f} MWh par 5 jours et le navire en a livré environ {real_mean_mwh:.0f} : la DP est optimiste parce qu'elle croit sa prévision.

**Pourquoi c'est important.** La valeur d'une prévision est dans ses premiers jours ; replanifier transforme une prévision lointaine imparfaite en décision utile à court terme. C'est aussi pourquoi l'optimisme (promis moins livré) est suivi dans l'Explorer.

**Limites.** Les plans sont recalculés depuis les positions de la trajectoire avec B1 et le modèle de prévision de graine 1 ; la simulation réelle utilisait aussi le raffineur. La fenêtre de 5 jours n'est pas celle de 15 jours des autres routeurs.""",
}

# ------------------------------------------------------------------------------ 5. forecasts
TEXTS["forecast"] = {
    "title_en": "5. Forecasts and ensembles: how wrong, how uncertain, how reduced",
    "title_fr": "5. Prévisions et ensembles : quelle erreur, quelle incertitude, quelle réduction",
    "caption_en": "Error of the control and of the ensemble mean, and ensemble spread [m/s] against lead time [days], "
                  "winter and summer (a, b); wind map at lead 5 d for the issue of {issue} (c); spread / error "
                  "ratio [-] (d).",
    "caption_fr": "Erreur du contrôle et de la moyenne d'ensemble, et dispersion de l'ensemble [m/s] selon l'échéance "
                  "[jours], hiver et été (a, b) ; carte du vent à 5 jours pour l'émission du {issue} (c) ; rapport "
                  "dispersion / erreur [-] (d).",
    "body_en": """**What it shows.** The routers do not see the true wind but forecasts, here produced by the project's forecast-error model (version 2) around the real ERA5 wind: a control run plus 20 ensemble members whose errors grow with lead time, with fresh cycles every 6 hours and a seasonal modulation. Panels (a) and (b) verify it against the truth on the sea cells over 8 weekly issues in winter and 8 in summer.

**How to read it.** Vertical axis: root-mean-square error of the vector wind in m/s. Horizontal: lead time in days. The orange curve is the single control forecast, the blue one the mean of the 20 members (smoother, therefore closer to the truth), the green dashed one the spread of the ensemble (its own estimate of its uncertainty). A calibrated ensemble has spread equal to the error of its mean.

**What to notice.**
- Control error grows from about 1 m/s at day 0 to {winter_ctrl_d3:.1f} m/s at day 3 and {winter_ctrl_d5:.1f} m/s at day 5 in winter (summer: {summer_ctrl_d3:.1f} and {summer_ctrl_d5:.1f}). Beyond 3-4 days a single forecast is a poor guide.
- The ensemble mean is clearly better than the control (day 5: {winter_mean_d5:.1f} vs {winter_ctrl_d5:.1f} m/s in winter) and the spread matches it ({winter_spr_d5:.1f} m/s): the ensemble is roughly calibrated. Winter errors are larger than summer ones.
- Panel (c): the 14 m/s contour at 5 days; colours show where the members disagree (spread up to 6 m/s). The ensemble mean contour is smoother than the truth and the control, which is exactly the information a router can use.
- Panel (d): the spread / error-of-the-mean ratio averages {ratio_w:.2f} in winter and {ratio_s:.2f} in summer over days 1 to 7 (1 = calibrated): the ensemble is somewhat over- or under-confident depending on the season, but of the right order.

**Why it matters.** This is the reason B1 over-trusts distant days and why ENS builds its tail-risk (CVaR) objective on a handful of scenarios.

**Limits.** The forecasts are a statistical model, not archived forecasts: errors are exchangeable with the truth, not meteorologically structured; 8 issues per season give noisy curves.""",
    "body_fr": """**Ce que montre la figure.** Les routeurs ne voient pas le vent réel mais des prévisions, produites ici par le modèle d'erreur de prévision du projet (version 2) autour du vent ERA5 réel : un contrôle et 20 membres d'ensemble dont l'erreur croît avec l'échéance, avec des cycles frais toutes les 6 heures et une modulation saisonnière. Les panneaux (a) et (b) la vérifient face à la vérité sur les cases de mer, sur 8 émissions hebdomadaires en hiver et 8 en été.

**Comment lire.** Axe vertical : erreur quadratique moyenne du vent vectoriel en m/s. Horizontal : échéance en jours. La courbe orange est la prévision de contrôle seule, la bleue la moyenne des 20 membres (plus lisse, donc plus proche de la vérité), la verte en tireté la dispersion de l'ensemble (sa propre estimation de son incertitude). Un ensemble calibré a une dispersion égale à l'erreur de sa moyenne.

**À retenir.**
- L'erreur du contrôle passe d'environ 1 m/s au jour 0 à {winter_ctrl_d3:.1f} m/s au jour 3 et {winter_ctrl_d5:.1f} m/s au jour 5 en hiver (été : {summer_ctrl_d3:.1f} et {summer_ctrl_d5:.1f}). Au-delà de 3-4 jours, une prévision seule est un mauvais guide.
- La moyenne d'ensemble est nettement meilleure que le contrôle (jour 5 : {winter_mean_d5:.1f} contre {winter_ctrl_d5:.1f} m/s en hiver) et la dispersion lui correspond ({winter_spr_d5:.1f} m/s) : l'ensemble est à peu près calibré. Les erreurs d'hiver dépassent celles d'été.
- Panneau (c) : le contour de 14 m/s à 5 jours ; la couleur indique où les membres divergent (dispersion jusqu'à 6 m/s). Le contour de la moyenne d'ensemble est plus lisse que la vérité et le contrôle, c'est exactement l'information qu'un routeur peut exploiter.
- Panneau (d) : le rapport dispersion / erreur de la moyenne vaut en moyenne {ratio_w:.2f} en hiver et {ratio_s:.2f} en été sur les jours 1 à 7 (1 = calibré) : l'ensemble est un peu trop dispersé ou trop confiant selon la saison, mais du bon ordre.

**Pourquoi c'est important.** C'est la raison pour laquelle B1 accorde trop de confiance aux jours lointains, et pour laquelle ENS travaille avec un ensemble (figures suivantes).

**Limites.** Les prévisions sont un modèle statistique, pas des prévisions archivées : les erreurs sont échangeables avec la vérité, sans structure météorologique ; 8 émissions par saison donnent des courbes bruitées.""",
}

# ------------------------------------------------------------------------------- 6. refiner
TEXTS["refiner"] = {
    "title_en": "6. Continuous refiner: from the grid path to a smooth trajectory",
    "title_fr": "6. Raffineur continu : du chemin de grille à une trajectoire lisse",
    "caption_en": "A real 48 h window ({date} {hour} UTC): DP path vs refined path (km), ground speed [m/s], "
                  "net power [kW] and cumulated energy [MWh] against time [h].",
    "caption_fr": "Une fenêtre réelle de 48 h ({date} {hour} UTC) : chemin DP et chemin raffiné (km), vitesse sol "
                  "[m/s], puissance nette [kW] et énergie cumulée [MWh] selon le temps [h].",
    "body_en": """**What it shows.** The grid DP is coarse: 40 km nodes, 3-hour steps, a limited list of directions. The refiner takes the first 48 hours of the DP plan, as a starting guess, and polishes it with a continuous optimiser (an NLP solved with IPOPT) at 30-minute stages. It maximises the energy of the window plus the DP value at its end (so that it still cares about what comes after), minus small penalties on speed changes and curvature, under the speed and coast-distance constraints.

**How to read it.** (a) the two paths in km on the planning grid: orange dots are DP nodes, the blue line the refined trajectory (squares every 3 h) and grey dots the 40 km grid. (b) and (c) give ground speed in m/s and net power in kW against time in hours since the issue. (d) is the energy accumulated over the window in MWh.

**What to notice.**
- The DP path is a staircase of straight pieces whose speed jumps between 2 and 5 m/s; the refined path is smooth, with a speed between {vmin_ref:.1f} and {vmax_ref:.1f} m/s. Over the window it is shorter ({dist_ref:.0f} km against {dist_dp:.0f} km).
- Even so the refined route is slightly more productive: {e_ref:.1f} MWh against {e_dp:.1f} MWh ({gain_pct:+.1f} %), because it holds the beam-reach power plateau (about 3 MW) more steadily, and slows down only when the wind dies around hour 25.
- Gains are modest and systematic: in the year-long runs the refiner adds only a few percent, with less spread.

**Why it matters.** It removes the dependence on the grid orientation, produces a trajectory the ship can actually follow and costs only a few seconds per replan. It is not a different strategy: the DP still chooses the basin of attraction, the refiner only finishes the job.

**Limits.** When IPOPT fails, leaves the velocity envelope, or breaks the coast limit, the DP plan is kept (the refined path is never worse than its starting guess in its own objective). Only one forecast member is used.""",
    "body_fr": """**Ce que montre la figure.** La DP sur grille est grossière : nœuds de 40 km, pas de 3 heures, liste limitée de directions. Le raffineur prend les 48 premières heures du plan DP comme point de départ et les polit avec un optimiseur continu (un problème non linéaire résolu par IPOPT) à des étapes de 30 minutes. Il maximise l'énergie de la fenêtre plus la valeur DP en fin de fenêtre (pour continuer à se soucier de la suite), moins de petites pénalités sur les variations de vitesse et la courbure, sous les contraintes de vitesse et de distance à la côte.

**Comment lire.** (a) les deux chemins en km sur la grille de planification : les points orange sont les nœuds DP, la ligne bleue la trajectoire raffinée (carrés toutes les 3 h) et les points gris la grille de 40 km. (b) et (c) donnent la vitesse sol en m/s et la puissance nette en kW selon le temps en heures depuis l'émission. (d) est l'énergie accumulée sur la fenêtre en MWh.

**À retenir.**
- Le chemin DP est un escalier de segments dont la vitesse saute entre 2 et 5 m/s ; le chemin raffiné est lisse, avec une vitesse entre {vmin_ref:.1f} et {vmax_ref:.1f} m/s. Sur la fenêtre il est plus court ({dist_ref:.0f} km contre {dist_dp:.0f} km).
- Malgré cela la route raffinée est un peu plus productive : {e_ref:.1f} MWh contre {e_dp:.1f} MWh ({gain_pct:+.1f} %), parce qu'elle tient plus régulièrement le plateau de puissance du vent de travers (environ 3 MW) et ne ralentit que lorsque le vent tombe vers l'heure 25.
- Les gains sont modestes et systématiques : sur les simulations annuelles le raffineur ajoute seulement quelques pour cent, avec moins de dispersion.

**Pourquoi c'est important.** Il supprime la dépendance à l'orientation de la grille, fournit une trajectoire que le navire peut vraiment suivre et ne coûte que quelques secondes par replanification. Ce n'est pas une autre stratégie : la DP choisit toujours le bassin d'attraction, le raffineur ne fait que finir le travail.

**Limites.** Quand IPOPT échoue, sort de l'enveloppe de vitesses ou viole la limite côtière, le plan DP est conservé (le chemin raffiné n'est jamais pire que son point de départ dans son propre objectif). Un seul membre de prévision est utilisé.""",
}

# ------------------------------------------------------------------------------ 7. terminal
TEXTS["terminal"] = {
    "title_en": "7. Terminal value: what the ship is worth at the end of the planning window",
    "title_fr": "7. Valeur terminale : ce que vaut le navire à la fin de la fenêtre de planification",
    "caption_en": "Climatological hold power [kW] (a) and learned 5-day value V_theta [MWh] for {date} (b) on the "
                  "40 km grid; hindsight bias [MWh and %] by month (c); error [MWh] of candidate values by held-out "
                  "month (d).",
    "caption_fr": "Puissance de tenue de position climatologique [kW] (a) et valeur apprise V_theta sur 5 jours [MWh] "
                  "au {date} (b) sur la grille de 40 km ; biais d'optimisme a posteriori [MWh et %] par mois (c) ; "
                  "erreur [MWh] des valeurs candidates par mois exclu (d).",
    "body_en": """**What it shows.** A 5-day DP ends at some node; if that node is given zero value, the plan will happily finish in a calm. The terminal value is the price put on arriving at a node: an estimate of the energy the ship will collect afterwards. Two candidates are mapped. (a) the climatological one: the mean station-keeping power of 2015 at each node, multiplied by the remaining hours (median {clim_med:.0f} kW, i.e. {clim120_med:.0f} MWh over 5 days). (b) V_theta, a gradient-boosted model that predicts the energy of the next 5 days from position, season, climatology, distance to coast and features of the forecast over the period; it is shown for {date}, with values from {vt_min:.0f} to {vt_max:.0f} MWh (median {vt_med:.0f}).

**How to read it.** Maps are in km on the planning grid, colour is kW in (a) and MWh over 5 days in (b); grey = land, coast buffer or outside ERA5. In (c), bars are the mean gap, in MWh, between the hindsight value (the best 5-day route knowing the wind) and what a causal router harvests from the same state, with the error bar the standard error; the orange line is that gap in % of the hindsight value. In (d) each curve is the mean absolute error of one candidate value against what routers really harvested in the held-out month (the model never saw that month).

**What to notice.**
- The hindsight value overestimates reality by {e0_all_pct:.1f} % on average ({e0_all_mwh:.1f} MWh out of {vhind_mwh:.0f}), from {e0_min_pct:.1f} % in {e0_min_month} to {e0_max_pct:.1f} % in {e0_max_month}: using it as terminal value would make the router too optimistic about the future.
- V_theta, learned on realised causal runs, has the lowest error ({mae_pol:.0f} MWh against {mae_clim_cal:.0f} for a recalibrated climatology, {mae_hind:.0f} for the value learned on hindsight and {mae_clim:.0f} for the raw climatology) and the best R2 ({r2_pol:.2f} against {r2_clim_cal:.2f} and {r2_hind:.2f}).

**Why it matters.** The terminal value steers the first days of every plan: without it, plans end in poor places; with a biased one, they chase optimistic spots. Using the climatology gains about 2 points of capacity factor in the year run (figure 8).

**Limits.** V_theta explains less than half of the variance (R2 {r2_pol:.2f}); it is trained on one year, so held-out months are the only honest test; the hindsight-bias statistics come from the 2015 rollouts only.""",
    "body_fr": """**Ce que montre la figure.** Une DP à 5 jours finit en un nœud ; si ce nœud vaut zéro, le plan finira volontiers dans un calme. La valeur terminale est le prix attribué à l'arrivée en un nœud : une estimation de l'énergie que le navire récoltera ensuite. Deux candidates sont cartographiées. (a) la climatologique : la puissance moyenne de tenue de position de 2015 en chaque nœud, multipliée par les heures restantes (médiane {clim_med:.0f} kW, soit {clim120_med:.0f} MWh sur 5 jours). (b) V_theta, un modèle à gradient boosting qui prédit l'énergie des 5 jours suivants à partir de la position, de la saison, de la climatologie, de la distance à la côte et de caractéristiques de la prévision sur la période ; il est montré pour le {date}, avec des valeurs de {vt_min:.0f} à {vt_max:.0f} MWh (médiane {vt_med:.0f}).

**Comment lire.** Les cartes sont en km sur la grille de planification, la couleur est en kW en (a) et en MWh sur 5 jours en (b) ; gris = terre, bande côtière ou hors ERA5. En (c), les barres sont l'écart moyen, en MWh, entre la valeur a posteriori (la meilleure route à 5 jours connaissant le vent) et ce que récolte un routeur causal depuis le même état, la barre d'erreur étant l'erreur standard ; la ligne orange est cet écart en % de la valeur a posteriori. En (d), chaque courbe est l'erreur absolue moyenne d'une valeur candidate face à ce que les routeurs ont réellement récolté pendant le mois exclu (le modèle n'a jamais vu ce mois).

**À retenir.**
- La valeur a posteriori surestime la réalité de {e0_all_pct:.1f} % en moyenne ({e0_all_mwh:.1f} MWh sur {vhind_mwh:.0f}), de {e0_min_pct:.1f} % en {e0_min_month} à {e0_max_pct:.1f} % en {e0_max_month} : l'utiliser comme valeur terminale rendrait le routeur trop optimiste sur l'avenir.
- V_theta, apprise sur des simulations causales réalisées, a la plus faible erreur ({mae_pol:.0f} MWh contre {mae_clim_cal:.0f} pour une climatologie recalibrée, {mae_hind:.0f} pour la valeur apprise sur l'a posteriori et {mae_clim:.0f} pour la climatologie brute) et le meilleur R2 ({r2_pol:.2f} contre {r2_clim_cal:.2f} et {r2_hind:.2f}).

**Pourquoi c'est important.** La valeur terminale oriente les premiers jours de chaque plan : sans elle les plans finissent en mauvais endroits ; biaisée, ils poursuivent des points trop optimistes. La climatologie apporte environ 2 points de facteur de charge sur la simulation annuelle (figure 8).

**Limites.** V_theta explique moins de la moitié de la variance (R2 {r2_pol:.2f}) ; elle est entraînée sur une seule année, les mois exclus sont donc le seul test honnête ; les statistiques de biais a posteriori viennent des seules simulations de 2015.""",
}

# --------------------------------------------------------------------------------- 8. results
TEXTS["results"] = {
    "title_en": "8. Results over 2015: capacity factor and gap to the oracle",
    "title_fr": "8. Résultats 2015 : facteur de charge et écart à l'oracle",
    "caption_en": "Monthly capacity factor [%] (a), gap to the oracle [percentage points of CF] (b), annual energy "
                  "budget [GWh] with annual CF (c) and cumulated shortfall [GWh] (d), year 2015, seed 1.",
    "caption_fr": "Facteur de charge mensuel [%] (a), écart à l'oracle [points de FC] (b), bilan énergétique annuel "
                  "[GWh] avec le FC annuel (c) et manque à gagner cumulé [GWh] (d), année 2015, graine 1.",
    "body_en": """**What it shows.** One year of 2015 ERA5 wind, one ship of 3 MW, five routers, the energy harvested measured on the true wind. The capacity factor (CF) is the energy divided by what 3 MW would give all year: 100 % means the ship produced 3 MW non-stop. The gap to the oracle is expressed in percentage points of CF, so that all figures are on the same base of 100 %.

**The five routers.** **Oracle**: rolling 15-day look-ahead on the true wind, refiner included; not causal, it is an approximate upper bound. **B0, optimal fixed station (perfect hindsight)**: the ship stays still, producing power by beam-reach tacks, at the best geographic point known with the benefit of hindsight (the point of the 2015 ERA5 truth with the highest mean hold power, at least 50 km from the coast, within 800 NM of 47N 6.5W). **B1**: 5-day DP on the control forecast, refined. **B1c**: B1 plus the climatological terminal value. **ENS**: ensemble DP with CVaR over 10 days, plus climatological terminal value and refiner.

**How to read it.** (a) one line per router, horizontal axis the months of 2015 (UTC). (b) bars give oracle CF minus router CF, in points. (c) stacked bars: energy while sailing and while holding, dashed boxes the energy missing to reach the oracle, labels the annual CF. (d) the shortfall to the oracle accumulated during the year.

**What to notice.**
- Annual CF: oracle {cf_or:.1f} %, ENS {cf_ens:.1f} %, B1c {cf_b1c:.1f} %, B1 {cf_b1:.1f} %, B0 {cf_b0:.1f} %. The gaps to the oracle are {gap_ens:.1f}, {gap_b1c:.1f}, {gap_b1:.1f} and {gap_b0:.1f} points. Even the optimal fixed station, which knows the whole year, loses {gap_b0:.1f} points: moving pays.
- The climatological terminal value is worth {clim_gain_pp:.1f} points (B1c versus B1); ENS adds another {ens_gain_pp:.1f} point(s), with large month-to-month noise.
- Seasons matter for everybody: the oracle ranges from {cfmin_or:.0f} % (worst month {cf_or_worst_m}) to {cfmax_or:.0f} % ({cf_or_best_m}); B1c loses from {gap_b1c_best:.1f} points ({gap_b1c_best_m}) to {gap_b1c_worst:.1f} points ({gap_b1c_worst_m}).

**Why it matters.** This is the scoreboard that the other figures try to explain: every model upstream (envelope, stencil, forecasts, terminal value) shows up as some points of CF here.

**Limits.** One year, one start, one seed per router: monthly differences of a few points are within noise (the seed-to-seed annual difference of B1c is 0.3 %). The oracle is an approximate bound, about 2 points optimistic.""",
    "body_fr": """**Ce que montre la figure.** Une année de vent ERA5 2015, un navire de 3 MW, cinq routeurs, l'énergie récoltée mesurée sur le vent réel. Le facteur de charge (FC) est l'énergie divisée par ce que donneraient 3 MW toute l'année : 100 % signifie que le navire a produit 3 MW sans arrêt. L'écart à l'oracle est exprimé en points de FC, de sorte que tous les chiffres sont sur la même base de 100 %.

**Les cinq routeurs.** **Oracle** : anticipation glissante de 15 jours sur le vent réel, raffineur inclus ; non causal, c'est une borne haute approximative. **B0, poste fixe optimal (avec clairvoyance)** : le navire reste immobile, produisant par bords de travers alternés, au meilleur point géographique connu a posteriori (le point de la vérité ERA5 2015 ayant la plus forte puissance moyenne de tenue de position, à au moins 50 km de la côte et à moins de 800 NM de 47N 6,5W). **B1** : DP à 5 jours sur la prévision de contrôle, raffinée. **B1c** : B1 avec la valeur terminale climatologique. **ENS** : DP d'ensemble avec CVaR sur 10 jours, plus valeur terminale climatologique et raffineur.

**Comment lire.** (a) une ligne par routeur, en abscisse les mois de 2015 (UTC). (b) les barres donnent le FC de l'oracle moins celui du routeur, en points. (c) barres empilées : énergie en navigation et en tenue de position, boîtes en tireté l'énergie manquante pour atteindre l'oracle, étiquettes le FC annuel. (d) le manque à gagner par rapport à l'oracle accumulé au cours de l'année.

**À retenir.**
- FC annuel : oracle {cf_or:.1f} %, ENS {cf_ens:.1f} %, B1c {cf_b1c:.1f} %, B1 {cf_b1:.1f} %, B0 {cf_b0:.1f} %. Les écarts à l'oracle sont de {gap_ens:.1f}, {gap_b1c:.1f}, {gap_b1:.1f} et {gap_b0:.1f} points. Même le poste fixe optimal, qui connaît toute l'année, perd {gap_b0:.1f} points : bouger rapporte.
- La valeur terminale climatologique vaut {clim_gain_pp:.1f} points (B1c contre B1) ; ENS ajoute {ens_gain_pp:.1f} point(s), avec un fort bruit d'un mois à l'autre.
- Les saisons comptent pour tous : l'oracle va de {cfmin_or:.0f} % (pire mois {cf_or_worst_m}) à {cfmax_or:.0f} % ({cf_or_best_m}) ; B1c perd de {gap_b1c_best:.1f} points ({gap_b1c_best_m}) à {gap_b1c_worst:.1f} points ({gap_b1c_worst_m}).

**Pourquoi c'est important.** C'est le tableau de score que les autres figures cherchent à expliquer : chaque modèle en amont (enveloppe, stencil, prévisions, valeur terminale) se retrouve ici en quelques points de FC.

**Limites.** Une année, un départ, une graine par routeur : des différences mensuelles de quelques points sont dans le bruit (l'écart annuel entre graines de B1c est de 0,3 %). L'oracle est une borne approximative, environ 2 points trop optimiste.""",
}

# ---------------------------------------------------------------------------------- 9. safety
TEXTS["safety"] = {
    "title_en": "9. Safety: distance to the coast and the Lorient corridor",
    "title_fr": "9. Sécurité : distance à la côte et couloir de Lorient",
    "caption_en": "Signed distance to coast (SDF) around Brittany [km] with the 20 km limit and the harbour corridor "
                  "(a, b); share of the year spent at each distance from land [%] (c); exact minimum margins of the "
                  "year runs [km] (d).",
    "caption_fr": "Distance signée à la côte (SDF) autour de la Bretagne [km] avec la limite de 20 km et le couloir "
                  "portuaire (a, b) ; part de l'année passée à chaque distance de la terre [%] (c) ; marges minimales "
                  "exactes des simulations annuelles [km] (d).",
    "body_en": """**What it shows.** The rule is simple: the ship must stay at least 20 km from the coast. The code represents the coast as a signed distance field (SDF): at each grid cell, the distance in km to the nearest land (positive at sea, negative on land). The DP, the refiner and the simulator all test the same condition SDF >= 20 km, on the bilinear interpolation of the field, along the whole straight chord of every move (not only at its ends).

**How to read it.** (a) the SDF in km (10 km grid, capped at 200), axes in km east and north of Lorient. The red line is the 20 km limit; the dashed black line is the limit once the harbour corridor is applied. (b) the required clearance as a function of the distance r to Lorient: 1 km at the port, ramping linearly to 20 km at 40 km, then constant. The corridor is not a special case in the solver: it is an SDF relaxation, SDF' = SDF + (20 km minus d_req), tested against 20 km, so every module keeps its code. (c) the cumulated share of the year spent below each distance to land, from the hourly tracks (log scale). (d) the exact minimum margin over the year, SDF minus 20 km, along the sailed chords.

**What to notice.**
- Without the corridor Lorient itself is unreachable (it lies inside the 20 km band); with it the port is feasible (SDF' = {relax_ok:.1f} km at the port, above the 20 km requirement).
- No router ever crossed the limit: zero violations and zero guard interventions on all year runs. The smallest margins of the moving routers are {mm_min:.2f} to {mm_max_routers:.2f} km (Oracle {mm_Oracle_REF_H:.2f}, B1 {mm_B1_5d_REF:.2f}, B1c {mm_B1c_5d_REF:.2f}, ENS {mm_ENS_REF:.2f} km): they sail right along the limit, as an optimiser does, but never beyond. The static B0 has a margin of hundreds of km.
- Routers spend {frac100_B1c_5d_REF:.0f} % (B1c) to {frac100_B1_5d_REF:.0f} % (B1) of the year within 100 km of the coast.

**Why it matters.** Safety is a hard constraint, not a penalty: the plan is either feasible or not.

**Limits.** Distance only (no traffic, shallows, restricted areas or swell); the coast comes from a land mask on a 10 km grid (40 km in the routing grid), so the margin is a model margin, to be confirmed with finer charts for operations.""",
    "body_fr": """**Ce que montre la figure.** La règle est simple : le navire doit rester à au moins 20 km de la côte. Le code représente la côte par un champ de distance signée (SDF) : en chaque case, la distance en km à la terre la plus proche (positive en mer, négative sur terre). La DP, le raffineur et le simulateur testent tous la même condition SDF >= 20 km, sur l'interpolation bilinéaire du champ, le long de toute la corde de chaque déplacement (pas seulement à ses extrémités).

**Comment lire.** (a) le SDF en km (grille de 10 km, plafonné à 200), axes en km à l'est et au nord de Lorient. La ligne rouge est la limite de 20 km ; le tireté noir est la limite une fois le couloir portuaire appliqué. (b) la distance requise en fonction de la distance r à Lorient : 1 km au port, croissant linéairement jusqu'à 20 km à 40 km, puis constante. Le couloir n'est pas un cas particulier du solveur : c'est une relaxation du SDF, SDF' = SDF + (20 km moins d_req), testée contre 20 km, de sorte que chaque module garde son code. (c) la part cumulée de l'année passée en dessous de chaque distance à la terre, d'après les trajectoires horaires (échelle log). (d) la marge minimale exacte sur l'année, SDF moins 20 km, le long des cordes navigées.

**À retenir.**
- Sans le couloir, Lorient elle-même est inaccessible (elle se trouve dans la bande des 20 km) ; avec lui le port est faisable (SDF' = {relax_ok:.1f} km au port, au-dessus des 20 km requis).
- Aucun routeur n'a jamais franchi la limite : zéro violation et zéro intervention du garde-fou sur toutes les simulations annuelles. Les plus petites marges des routeurs mobiles vont de {mm_min:.2f} à {mm_max_routers:.2f} km (Oracle {mm_Oracle_REF_H:.2f}, B1 {mm_B1_5d_REF:.2f}, B1c {mm_B1c_5d_REF:.2f}, ENS {mm_ENS_REF:.2f} km) : ils longent la limite, comme le fait un optimiseur, sans jamais la dépasser. Le B0 statique a une marge de centaines de km.
- Les routeurs passent de {frac100_B1c_5d_REF:.0f} % (B1c) à {frac100_B1_5d_REF:.0f} % (B1) de l'année à moins de 100 km de la côte.

**Pourquoi c'est important.** La sécurité est une contrainte dure, pas une pénalité : le plan est faisable ou il ne l'est pas.

**Limites.** Distance seulement (pas de trafic, hauts-fonds, zones interdites ni houle) ; la côte vient d'un masque de terre sur grille de 10 km (40 km sur la grille de routage), la marge est donc une marge de modèle, à confirmer avec des cartes plus fines pour l'exploitation.""",
}


# ============================================================ v4.7: story order, numbering, new texts
TEXTS["architecture"] = {
    "title_en": "The router in one picture: three layers between the weather and the capacity factor",
    "title_fr": "Le routeur en une image : trois couches entre la météo et le facteur de charge",
    "caption_en": "Block diagram: inputs (weather, ship, coast), strategic exploration on a {dx:.0f} km x {dt:.0f} h graph with {K} macro-arcs, tactical refinement at {stage_min:.0f} min over {trunk:.0f} h, execution with a {replan:.0f} h replanning cycle, outputs (CF [%], gap [points]).",
    "caption_fr": "Schéma bloc : entrées (météo, navire, côte), exploration stratégique sur un graphe de {dx:.0f} km x {dt:.0f} h à {K} macro-arcs, raffinement tactique au pas de {stage_min:.0f} min sur {trunk:.0f} h, exécution avec replanification toutes les {replan:.0f} h, sorties (CF [%], écart [points]).",
    "body_en": """**Where we are in the story.** This is the map of the whole guide: each following figure zooms on one box of this diagram.

**What it shows.** The router is a stack of three layers fed by three kinds of input. **Inputs**: the weather (the ERA5 truth in a backtest, or forecast ensembles with their latency), the ship (the BETA power polar, turned into a power envelope) and the coast (a signed distance field plus the Lorient port corridor). **1. Strategic exploration** reduces the ensemble to {k} scenarios, then runs one stochastic dynamic programme (DP) per scenario on a {dx:.0f} km x {dt:.0f} h graph, where each node offers {K} macro-arcs ({n_one} one-step and {n_two} two-step moves plus the hold). It looks 10-15 days ahead, aggregates the scenarios with a tail-risk measure (CVaR), closes the horizon with a terminal value, and keeps only a non-anticipative {trunk:.0f} h trunk: the part of the plan that is common to all scenarios. **2. Tactical refinement** turns this trunk into a smooth trajectory by continuous optimisation (CasADi/IPOPT) over {trunk:.0f} h at {stage_min:.0f} min ({stages} stages), with an exact coast constraint and the DP value as terminal reward. **3. Execution** applies the first {replan:.0f} h, lets the simulator (with a safety guard) move the ship, then replans with the new forecasts.

**How to read it.** Boxes are computations, arrows are data flows with their units and resolutions; the orange dashed arrow is the replanning loop; the ruler at right gives the time scales from {replan:.0f} h to 15 days.

**What to notice.** Each layer trades fidelity for reach: the coarse graph sees far but roughly, the refiner sees {trunk:.0f} h finely, and the loop corrects forecast errors every {replan:.0f} h.

**Why it matters.** Every result in the last figure is the output of this chain; comparing routers means switching layers on or off.

**What to look at in the inspector.** Overview tab: the router list (B0, B1, B1c, ENS, REF, Oracle) corresponds to nested subsets of these layers; Explorer tab: the track of any router shows the replanning loop in action.""",
    "body_fr": """**Où nous en sommes.** C'est la carte de tout le guide : chaque figure suivante zoome sur une case de ce schéma.

**Ce que montre la figure.** Le routeur est une pile de trois couches alimentée par trois types d'entrées. **Entrées** : la météo (la vérité ERA5 en backtest, ou des ensembles de prévisions avec leur latence), le navire (la polaire de puissance BETA, transformée en enveloppe de puissance) et la côte (un champ de distance signée plus le couloir du port de Lorient). **1. Exploration stratégique** : réduit l'ensemble à {k} scénarios, puis résout une programmation dynamique (DP) stochastique par scénario sur un graphe de {dx:.0f} km x {dt:.0f} h, où chaque nœud offre {K} macro-arcs ({n_one} à un pas, {n_two} à deux pas, plus l'attente). Elle regarde 10 à 15 jours, agrège les scénarios par une mesure de risque de queue (CVaR), ferme l'horizon par une valeur terminale, et ne garde qu'un tronc non anticipatif de {trunk:.0f} h : la partie du plan commune à tous les scénarios. **2. Raffinement tactique** : transforme ce tronc en trajectoire lisse par optimisation continue (CasADi/IPOPT) sur {trunk:.0f} h au pas de {stage_min:.0f} min ({stages} étapes), avec une contrainte de côte exacte et la valeur DP comme récompense terminale. **3. Exécution** : applique les {replan:.0f} premières heures, laisse le simulateur (avec garde de sécurité) déplacer le navire, puis replanifie avec les nouvelles prévisions.

**Comment lire.** Les cases sont des calculs, les flèches des flux de données avec leurs unités et résolutions ; la flèche orange en tireté est la boucle de replanification ; la règle à droite donne les échelles de temps de {replan:.0f} h à 15 jours.

**À retenir.** Chaque couche échange fidélité contre portée : le graphe grossier voit loin mais grossièrement, le raffineur voit {trunk:.0f} h finement, et la boucle corrige les erreurs de prévision toutes les {replan:.0f} h.

**Pourquoi c'est important.** Chaque résultat de la dernière figure sort de cette chaîne ; comparer les routeurs, c'est activer ou désactiver des couches.

**À regarder dans l'inspecteur.** Onglet Vue d'ensemble : la liste des routeurs (B0, B1, B1c, ENS, REF, Oracle) correspond à des sous-ensembles emboîtés de ces couches ; onglet Explorateur : la trace d'un routeur montre la boucle de replanification à l'œuvre.""",
}

TEXTS["ensemble"] = {
    "title_en": "Ensembles and risk: from 20 forecasts to 6 scenarios and a tail-risk objective",
    "title_fr": "Ensembles et risque : de 20 prévisions à 6 scénarios et un objectif de risque de queue",
    "caption_en": "Wind speed [m/s] at the ship for the 20 members, the {k} medoids and the truth, issue {issue} (a); members in the plane of the first two EOF scores, clustered (b); mean hold power over days 2-5 [kW] per member with mean and CVaR 20 % (c); scenario weights [%] and power [kW] (d).",
    "caption_fr": "Vitesse du vent [m/s] au navire pour les 20 membres, les {k} médoïdes et la vérité, émission du {issue} (a) ; membres dans le plan des deux premiers scores EOF, regroupés (b) ; puissance moyenne en attente sur les jours 2-5 [kW] par membre, avec moyenne et CVaR 20 % (c) ; poids des scénarios [%] et puissance [kW] (d).",
    "body_en": """**Where we are in the story.** After the forecast verification (Fig. 3) and the DP graph (Fig. 6), this figure shows how the DP is fed with uncertainty; the next one closes the horizon with a terminal value.

**What it shows.** Solving the DP on 20 members would be too slow, so the ensemble is reduced. The members are projected on empirical orthogonal functions (EOF: the dominant spatial patterns of the ensemble variability), then grouped by k-medoids (PAM) into {k} clusters, each represented by a real member (the medoid) with a weight equal to its cluster share. One DP is solved per medoid.

**How to read it.** (a) wind speed in m/s against days since the issue: grey = the 14 other members, colours = medoids, black = truth; the shaded 48 h is the trunk on which a single plan is imposed. (b) each dot is a member, a star its medoid. (c) each bar is a member's mean hold power over days 2-5 in kW; the dashed line is the CVaR at 20 %, the mean of the worst 20 % of outcomes. (d) weights and powers of the {k} scenarios.

**What to notice.**
- Members agree for the first day and spread to {w_rng5:.0f} m/s at day 5; the truth stays inside the cloud, which is what an ensemble is for.
- {n_modes} EOF modes keep {cum_modes:.0f} % of the variance; weights span {w_min:.0f} to {w_max:.0f} %.
- The {k} scenarios give mean {mean_med:.0f} kW and CVaR {cvar_med:.0f} kW against {mean_all:.0f} / {cvar_all:.0f} kW for all 20: the reduction preserves the mean and, roughly, the tail.

**Why it matters.** The router optimises a blend of the mean and the CVaR: it avoids plans that are good on average but disastrous in a minority of scenarios, and the non-anticipative trunk prevents it from betting on one scenario in the next 48 h.

**Limits.** Only {k} scenarios, chosen on the wind alone; the CVaR is estimated on few points.

**What to look at in the inspector.** Explorer tab: compare ENS with B1 on a stormy week (ENS keeps away from risky areas); Overview tab: the CF and gap of ENS versus B1.""",
    "body_fr": """**Où nous en sommes.** Après la vérification des prévisions (Fig. 3) et le graphe DP (Fig. 6), cette figure montre comment la DP reçoit l'incertitude ; la suivante ferme l'horizon par une valeur terminale.

**Ce que montre la figure.** Résoudre la DP sur 20 membres serait trop lent : l'ensemble est donc réduit. Les membres sont projetés sur des fonctions orthogonales empiriques (EOF : les structures spatiales dominantes de la variabilité de l'ensemble), puis regroupés par k-médoïdes (PAM) en {k} classes, chacune représentée par un membre réel (le médoïde) de poids égal à la part de sa classe. Une DP est résolue par médoïde.

**Comment lire.** (a) vitesse du vent en m/s selon les jours depuis l'émission : gris = les 14 autres membres, couleurs = médoïdes, noir = vérité ; les 48 h ombrées sont le tronc sur lequel un plan unique est imposé. (b) chaque point est un membre, chaque étoile son médoïde. (c) chaque barre est la puissance moyenne en attente d'un membre sur les jours 2-5, en kW ; le tireté est la CVaR à 20 %, moyenne des 20 % de pires issues. (d) poids et puissances des {k} scénarios.

**À retenir.**
- Les membres s'accordent le premier jour et divergent de {w_rng5:.0f} m/s à 5 jours ; la vérité reste dans le nuage, ce à quoi sert un ensemble.
- {n_modes} modes EOF conservent {cum_modes:.0f} % de la variance ; les poids vont de {w_min:.0f} à {w_max:.0f} %.
- Les {k} scénarios donnent une moyenne de {mean_med:.0f} kW et une CVaR de {cvar_med:.0f} kW contre {mean_all:.0f} / {cvar_all:.0f} kW pour les 20 : la réduction préserve la moyenne et, à peu près, la queue.

**Pourquoi c'est important.** Le routeur optimise un mélange de la moyenne et de la CVaR : il évite les plans bons en moyenne mais désastreux dans une minorité de scénarios, et le tronc non anticipatif l'empêche de parier sur un seul scénario dans les 48 h à venir.

**Limites.** Seulement {k} scénarios, choisis sur le vent seul ; la CVaR est estimée sur peu de points.

**À regarder dans l'inspecteur.** Onglet Explorateur : comparer ENS et B1 lors d'une semaine de tempête (ENS évite les zones à risque) ; onglet Vue d'ensemble : le CF et l'écart d'ENS par rapport à B1.""",
}

# story order: id -> (number, short title EN, short title FR, previous/next line EN, FR, inspector pointers EN, FR)
_ORDER = ["architecture", "polar", "forecast", "safety", "envelope", "dp", "ensemble", "terminal", "refiner", "mpc", "results"]
_SHORT = {
    "polar": ("The ship and its power polar", "Le navire et sa polaire de puissance"),
    "forecast": ("Weather and forecasts: how wrong are they?", "Météo et prévisions : quelle erreur ?"),
    "safety": ("Coast and safety constraints", "Côte et contraintes de sécurité"),
    "envelope": ("Power envelope: why zig-zagging beats any single heading", "Enveloppe de puissance : pourquoi louvoyer bat tout cap unique"),
    "dp": ("Exploration: dynamic programming on the space-time graph", "Exploration : programmation dynamique sur le graphe espace-temps"),
    "terminal": ("Terminal value and the hindsight bias E0", "Valeur terminale et biais de clairvoyance E0"),
    "refiner": ("Refinement: from the grid path to a smooth trajectory", "Raffinement : du chemin sur grille à une trajectoire lisse"),
    "mpc": ("Execution: receding-horizon replanning (MPC)", "Exécution : replanification à horizon glissant (MPC)"),
    "results": ("Results over 2015: capacity factor and gap to the oracle", "Résultats 2015 : facteur de charge et écart à l'oracle"),
}
_NAV = {  # (where we are EN, FR)
    "polar": ("Input 1/3, after the architecture (Fig. 1): the ship's power as a function of wind and speed; the next figure adds the weather.",
              "Entrée 1/3, après l'architecture (Fig. 1) : la puissance du navire selon le vent et la vitesse ; la figure suivante ajoute la météo."),
    "forecast": ("Input 2/3: the weather the router actually sees (forecasts, not truth); the next figure adds the coast constraints.",
                 "Entrée 2/3 : la météo réellement vue par le routeur (prévisions, pas vérité) ; la figure suivante ajoute les contraintes de côte."),
    "safety": ("Input 3/3: where the ship may go; next, the polar of Fig. 2 is turned into rewards (Fig. 5).",
               "Entrée 3/3 : où le navire peut aller ; ensuite, la polaire de la Fig. 2 devient une récompense (Fig. 5)."),
    "envelope": ("From inputs to rewards: this is the power the DP collects per step; the next figure builds the graph on which it is accumulated.",
                 "Des entrées aux récompenses : c'est la puissance que la DP collecte à chaque pas ; la figure suivante construit le graphe où elle est cumulée."),
    "dp": ("Exploration layer, step 1: one deterministic DP on the 40 km x 3 h graph; the next figure feeds it with several scenarios.",
           "Couche d'exploration, étape 1 : une DP déterministe sur le graphe de 40 km x 3 h ; la figure suivante l'alimente avec plusieurs scénarios."),
    "terminal": ("Exploration layer, closing the horizon: after the scenarios (Fig. 7), what the ship is worth at the end of the window; next, the refinement layer.",
                 "Couche d'exploration, fermeture de l'horizon : après les scénarios (Fig. 7), ce que vaut le navire en fin de fenêtre ; ensuite, la couche de raffinement."),
    "refiner": ("Layer 2: it takes the 48 h trunk of the exploration (Figs. 6-8) and smooths it; the next figure shows the replanning loop around it.",
                "Couche 2 : elle reprend le tronc de 48 h de l'exploration (Fig. 6-8) et le lisse ; la figure suivante montre la boucle de replanification qui l'entoure."),
    "mpc": ("Layer 3: the loop that applies 6 h of plan and replans; the last figure shows what all this earns over a year.",
            "Couche 3 : la boucle qui applique 6 h de plan puis replanifie ; la dernière figure montre ce que tout cela rapporte sur un an."),
    "results": ("The conclusion: outputs of the whole chain of Fig. 1, over the year 2015.",
                "La conclusion : sorties de toute la chaîne de la Fig. 1, sur l'année 2015."),
}
_INSP = {
    "polar": ("Polar tab: the same net-power polar, per wind speed.", "Onglet Polaire : la même polaire de puissance nette, par vitesse de vent."),
    "forecast": ("Explorer tab: the wind map and the forecast layers along a router track.", "Onglet Explorateur : la carte de vent et les couches de prévision le long d'une trace."),
    "safety": ("Explorer tab: the coast layer and the minimum margin of each router.", "Onglet Explorateur : la couche côte et la marge minimale de chaque routeur."),
    "envelope": ("Polar tab: compare the single-heading polar with the envelope-based reward.", "Onglet Polaire : comparer la polaire à cap unique et la récompense issue de l'enveloppe."),
    "dp": ("Explorer tab: the DP value field and the Oracle track.", "Onglet Explorateur : le champ de valeur DP et la trace de l'Oracle."),
    "terminal": ("Overview tab: the E0 bias and the climatology row of the router cards.", "Onglet Vue d'ensemble : le biais E0 et la ligne climatologie des fiches routeur."),
    "refiner": ("Explorer tab: compare REF and ENS tracks over the same days.", "Onglet Explorateur : comparer les traces REF et ENS sur les mêmes jours."),
    "mpc": ("Explorer tab: step through the plans issued every 6 h along a B1 track.", "Onglet Explorateur : parcourir les plans émis toutes les 6 h le long d'une trace B1."),
    "results": ("Overview tab and Seasons tab: monthly CF and gaps per router.", "Onglets Vue d'ensemble et Saisons : CF mensuel et écarts par routeur."),
}
_HONEST_ENV = (
    "\n\n**Known limitation (planned for S5).** Manoeuvre losses (tack, gybe, heading change) are currently modelled only through the availability factor of the envelope mixing; abrupt heading changes in the DP and refiner tracks are not penalised.",
    "\n\n**Limite connue (prévue en S5).** Les pertes de manoeuvre (virement, empannage, changement de cap) ne sont modélisées que par le facteur de disponibilité du mélange de l'enveloppe ; les changements de cap brusques dans les traces DP et raffineur ne sont pas pénalisés.",
)


def _finish():
    n = len(_ORDER)
    for i, fid in enumerate(_ORDER):
        t = TEXTS[fid]
        if fid != "architecture":
            short = _SHORT.get(fid)
            if short:
                t["title_en"], t["title_fr"] = short
        base_en, base_fr = t["title_en"], t["title_fr"]
        base_en = base_en.split(". ", 1)[-1] if base_en[:2].strip(". ").isdigit() else base_en
        base_fr = base_fr.split(". ", 1)[-1] if base_fr[:2].strip(". ").isdigit() else base_fr
        t["title_en"] = f"Fig. {i + 1}/{n} · {base_en}"
        t["title_fr"] = f"Fig. {i + 1}/{n} · {base_fr}"
        if fid in _NAV:
            t["body_en"] = f"**Where we are in the story.** {_NAV[fid][0]}\n\n" + t["body_en"]
            t["body_fr"] = f"**Où nous en sommes.** {_NAV[fid][1]}\n\n" + t["body_fr"]
        if fid in _INSP:
            t["body_en"] += f"\n\n**What to look at in the inspector.** {_INSP[fid][0]}"
            t["body_fr"] += f"\n\n**À regarder dans l'inspecteur.** {_INSP[fid][1]}"
        if fid in ("envelope", "refiner"):
            t["body_en"] += _HONEST_ENV[0]
            t["body_fr"] += _HONEST_ENV[1]


_finish()
TEXTS = {k: TEXTS[k] for k in _ORDER}
