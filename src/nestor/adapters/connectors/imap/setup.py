"""The guide the admin shows before connecting a mailbox over IMAP (French: the admin's language)."""

SETUP = """\
Nestor lit votre boîte en IMAP, en lecture seule : il ne déplace, ne supprime ni ne marque aucun mail.

Utilisez un mot de passe d'application plutôt que votre mot de passe habituel : il ne sert qu'à Nestor
et se révoque à tout moment sans toucher au reste. La plupart des fournisseurs l'exigent dès que la
validation en deux étapes est activée.

- Gmail : activez la validation en deux étapes, puis créez un mot de passe d'application sur
  https://myaccount.google.com/apppasswords. Serveur imap.gmail.com, port 993. (Le connecteur
  « Google » est plus simple et plus sûr pour Gmail.)
- iCloud : https://account.apple.com, « Connexion et sécurité », « Mots de passe pour app ».
  Serveur imap.mail.me.com, port 993 ; l'identifiant est votre adresse iCloud.
- Outlook / Hotmail : depuis septembre 2024, Microsoft n'accepte plus de mot de passe en IMAP pour
  les comptes personnels (connexion OAuth obligatoire) : ce connecteur ne peut pas s'y connecter.
- Free : serveur imap.free.fr, port 993, votre adresse et le mot de passe de votre boîte Free.
- Orange : serveur imap.orange.fr, port 993, votre adresse et votre mot de passe de messagerie.

Renseignez ensuite le serveur, le port (993 : connexion chiffrée), l'identifiant (souvent votre
adresse complète), le mot de passe et le dossier à surveiller (INBOX pour la boîte de réception).
Le port 143 sans chiffrement n'est pas accepté, sauf pour un serveur local (un pont comme Proton Bridge).
"""
