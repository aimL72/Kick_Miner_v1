<p align="center">
  <img src="assets/logo.png" alt="Kick Channel Points Miner" width="320">
</p>

<p align="center">
  <a href="https://github.com/aimL72/Kick_Miner_v1/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/aimL72/Kick_Miner_v1?style=flat&color=black&logo=unlicense&logoColor=white"></a>
  <a href="https://github.com/aimL72/Kick_Miner_v1/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/aimL72/Kick_Miner_v1?style=flat&color=32CD32&logo=github&logoColor=white"></a>
  <a href="https://github.com/aimL72/Kick_Miner_v1/pkgs/container/kick_miner_v1"><img alt="GHCR image" src="https://img.shields.io/badge/ghcr.io-kick__miner__v1-2496ED?style=flat&logo=docker&logoColor=white"></a>
  <a href="README.md"><img alt="English version" src="https://img.shields.io/badge/lang-%F0%9F%87%AC%F0%9F%87%A7%20English-white?style=flat"></a>
</p>

<h1 align="center">https://github.com/aimL72/Kick_Miner_v1</h1>

**Credits**
- Konzept / Funktionsumfang: [zarmstrong/Twitch-Channel-Points-Miner-v3](https://github.com/zarmstrong/Twitch-Channel-Points-Miner-v3) (GPL-3.0) – nur als konzeptionelle Vorlage genutzt, kein Quellcode übernommen
- Ursprüngliche Twitch-Idee: [gottagofaster236/Twitch-Channel-Points-Miner](https://github.com/gottagofaster236/Twitch-Channel-Points-Miner) und [Tkd-Alex/Twitch-Channel-Points-Miner-v2](https://github.com/Tkd-Alex/Twitch-Channel-Points-Miner-v2)
- Kick-Plattform-Basis: [Baillora/Kick_Channel_Points_Miner](https://github.com/Baillora/Kick_Channel_Points_Miner) (MIT) – Kick-API-Endpunkte, Cloudflare-Bypass-Ansatz, Viewer-WebSocket-Protokoll

> Ein einfacher Bot, der für dich Kick-Streams schaut und die Channel-Points farmt.

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
* **Telegram-Bot** – `/status` `/balance` `/accounts` `/restart` `/language`,
  nur für die eine konfigurierte `chat_id`.
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
| `Telegram.enabled` / `.bot_token` / `.chat_id` | Steuer-Bot - `chat_id` ist der einzige berechtigte Nutzer |
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

Alles Veränderliche (`config.json`, `logs/`, `data/`) liegt in **einem**
eingebundenen Verzeichnis (`/data` im Container, `KICK_MINER_DATA`).

```bash
mkdir -p data
docker compose up -d          # zieht ghcr.io/aiml72/kick_miner_v1:latest
```

Beim ersten Start wird eine Vorlage `data/config.json` angelegt – ausfüllen
(Tokens, Streamer) und `docker compose restart`.

Statt zu ziehen aus diesem Checkout bauen: in `docker-compose.yml` `image:`
auskommentieren, `build:` einkommentieren, dann `docker compose up -d --build`.

### ZimaOS / CasaOS

1. Im App-Store **Eigene App installieren** → **Importieren**, den Inhalt von
   [`docker-compose.yml`](docker-compose.yml) einfügen.
2. Die Volume-Zeile `./data:/data` auf einen echten NAS-Pfad ändern, z. B.
   `/DATA/AppData/kick-miner:/data`.
3. Einmal starten, dann im ZimaOS-Dateimanager
   `/DATA/AppData/kick-miner/config.json` bearbeiten (Tokens + Streamer) und die
   App neu starten.
4. Dashboard: `http://<nas-ip>:5000`.

Das Image ist Multi-Arch (amd64 + arm64) und wird von GitHub Actions bei jedem
Push auf `main` neu gebaut.

## Telegram einrichten

1. Mit [@BotFather](https://t.me/BotFather) schreiben, `/newbot`, Token nach
   `Telegram.bot_token` kopieren.
2. [@userinfobot](https://t.me/userinfobot) anschreiben, um die eigene
   numerische User-ID zu bekommen, diese in `Telegram.chat_id` eintragen
   (damit bist du der Owner).

## Entwicklung

```bash
pip install -r requirements-dev.txt
pytest
```

## Änderungsverlauf

Der vollständige Verlauf aller Änderungen steht in [CHANGELOG.md](CHANGELOG.md)
(auf Englisch).

## Danksagungen

Siehe den **Credits**-Block ganz oben in dieser Datei.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
