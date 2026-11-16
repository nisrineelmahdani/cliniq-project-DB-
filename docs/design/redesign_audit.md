# DEV-010 — Audit, direction et vérification du redesign

## Audit initial, captures réelles du 16 novembre 2026

Captures Playwright locales, viewport 1440 × 1050, exclusivement sur le seed fictif
de cliniq_test_dev. Le serveur avait été arrêté après expiration de sa session ;
il a été relancé avant les captures acceptées. Une capture refusée pour connexion
indisponible n'est pas utilisée comme preuve.

1. Dashboard — `before_dashboard.png` : navigation automatique par noms de fichiers,
   pages inachevées exposées, identité disparue, deux titres et un long préambule
   avant les indicateurs. Les données SQL sont existantes et conservées.
2. Patients — `before_patients.png` : le dossier sélectionné vient après la liste ;
   la création est noyée dans un sélecteur. Absence de panneau d'orientation avant
   sélection. Étiquette de recherche et données natives présentes.
3. Agenda — `before_appointments.png` : filtres longs avant les créneaux, lignes de
   planning réunissant heure, patient, médecin et statut sans hiérarchie.
4. Hospitalisations — `before_hospitalizations.png` : les filtres/pagination occupent
   presque toute la première vue ; les dates et la disponibilité arrivent tard.

## Direction annoncée avant implémentation

Navigation persistante en trois groupes, sept pages actives explicites, logo
médical Material Symbols, pied avec version. En-tête unique et CTA prioritaire.
Dashboard orienté activité/capacité ; annuaire et dossier côte à côte ; recherche
visible et filtres détaillés repliables ; formulaires natifs sur surfaces blanches,
contexte de soin persistant, statut sémantique distinct de la marque.

## Système visuel et interactions

- Rose #E84C71, corail #FF7B89, blush #FCE7ED, fond #FFF8FA, surfaces #FFFFFF,
  texte #442638, secondaire #806775. Rouge profond #C93F55 pour les contrôles
  principaux avec texte blanc : contraste supérieur au rose clair. Le rose reste
  la couleur des accents, de l'état actif et du graphique d'activité.
- Inter avec repli système en l'absence de police distante ; Material Symbols
  natifs. Aucun logo SVG artisanal, dépendance graphique ou donnée simulée.
- Surfaces de 18 px, bordures neutres, ombre légère, hiérarchie compacte ; CSS
  ciblé sur les classes propres à l'application et les clés explicites des
  conteneurs, sans classes générées ni sélecteurs data-testid.
- Focus visible bleu, transitions désactivées si reduced-motion. Succès vert,
  avertissement ambre, prévu bleu, annulation rouge, terminé neutre. Les libellés
  restent textuels : le sens ne dépend pas uniquement de la couleur.
- Dates formatées uniformément dans les tableaux ; colonnes natives responsives.
- Boutons d'en-tête ouvrant directement la création existante, clés de formulaire
  conservées, validation et protection des éditions périmées inchangées.
- Retraits de médicament et affectation séparés et toujours confirmés explicitement.
- Indicateurs, capacité et graphiques proviennent exclusivement du snapshot SQL
  existant ; pas de croissance ou tendance fabriquée.

Les états rapides ne remplacent ni les confirmations ni les vérifications métier.
Aucun repository, service, schéma, trigger, index ou CIF n'est modifié par DEV-010.
Les résultats de QA et captures finales sont ajoutés après vérification.

## Résultats finaux DEV-010

- **427 tests pytest réussis, 0 échec, 0 erreur, 0 ignoré**, dont **135 cas MySQL**,
  en 20,33 s ; **74 fichiers Python** contrôlés par mypy sans erreur.
- Les 418 cas préexistants sont conservés. Un test de recherche utilisait le
  premier bouton : il cible maintenant la clé du vrai bouton Rechercher, car une
  action de création figure désormais en tête. Aucune assertion métier supprimée.
- Neuf nouveaux cas couvrent les cinq actions prioritaires, la capacité vide sans
  valeur inventée, l'échappement HTML d'un statut arbitraire, l'absence de boutons
  de pagination inutiles et le fonctionnement de la pagination à plusieurs pages.
- Répétition réelle sur le frontend final : **68 interactions UI et 23 contrôles**
  avec SQL indépendant. Patient créé/recherché/modifié ; RDV créé/filtré/modifié ;
  consultation liée puis modifiée ; deux médicaments ajoutés, quantité corrigée,
  retrait refusé sans confirmation puis accepté ; admission/lit, correction,
  sortie, historique et occupation ; affectation, réaffectation et retrait confirmé.
  Trigger 1644 et CIF 1062 ont aussi été vérifiés directement dans le test.
