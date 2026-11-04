## La voix d'une personne : son état sur sa page, puis l'enregistrement guidé, où { $assistant } parle à qui lit.

people-voice = voix
people-voice-none = Pas encore enregistrée.
people-voice-recorded = Enregistrée
people-voice-learned = { $count ->
    [0] Rien d'appris depuis.
    [one] 1 empreinte apprise depuis, la dernière
   *[other] { $count } empreintes apprises depuis, la dernière
}
people-voice-not-learning = N'apprend plus au fil du temps.
people-voice-off = La reconnaissance des voix est éteinte.
people-voice-off-link = Configuration › Voix
people-voice-record = { $own ->
    [yes] Enregistrer ma voix
   *[no] Enregistrer sa voix
}
people-voice-redo = Refaire l'enregistrement
people-voice-learning = Apprendre au fil du temps
people-voice-learning-on = { $assistant } apprend à nouveau au fil du temps.
people-voice-learning-off = { $assistant } n'apprend plus au fil du temps.
people-voice-forget-learned = Oublier ce qui a été appris
people-voice-forget-learned-title = Oublier ce qui a été appris ?
people-voice-forget-learned-body = { $count ->
    [one] L'empreinte apprise au fil des conversations est effacée.
   *[other] Les { $count } empreintes apprises au fil des conversations sont effacées.
} L'enregistrement reste.
people-voice-forget = { $own ->
    [yes] Oublier ma voix
   *[no] Oublier sa voix
}
people-voice-forget-title = { $own ->
    [yes] Oublier votre voix ?
   *[no] Oublier la voix de { $name } ?
}
people-voice-forget-body = L'enregistrement et tout ce qui a été appris sont effacés. { $assistant } ne reconnaîtra plus { $name } sur les satellites.
people-voice-forget-confirm = Oublier
people-voice-forgotten = Voix oubliée.
people-voice-learned-forgotten = Ce qui a été appris est oublié.

recording-description = Quatre étapes pour que { $assistant } reconnaisse une voix : accord, micro, cinq phrases, essai.
recording-figure = { $assistant }

## 1. Avant de commencer
recording-title = { $own ->
    [yes] Enregistrer ta voix
   *[no] Enregistrer la voix de { $name }
}
recording-keeps = { $own ->
    [yes] Je garde une empreinte de ta voix, jamais le son.
   *[no] Je garde une empreinte de la voix de { $name }, jamais le son.
}
recording-use = Elle me sert à savoir qui me parle sur les satellites, pour répondre avec les bons rappels, comptes et souvenirs.
recording-not-a-password = Ce n'est pas un mot de passe : pour une action sensible, je demande toujours une confirmation.
recording-other-agrees = C'est { $name } qui lit les phrases, et qui doit être d'accord.
recording-learning = Apprendre au fil du temps
recording-learning-hint = J'affine l'empreinte quand je suis sûr de qui parle, sans garder le son.
recording-erase = { $own ->
    [yes] Tout s'efface depuis ta page, avec « Oublier ma voix ».
   *[no] Tout s'efface depuis la page de { $name }, avec « Oublier sa voix ».
}
recording-start = Commencer

## 2. Le micro
recording-title-microphone = Dis bonjour
recording-microphone = Micro
recording-microphone-unnamed = Micro { $n }
recording-microphone-opening = J'ouvre le micro…
recording-microphone-say = Dis « Bonjour { $assistant } » pour essayer le micro.
recording-microphone-clear = Je t'entends bien.
recording-microphone-quiet = Je t'entends à peine. Rapproche-toi du micro, ou parle plus fort.
recording-microphone-noisy = Il y a trop de bruit autour de toi. Trouve un endroit plus calme.
recording-microphone-denied = Le navigateur refuse le micro. Autorise-le dans les réglages du site, puis réessaie.
recording-microphone-missing = Aucun micro trouvé. Branches-en un, puis réessaie.
recording-microphone-insecure = Le navigateur n'ouvre le micro que sur une adresse sécurisée : https, ou localhost.
recording-microphone-unsupported = Ce navigateur ne donne pas accès au micro.
recording-microphone-failed = Le micro n'a pas pu s'ouvrir.
recording-retry = Réessayer
recording-continue = Continuer

## 3. Cinq phrases
recording-title-phrase = Lis cette phrase
recording-phrase-count = Phrase { $n } sur { $total }
recording-phrase = « { $phrase } »
recording-ring = Phrases réussies
recording-listening = Je t'écoute. Pas de bouton : je sais quand tu as fini.
recording-checking = Je vérifie…
recording-kept = Parfait. La suivante.
recording-again = { $problem ->
    [too_short] C'était un peu court. Encore une fois ?
    [too_quiet] Je n'ai pas bien entendu. Encore une fois, un peu plus fort ?
    [too_loud] C'était trop fort, ou trop de bruit. Encore une fois ?
    [other_voice] Ce n'est pas la même voix que tout à l'heure. Encore une fois ?
   *[other] Je n'ai pas bien entendu, encore une fois ?
}
recording-finishing = Je retiens ta voix…

## 4. C'est prêt
recording-title-done = { $own ->
    [yes] Je reconnais ta voix
   *[no] Je reconnais la voix de { $name }
}
recording-try = Essayer
recording-try-hint = Dis quelque chose, et je te dis qui j'entends.
recording-try-listening = Dis quelque chose…
recording-heard = C'est { $name }.
recording-heard-nobody = Je ne reconnais pas cette voix.
recording-likeness = Ressemblance { $score } %, reconnue dès { $threshold } %.
recording-satellite = Tu peux aussi le refaire depuis un satellite, avec son vrai micro : dis « { $assistant }, apprends à reconnaître ma voix ».
recording-done = Terminer
