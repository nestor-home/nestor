# Bancs d'essai (`nestor bench`) : la commande, ses erreurs, les tableaux et le rapport HTML.

## La commande.

bench-help = mesure Nestor sur un jeu de données et compare des configurations
bench-list-help = les suites installées
bench-run-help = lance une suite sur une ou plusieurs variantes
bench-run-description = Lance chaque cas d'une suite sur chaque variante, à chaque répétition. Une variante est un fragment de nestor.yaml (le modèle à tester…), avec les réglages de la suite sous `bench:`. Chaque appel au modèle est mesuré et mis en cache : --replay rejoue une course sans appeler de fournisseur.
bench-suite-help = la suite à lancer (voir `nestor bench list`)
bench-variant-help = un fichier de variante ; répéter l'option pour en comparer plusieurs
bench-repeat-help = nombre de passages sur chaque cas (par défaut : 1)
bench-cases-help = votre propre jeu de données, au format JSONL de la suite (par défaut : celui de la suite)
bench-replay-help = rejoue les réponses en cache, sans appeler de fournisseur
bench-seed-help = la seed de l'ordre des cas et des clés du cache (par défaut : 0)
bench-concurrency-help = cas traités en même temps (par défaut : 4 ; 1 pour des latences plus stables)
bench-results-help = où écrire les courses (par défaut : bench-results)
bench-cache-help = où mettre en cache les réponses des modèles (par défaut : .bench-cache)
bench-compare-help = compare des courses côte à côte, dans le terminal et en page HTML
bench-runs-help = le dossier d'une course, ou son results.json
bench-out-help = la page HTML à écrire (par défaut : à côté de la première course)
bench-report-help = affiche le tableau et les cas à relire d'une course, et régénère son rapport HTML

bench-list-line = { $suite } : { $description }
bench-running = { $suite } : { $cases } cas × { $variants ->
    [one] 1 variante
   *[other] { $variants } variantes
} × { $repeat ->
    [one] 1 répétition
   *[other] { $repeat } répétitions
}{ $replayed ->
    [yes] , rejoué depuis le cache
   *[no] {""}
}
bench-wrote = écrit : { $path }
bench-failed = nestor bench : { $reason }

## Erreurs.

bench-unknown-suite = aucune suite nommée { $suite } (installées : { $known })
bench-dataset-unreadable = impossible de lire le jeu de données { $path }
bench-dataset-invalid-line = { $path }, ligne { $line } : pas un objet JSON
bench-variant-unreadable = { $path } n'est pas un dictionnaire YAML (un fragment de nestor.yaml)
bench-variant-invalid = { $path }, section bench : { $problems }
bench-variant-not-a-model = { $path } : { $kind } ne fournit pas le type de modèle attendu par ce rôle
bench-no-dataset = { $suite } n'a pas de jeu de données intégré : passez-en un avec --cases
bench-variant-no-voices = { $path } : cette suite demande un modèle de reconnaissance du locuteur, renseignez voices.embedder
bench-no-recording = aucune réponse enregistrée pour le cas { $case } ({ $role }) : lancez-le une fois sans --replay
bench-cache-unreadable = le fichier de cache { $path } est corrompu : supprimez-le
bench-results-unreadable = { $path } n'est pas une course (pas de results.json lisible)
bench-same-variant-name = deux variantes portent le même nom ({ $names }) : renseignez bench.name dans l'une d'elles

## Tableaux et rapport.

bench-table-header = { $suite } · jeu { $dataset } (v{ $version }, { $cases } cas) · { $repeat ->
    [one] 1 répétition
   *[other] { $repeat } répétitions
} · seed { $seed }
bench-column-metric = mesure
bench-table-best = { $mark } meilleur de la ligne
bench-different-datasets = attention : ces courses n'ont pas utilisé le même jeu de données
bench-table-run = { $variant } : servi par { $served }{ $replayed ->
    [yes] , rejoué
   *[no] {""}
}
bench-report-title = Rapport de banc
bench-report-metrics = Mesures
bench-report-best = La meilleure valeur de chaque ligne est mise en avant.
bench-report-charts = Graphiques
bench-report-runs = Courses
bench-report-findings = Cas à relire
bench-report-no-findings = Rien à relire : aucun cas n'a mal tourné.
bench-report-replayed = rejoué
bench-column-variant = variante
bench-column-served = servi par
bench-column-config = configuration
bench-column-dataset = jeu de données
bench-column-repeat = répétitions / seed
bench-column-version = Nestor
bench-column-started = début

## Mesures de chaque course.

bench-metric-calls-per-case = appels au modèle par cas
bench-metric-case-latency-p50 = latence par cas, médiane
bench-metric-case-latency-p95 = latence par cas, p95
bench-metric-call-latency-p50 = latence par appel, médiane
bench-metric-call-latency-p95 = latence par appel, p95
bench-metric-input-tokens-per-case = tokens en entrée par cas
bench-metric-cached-input-share = part des tokens en entrée lus en cache
bench-metric-output-tokens-per-case = tokens en sortie par cas
bench-metric-cost-per-1000-cases = coût pour 1000 cas
bench-metric-provider-errors = erreurs du fournisseur
