# Le connecteur Google (Gmail) : son nom, sa description et le guide affiché avant de le connecter.

connector-google-title = Google (Gmail)
connector-google-description = Recherche et lecture des mails Gmail, en lecture seule. Les nouveaux mails alimentent les veilles.
connector-google-setup =
    Nestor se connecte à Google avec votre propre client OAuth. Comptez une dizaine de minutes, une
    seule fois par foyer.

    1. Ouvrez la console Google Cloud (https://console.cloud.google.com/), choisissez « Sélectionner un
       projet » puis « Nouveau projet », donnez-lui un nom (par exemple « Nestor ») et créez-le. Vérifiez
       qu'il est bien sélectionné en haut de la page.
    2. Activez l'API Gmail : https://console.cloud.google.com/apis/library/gmail.googleapis.com puis
       « Activer ».
    3. Configurez l'écran de consentement dans Google Auth Platform
       (https://console.cloud.google.com/auth/branding, « Commencer » s'il n'existe pas encore) :
       - Informations sur l'application : un nom (« Nestor ») et votre adresse comme e-mail d'assistance ;
       - Audience : « Externe » ;
       - Coordonnées : votre adresse ; acceptez le règlement sur les données, puis « Créer ».
    4. Dans « Accès aux données », ajoutez les champs d'application openid, email et
       https://www.googleapis.com/auth/gmail.readonly (lecture seule : Nestor ne peut ni envoyer, ni
       supprimer, ni modifier vos mails).
    5. Dans « Audience », cliquez sur « Publier l'application » pour la passer « En production ». Sinon,
       Google fait expirer l'autorisation au bout de 7 jours. Inutile de demander la validation de
       Google : l'application ne sert qu'à vous.
    6. Dans « Clients », choisissez « Créer un client », type « Application Web ». Sous « URI de
       redirection autorisés », collez exactement l'adresse de retour affichée par Nestor ci-dessous.
       Créez, puis copiez l'ID client et le code secret (le secret n'est plus affiché ensuite).
    7. Collez l'ID client et le code secret dans Nestor, puis cliquez sur « Connecter ». Google affiche
       « Google n'a pas validé cette application » : c'est votre propre application, choisissez
       « Paramètres avancés » puis « Accéder à Nestor (non sécurisé) », et autorisez l'accès.

    Un nouveau client peut mettre quelques minutes (rarement quelques heures) à fonctionner. Pour couper
    l'accès : déconnectez le compte dans Nestor, ou retirez-le sur https://myaccount.google.com/permissions.
