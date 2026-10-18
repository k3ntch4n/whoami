# Alertes Telegram : Earth Arcade (지구오락실) & An Yujin (IVE)

Un workflow GitHub Actions vérifie toutes les 15 minutes :

- **YouTube** (tvN, tvN D ENT, IVE officiel) : nouvelles vidéos dont le titre ou la description
  contient 지구오락실 / Earth Arcade / 안유진 / Yujin…
  - 🎬 nouvelle vidéo
  - ⏰ live ou première programmé (avec l'heure de Paris)
  - 🔴 message supplémentaire quand le live démarre
- **Google News** (coréen, anglais, français) : un récap des nouveaux articles par passage,
  avec 📅 devant ceux qui ressemblent à un événement (comeback, concert, fan meeting, nouvelle saison…).

Le premier lancement mémorise tout ce qui existe déjà sans rien t'envoyer (sauf un message de confirmation),
pour éviter d'être inondé.

## Mise en place (5 min)

1. **Créer le bot** : sur Telegram, écris à [@BotFather](https://t.me/BotFather), envoie `/newbot`,
   choisis un nom → il te donne un **token** (`123456:ABC...`).
2. **Récupérer ton chat id** : envoie n'importe quel message à ton nouveau bot, puis ouvre
   `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` dans le navigateur et note la valeur
   `"chat":{"id": ...}`.
3. **Ajouter les secrets** dans GitHub : *Settings → Secrets and variables → Actions → New repository secret*
   - `TELEGRAM_BOT_TOKEN` = le token
   - `TELEGRAM_CHAT_ID` = le chat id
4. **Fusionner cette branche dans la branche par défaut** : GitHub n'exécute les workflows
   planifiés que depuis la branche par défaut.
5. **Tester** : onglet *Actions → Alertes Earth Arcade / Yujin → Run workflow*, coche « Envoyer seulement
   un message de test ». Relance-le ensuite sans cocher pour initialiser.

## Personnaliser

Tout se règle dans [`config.json`](config.json) :

- `youtube_channels` : ajoute une chaîne avec son `@handle` (ou `channel_id: "UC..."`).
  `"filter": false` = toutes ses vidéos, `true` = seulement celles qui contiennent un mot-clé.
- `keywords` : mots-clés recherchés dans les vidéos. `유진` seul peut attraper d'autres Yujin ;
  retire-le si tu reçois trop de faux positifs.
- `news_feeds` : recherches Google News (`lang` : `ko`, `en` ou `fr`).
- `event_keywords` : mots qui font afficher 📅 devant un article.
- La fréquence se change dans `.github/workflows/kpop-alerts.yml` (`cron`).

## Bon à savoir

- Gratuit : aucune clé API YouTube n'est nécessaire (flux RSS publics).
- Les flux RSS YouTube ont parfois 5 à 15 min de retard, donc l'alerte arrive en général
  10 à 30 min après la mise en ligne.
- Sur un dépôt sans aucune activité pendant 60 jours, GitHub désactive les workflows planifiés
  (il envoie un e-mail avant) : il suffit de cliquer sur « Enable workflow » dans l'onglet Actions.
- Test en local sans rien envoyer : `DRY_RUN=1 python alerts/watch.py`.
