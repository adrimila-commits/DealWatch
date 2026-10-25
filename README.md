# Angebots-Wächter

Sucht täglich Angebote (mind. 30 % Rabatt) zu deiner Liste und schickt **eine** Push-Nachricht aufs Handy (via ntfy).

## Einrichtung (ca. 10 Minuten)

1. **ntfy-App** installieren (iPhone/Android) und ein Topic abonnieren mit einem langen, nicht erratbaren Namen, z. B. `angebote-<zufälliger-text>`.
2. **GitHub-Konto** → neues privates Repository → alle Dateien dieses Ordners hochladen (inkl. `.github/workflows/daily.yml`).
3. Repository → Settings → Secrets and variables → Actions → **New secret**: Name `NTFY_TOPIC`, Wert = dein Topic.
4. Tab **Actions** → „Taegliche Angebote“ → **Run workflow** zum Testen. Danach läuft es täglich um ca. 07:00/08:00 Uhr.

Lokal testen: `pip install -r requirements.txt && python dealwatch.py --dry-run`
Push testen: `NTFY_TOPIC=dein-topic python dealwatch.py --test-push`

## Anpassen

Alles steht in `config.yaml`: Rabattschwelle, Suchbegriffe, Grössen, Shops, Lamm-Herkunft, Helm-Marken.

## Wichtig / Einschränkungen

- Es werden nur Shops aus `config.yaml` abgefragt: Schweizer Shops (Lieferung in die Schweiz, Preise in CHF) und deutsche Shops (Lieferung in Deutschland, Preise in €). So fällt kein Einfuhrzoll an. Keine Importe aus Drittländern, keine Marktplatz-Händler aus China. Bei Galaxus und MediaMarkt können Marktplatz-Händler dabei sein, bitte im Link den Verkäufer prüfen.
- Die Parser lesen Produktdaten (schema.org) bzw. Preis-Kacheln. **Die Suchadressen und die Erkennung wurden noch nicht live geprüft.** Erster Lauf: Ausgabe im Actions-Log prüfen. Steht in der Push „Nicht erreichbar: …“, blockiert der Shop automatisierte Abfragen oder die URL stimmt nicht. Dann in `config.yaml` anpassen oder den Shop entfernen.
- Filial-Verfügbarkeit (Region Basel/Weil/Lörrach) wird nicht geprüft; bei Aktionis-Treffern (Migros/Coop/Denner) gelten die Angebote schweizweit, Details im Link prüfen.
- Lammfleisch wird nur aufgenommen, wenn im Titel die Herkunft Schweiz/Deutschland steht.
- Bitte AGB/robots.txt der Shops beachten; die Abfragen sind bewusst selten (1x täglich, mit Pause).