- Playwright/Chrome local autorisé : sept pages à **1440 × 1050** et **390 × 844**,
  un H1 par page, aucun débordement horizontal du document ni alerte d'erreur.
  Les tableaux conservent leur défilement interne natif quand nécessaire.
- Recherche clavier avec saisie, flèche puis Entrée dans les sélecteurs vérifiée.
  Focus clavier initial sur le lien d'évitement natif. Menu mobile ouvert puis
  navigation Patients réussie. Pas d'audit exhaustif de lecteur d'écran/WCAG.
- 27 fichiers protégés (modèles, SQL, repositories, services et connexion) gardent
  leur empreinte. Aucune écriture de développement et aucun changement global MySQL.
  Tous les essais d'écriture et captures utilisent le seed fictif de cliniq_test_dev.
- Pas de dépendance applicative ajoutée : Playwright était installé hors projet
  seulement pour le contrôle visuel. Les données figurant dans les captures sont
  réellement lues en SQL, y compris le patient fictif DEV010 ajouté pour les essais.

Le premier contrôle visuel a révélé un ancien bloc de titre HTML encore présent
sur Prescriptions ; il a été retiré. Le padding mobile du panneau d'accueil et
les sélecteurs sous de longues listes ont aussi été corrigés avant validation.
Les boutons de pagination sont maintenant masqués uniquement lorsque tout tient
sur une page. Le serveur a été relancé pour éviter le cache de l'ancien module UI.

## Captures acceptées

Les fichiers `before_*.png` sont les quatre états initiaux. Les fichiers
`after_<page>_desktop.png` et `after_<page>_mobile.png` couvrent les sept pages :
dashboard, patients, appointments, consultations, prescriptions,
hospitalizations et medical_acts. Ils proviennent du navigateur réel, sans
retouche ou données superposées. Captures complémentaires :

- `after_dashboard_detail_desktop.png` : activité et capacité ;
- `after_patient_detail_desktop.png` : annuaire et dossier côte à côte ;
- `after_patient_form_desktop.png` : identité/coordonnées regroupées ;
- `after_prescriptions_context_desktop.png` : contexte sélectionné et liste repliée ;
- `after_occupancy_desktop.png` : disponibilité par chambre et lit ;
- `after_navigation_mobile.png` : menu mobile.

## Fichiers DEV-010

- `app.py`, `.streamlit/config.toml` ;
- `ui/design.py`, `ui/styles.css`, `ui/clinical_forms.py`, `ui/patient_form.py`,
  `ui/hospitalization_form.py`, `ui/medical_act_views.py` ;
- `pages/dashboard.py`, `pages/patients.py`, `pages/appointments.py`,
  `pages/consultations.py`, `pages/prescriptions.py`, `pages/hospitalizations.py`,
  `pages/medical_acts.py` ;
- `tests/test_dev003_ui.py`, `tests/test_dev010_ui.py`, `README.md` ;
- ce rapport, `qa_results.json` et les 24 captures PNG du dossier `docs/design/`.

## Limites

Les sept parcours restent soumis aux limites métier déjà documentées : pas de
trigger universel de chevauchement, ni nouveau modèle d'audit ou d'authentification.
La réponse mobile a été contrôlée dans Chromium émulé, pas sur appareils physiques
ni tous les navigateurs. Les polices distantes nécessitent le réseau ; le repli
système fonctionne hors connexion. Aucun test de conformité WCAG intégrale n'est
revendiqué. Les styles évitent les sélecteurs privés, mais les widgets et tableaux
restent ceux de Streamlit. Après mise à jour, redémarrer l'instance existante pour
recharger les composants partagés. Le serveur temporaire de QA est arrêté ;
l'instance utilisateur n'est ni arrêtée ni reconfigurée.

### Observation finale sur les données de développement

Le contrôle final en lecture seule retrouve 15 tables et les colonnes/clés
inchangées. La base compte **90 lignes**, avec **un patient supplémentaire** par
rapport à la référence DEV-009 (89). Les sept patients d'origine gardent leurs
empreintes, et toutes les autres tables conservent leur contenu. L'origine et
l'instant de cet ajout ne sont pas déterminés ; DEV-010 n'a émis aucune écriture
sur cliniq_db. Le nouveau dossier est conservé sans intervention. Ne pas présenter
ce constat comme une réinitialisation ou une correction de données. La base test,
elle, a bien retrouvé ses 89 lignes après les essais.
