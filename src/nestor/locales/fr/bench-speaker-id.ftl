# La suite de banc speaker-id : un modèle de voix distingue-t-il les voix du foyer, et à quel coût.

bench-speaker-id-description = à quel point un modèle de voix distingue les voix (les fausses acceptations d'abord), ce qu'apporte l'apprentissage, et ce qu'il coûte sur cette machine
bench-speaker-id-no-header = le jeu de données doit commencer par {"{"}"dataset": "speaker-id", "version": <nombre>, "audio": <dossier>{"}"}, et éventuellement "enroll", "spare" et "impostors"
bench-speaker-id-no-audio = { $path } doit contenir un dossier de fichiers WAV par personne, pour au moins deux personnes
bench-speaker-id-unknown = imposteurs sans enregistrements : { $speakers }
bench-speaker-id-too-few = { $speaker } doit avoir au moins { $needed } enregistrements
bench-speaker-id-bad-audio = { $path } n'est pas un fichier WAV 16 bits

bench-speaker-id-eer = EER (taux d'égale erreur)
bench-speaker-id-threshold = seuil utilisé
bench-speaker-id-far = fausses acceptations au seuil (paires de voix)
bench-speaker-id-frr = faux rejets au seuil
bench-speaker-id-threshold-at-far-1 = seuil pour 1 % de fausses acceptations
bench-speaker-id-frr-at-far-1 = faux rejets à ce seuil
bench-speaker-id-top1 = ensemble fermé : la voix la plus proche est la bonne
bench-speaker-id-unrecognised = tours d'une voix enregistrée restés inconnus
bench-speaker-id-misheard = tours attribués à quelqu'un d'autre
bench-speaker-id-impostors-unknown = tours d'une voix inconnue restés inconnus
bench-speaker-id-failed = tours sans empreinte
bench-speaker-id-replay-off-far-first = rejeu sans apprentissage : pris pour quelqu'un d'autre, premier tiers
bench-speaker-id-replay-off-far-last = rejeu sans apprentissage : pris pour quelqu'un d'autre, dernier tiers
bench-speaker-id-replay-off-frr-first = rejeu sans apprentissage : non reconnu, premier tiers
bench-speaker-id-replay-off-frr-last = rejeu sans apprentissage : non reconnu, dernier tiers
bench-speaker-id-replay-on-far-first = rejeu avec apprentissage : pris pour quelqu'un d'autre, premier tiers
bench-speaker-id-replay-on-far-last = rejeu avec apprentissage : pris pour quelqu'un d'autre, dernier tiers
bench-speaker-id-replay-on-frr-first = rejeu avec apprentissage : non reconnu, premier tiers
bench-speaker-id-replay-on-frr-last = rejeu avec apprentissage : non reconnu, dernier tiers
bench-speaker-id-learned = tours appris pendant le rejeu
bench-speaker-id-retakes = phrases d'enregistrement redites
bench-speaker-id-failed-enrollments = enregistrements échoués
bench-speaker-id-cold-start = cold start (chargement et première empreinte)
bench-speaker-id-latency-p50 = latence d'une empreinte, médiane
bench-speaker-id-latency-p95 = latence d'une empreinte, 95e centile
bench-speaker-id-rtf-p50 = RTF, médiane (latence par seconde de parole)
bench-speaker-id-model-size = modèle sur disque
bench-speaker-id-memory = mémoire ajoutée au chargement

bench-speaker-id-taken-list = Voix prises pour quelqu'un d'autre
bench-speaker-id-taken = { $who } pris pour { $whom } : { $times ->
    [one] une fois
   *[other] { $times } fois
} (score jusqu'à { $score })
