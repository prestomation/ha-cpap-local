# IDEAS.md — ha-cpap-local Future Features

## UI
- **Dashboard card** — A dedicated Lovelace card (like Pawsistant card) showing nightly summary: AHI gauge, usage bar, leak trend, pressure graph. Would need a separate HACS frontend repo.
- **History graph** — Lovelace graph card config template showing 30-day AHI trend.

## Automations
- **Weekly summary notification blueprint** — Automation blueprint that sends a weekly summary (avg AHI, compliance %, best/worst nights) via any notify service.
- **Reminder automation** — Notify if CPAP wasn't used by a configured bedtime hour.
- **Low leak coaching** — Notify if mask leak 95th has trended up over the last 7 days.

## Device Support
- **AirMini Bluetooth support** — Once `pycpap` implements `AirMiniFetcher`, add a "Bluetooth" fetch method to the config flow with a pairing step for the 4-digit PIN. See [pycpap docs/airmini-protocol.md](https://github.com/prestomation/pycpap/blob/main/docs/airmini-protocol.md) for protocol research.
- **AirSense 11 native features** — AirSense 11 has Bluetooth for direct data sync; explore if pycpap can leverage this.
- **Philips DreamStation support** — Once pycpap supports Respironics, expose the same sensor set.
- **F&P Icon support** — Same pattern if pycpap adds support.

## Sensors & Analytics
- **Historical trend sensors** — 7-day and 30-day rolling average AHI, usage hours, leak. Useful for dashboards and long-term tracking.
- **Compliance streak sensor** — Number of consecutive compliant nights. Useful for insurance requirements.
- **Best/worst week sensor** — Week number with lowest avg AHI.

## Integration
- **MyAir sync comparison** — Optional: pull from ResMed's cloud (MyAir) to cross-check local data.
- **Energy tracking** — If device power consumption is known, estimate nightly energy use.
- **Export to InfluxDB / Grafana** — Blueprint or guide for piping sensor history to Grafana for long-term visualization.
