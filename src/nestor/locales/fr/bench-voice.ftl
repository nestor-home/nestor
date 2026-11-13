# Les bancs de la voix : transcription et synthèse.

bench-transcription-description = à quel point un modèle de transcription entend bien des enregistrements en français, et à quelle vitesse
bench-transcription-no-header = le jeu doit commencer par {"{"}"dataset": "transcription", "version": <nombre>, "audio": <dossier>{"}"}
bench-transcription-bad-case = cas { $case } : il lui faut un "text" et un "file" présent dans le dossier audio
bench-transcription-wer = taux d'erreur sur les mots
bench-transcription-failed = enregistrements en échec
bench-transcription-latency-p50 = latence d'un enregistrement, médiane
bench-transcription-latency-p95 = latence d'un enregistrement, 95e centile
bench-transcription-rtf-p50 = facteur temps réel, médiane (secondes de calcul par seconde de parole)
bench-transcription-cold-start = démarrage à froid (chargement du modèle)
bench-transcription-memory = mémoire ajoutée au chargement
bench-transcription-worst = enregistrements les plus mal entendus
bench-transcription-heard = dit : { $said } · entendu : { $heard }

bench-speech-description = à quelle vitesse un modèle de synthèse enregistre une phrase, et à quel point un modèle de transcription la réentend clairement
bench-speech-no-header = le jeu doit commencer par {"{"}"dataset": "speech", "version": <nombre>{"}"}
bench-speech-bad-case = cas { $case } : il lui faut un "text"
bench-speech-wer = taux d'erreur du juge sur les enregistrements
bench-speech-failed = phrases non enregistrées
bench-speech-unheard = enregistrements que le juge n'a pas pu entendre
bench-speech-latency-p50 = latence d'une phrase, médiane
bench-speech-latency-p95 = latence d'une phrase, 95e centile
bench-speech-cold-start = démarrage à froid (chargement du modèle)
bench-speech-misheard = phrases mal réentendues par le juge
bench-speech-heard = dit : { $said } · entendu : { $heard }
