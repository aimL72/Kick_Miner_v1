# Kick Channel Points Miner

<p align="center"><em><a href="README.md">🇬🇧 English version</a></em></p>

Ein reiner Channel-Points-Farm-Bot für **Kick.com**. Er hält für die
konfigurierten Streamer eine Viewer-WebSocket offen, sodass beim „Zuschauen"
Punkte anfallen, speichert die Punktestände in SQLite, zeigt alles in einem
Web-Dashboard im Stil des Twitch-Miners (inklusive Streamer-Editor) und kann
Updates an Discord schicken sowie über Telegram gesteuert werden.

Angelehnt an den Funktionsumfang der Twitch-Channel-Points-Miner, aber
ausschließlich für Kick. Predictions, Watch-Streaks, Raids und Drops sind
**nicht** enthalten – Kick hat sie entweder nicht oder bietet keine nutzbare
Schnittstelle dafür.

> ⚠️ **Nutzung auf eigene Gefahr.** Automatisiertes Zuschauen verstößt gegen
> Kicks Nutzungsbedingungen und kann zu Sperren führen. Nur mit Accounts
> verwenden, deren Verlust du verschmerzen kannst. Nur zu Lernzwecken.

## Funktionen

* **Multi-Account** – jeder Account mit eigenem Token, Proxy, eigener
  Streamer-Liste und Limit.
* **Prioritäts-Watching** – Position in der Streamer-Liste = Priorität; geht ein
  höher priorisierter Streamer live, verdrängt er einen niedrigeren
  (max. `max_concurrent` gleichzeitig).
* **Cloudflare-Bypass** – eine geteilte `curl_cffi`-Session pro Account mit
  403-Neuinitialisierung + Retry.
* **SOCKS5-/HTTP-Proxy** – global oder pro Account.
* **Web-Dashboard** (`http://localhost:5000`) – Tabs Points / Config / Log,
  „Now watching"-Leiste, Punkte-Charts pro Streamer und ein **Streamer-Editor**
  (hinzufügen / entfernen / verschieben, Limit ändern); Speichern startet den
  Miner automatisch neu.
* **Punkteverlauf** in `data/analytics.sqlite3` (30 Tage Aufbewahrung).
* **Discord-Webhook** – exakt das Nachrichtenformat des Twitch-Miners.
* **Telegram-Bot** – `/status` `/balance` `/accounts` für alle erlaubten Nutzer,
  `/restart` `/language` nur für den Owner.
* **Auto-Neustart** bei Abstürzen, bei Telegram `/restart` und nach einer
  Konfig-Änderung im Dashboard. Sauberes Beenden mit `Strg+C`.
* **Selbsttest** – `python -m kickminer.selfcheck <kanal> --account "<alias>"`
  prüft den kompletten Lese-Pfad (Cloudflare, Kanal, Punkte, WS-Token).

## Voraussetzungen

* Python 3.10+
* Ein Kick-**Bearer-Token** pro Account (siehe unten)

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
cp config.example.json config.json
```

Dann `config.json` bearbeiten (steht in `.gitignore` – dein Token wird nie
committet).

## Kick-Token holen

1. Bei **kick.com** im Browser anmelden.
2. Entwicklertools öffnen (`F12`) → Tab **Netzwerk**.
3. Seite neu laden, eine beliebige Anfrage an `kick.com` anklicken.
4. Unter **Request Headers** die Zeile `authorization: Bearer <token>` suchen.
5. Den Teil nach `Bearer ` (Format `123456|xxxxxxxx…`) in `config.json` unter
   `Accounts[].token` eintragen.

Tokens laufen ab; wenn die Punkteabfrage plötzlich fehlschlägt, einen frischen
holen.

## Konfiguration

Schlüssel in `config.json` (vollständiges Beispiel: `config.example.json`):

| Schlüssel | Bedeutung |
| --- | --- |
| `Language` | `en` (Standard) oder `de` |
| `Debug` | ausführliches Konsolen-Log (die Logdatei ist immer DEBUG) |
| `WebDashboard.enabled` / `.port` | Web-Dashboard |
| `Discord.enabled` / `.webhook_url` / `.username` / `.avatar_url` | Webhook-Benachrichtigungen |
| `Discord.notify_points` / `notify_status_change` / `notify_errors` / `notify_startup` | einzelne Ereignis-Schalter |
| `Discord.min_points_gain` | Punkte-Zugänge kleiner als dieser Wert unterdrücken |
| `Telegram.enabled` / `.bot_token` / `.chat_id` / `.allowed_users` | Steuer-Bot (Owner = `chat_id`) |
| `Proxy.enabled` / `.url` | globaler Proxy (`socks5://`, `http://`) |
| `Accounts[]` | ein Eintrag pro Kick-Account |
| `Accounts[].alias` | Anzeigename (Dashboard, Telegram) |
| `Accounts[].token` | Kick-Bearer-Token |
| `Accounts[].proxy` | Proxy pro Account, oder `null` für den globalen |
| `Accounts[].streamers` | geordnete Liste – **Position = Priorität**, Index 0 = höchste |
| `Accounts[].max_concurrent` | wie viele Streamer gleichzeitig geschaut werden |
| `Check_interval` | Sekunden zwischen den Online-Checks |
| `Reconnect_cooldown` | wenn die WebSocket eines Streamers aufgibt: Wartezeit in Sekunden bis zum erneuten Versuch |
| `Connection_stagger_min/max` | Verzögerungsbereich zwischen Verbindungsaufbauten |

Das alte Einzel-Account-Format (`Private.token` / `Streamers` /
`Max_active_channels`) wird weiterhin akzeptiert und automatisch umgestellt.

## Starten

```bash
python main.py
```

Dann `http://localhost:5000` öffnen.

### Docker

```bash
docker compose up -d --build
```

`config.json` wird schreibgeschützt eingebunden; `logs/` und `data/` bleiben
erhalten.

## Telegram einrichten

1. Mit [@BotFather](https://t.me/BotFather) schreiben, `/newbot`, Token nach
   `Telegram.bot_token` kopieren.
2. [@userinfobot](https://t.me/userinfobot) anschreiben, um die eigene
   numerische User-ID zu bekommen, diese in `Telegram.chat_id` eintragen
   (damit bist du der Owner).
3. IDs von reinen Zuschauern in `Telegram.allowed_users` ergänzen.

## Entwicklung

```bash
pip install -r requirements-dev.txt
pytest
```

## Danksagungen

* [Baillora/Kick_Channel_Points_Miner](https://github.com/Baillora/Kick_Channel_Points_Miner)
  (MIT) – Kick-API-Endpunkte, Cloudflare-Bypass-Ansatz, Viewer-WebSocket-Protokoll.
* [zarmstrong/Twitch-Channel-Points-Miner-v3](https://github.com/zarmstrong/Twitch-Channel-Points-Miner-v3)
  (GPL-3.0) – konzeptionelle Vorlage für Architektur, Dashboard-Aufbau und das
  Discord-Nachrichtenformat. Es wurde kein Quellcode übernommen.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
