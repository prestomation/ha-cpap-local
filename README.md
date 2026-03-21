# CPAP Local — Home Assistant Integration

A Home Assistant custom integration that fetches ResMed CPAP therapy data and exposes it as sensors. HACS-compatible.

This integration is a thin wrapper around [pycpap](https://github.com/prestomation/pycpap) — a standalone Python library that handles all device communication and data parsing. If you want to use CPAP data outside of Home Assistant (scripts, dashboards, data analysis), use pycpap directly.

## Supported Devices

### SD Card devices (AirSense 10, AirSense 11, S9)
Data is fetched from the SD card via a WiFi adapter or direct mount. The CPAP machine must have an SD card inserted.

### AirMini (Bluetooth — planned)
The AirMini stores **365 days** of therapy data on-device, accessible over Bluetooth Classic SPP. No SD card or WiFi adapter required. You can pull a whole trip's data retroactively when you get home — no mobile app needed. See [pycpap/docs/airmini-protocol.md](https://github.com/prestomation/pycpap/blob/main/docs/airmini-protocol.md) for protocol details.

---

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations → Custom Repositories**
3. Add `https://github.com/prestomation/ha-cpap-local` as an **Integration**
4. Search for "CPAP Local" and install
5. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **CPAP Local**
3. Follow the config flow:

### Step 1: Choose Connection Method

| Method | When to use |
|---|---|
| **HTTP (WiFi SD Card)** | EZ Share or similar WiFi adapter on your network |
| **Local Path** | SD card mounted directly on the HA host |

### Step 2a: HTTP Setup
- **Adapter URL** — default `http://192.168.4.1` (EZ Share default). Change if using a bridge or different adapter.
- **Daily Sync Hour** — time to fetch data each day (default 10 = 10:00 AM local time)

> The integration does not manage your WiFi or network routing. The URL just needs to be reachable at sync time. Common approaches: direct connection to the EZ Share AP, OpenWRT routing, or a Raspberry Pi bridge.

### Step 2b: Local Path Setup
- **SD Card Path** — path to the SD card mount point (e.g. `/media/resmed_sd`)
- **Daily Sync Hour** — same as above

### Options (editable after setup)
- **AHI Threshold** — triggers `binary_sensor.cpap_ahi_elevated` (default 10 events/hr)
- **Minimum Usage Hours** — defines compliance (default 4h, per insurance standard)
- **Raw DATALOG Sync** — optionally archive high-res DATALOG files to a local path for use with OSCAR or SleepHQ

---

## Entities

### Sensors

| Entity | Unit | Description |
|---|---|---|
| `sensor.cpap_ahi` | events/h | Apnea-Hypopnea Index |
| `sensor.cpap_usage_hours` | h | Nightly usage duration |
| `sensor.cpap_mask_leak` | L/min | Median mask leak |
| `sensor.cpap_mask_leak_95` | L/min | 95th percentile mask leak |
| `sensor.cpap_pressure_median` | cmH₂O | Median therapy pressure |
| `sensor.cpap_pressure_95` | cmH₂O | 95th percentile pressure |
| `sensor.cpap_session_start` | timestamp | Mask-on time |
| `sensor.cpap_session_end` | timestamp | Mask-off time |
| `sensor.cpap_mode` | — | Therapy mode (CPAP, APAP, AutoSet, etc.) |
| `sensor.cpap_last_sync` | timestamp | Last time new data was fetched |

### Binary Sensors

| Entity | Description |
|---|---|
| `binary_sensor.cpap_used_last_night` | True if usage ≥ 1 hour |
| `binary_sensor.cpap_ahi_elevated` | True if AHI exceeded configured threshold |
| `binary_sensor.cpap_compliant` | True if usage ≥ configured minimum hours |

---

## Services

### `cpap_local.sync_now`
Immediately fetch the latest data, bypassing the scheduled sync time. Optionally target a specific device if you have multiple config entries.

```yaml
service: cpap_local.sync_now
# data:
#   entry_id: "abc123..."  # optional, syncs all if omitted
```

---

## Automation Examples

```yaml
# Morning notification with last night's stats
automation:
  - alias: "CPAP Morning Summary"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Last Night's CPAP"
          message: >
            AHI: {{ states('sensor.cpap_ahi') }} · 
            {{ (states('sensor.cpap_usage_hours') | float) | round(1) }}h · 
            Leak: {{ states('sensor.cpap_mask_leak_95') }} L/min

# Alert if AHI was high
automation:
  - alias: "CPAP AHI Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cpap_ahi
        above: 10
    action:
      - service: notify.mobile_app_phone
        data:
          title: "High AHI Last Night"
          message: "AHI was {{ states('sensor.cpap_ahi') }} events/hour. Check mask fit."
```

---

## Requirements

- Home Assistant 2023.3+
- [pycpap](https://github.com/prestomation/pycpap) (installed automatically)
- ResMed AirSense 10, AirSense 11, or S9 — with SD card inserted and a WiFi adapter or USB card reader

## License

MIT
