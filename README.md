# VibeAlarmSys Bridge
Home Assistant Custom Integration

---

## ➕ Add to Home Assistant

### 1️⃣ Add to HACS
[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](
https://my.home-assistant.io/redirect/hacs_repository/?owner=sccmlive&repository=VibeAlarmSys&category=integration
)

### 2️⃣ Start setup
[![Start setup](https://my.home-assistant.io/badges/config_flow_start.svg)](
https://my.home-assistant.io/redirect/config_flow_start/?domain=vibe_alarm_sys
)

> **Hinweis / Note:**  
> Nach der Installation über HACS ist **ein Neustart von Home Assistant erforderlich**, bevor das Setup gestartet werden kann.

---

## 🇩🇪 Deutsch

### Beschreibung
**VibeAlarmSys Bridge** verbindet ein vorhandenes Alarm-System in Home Assistant  
(`alarm_control_panel`, z. B. Alarmo oder andere Integrationen) mit einem  
ESPHome-basierten Vibrationsalarm.

Der aktuelle Alarmstatus wird automatisch an das ESPHome-Gerät übertragen.

---

### Funktionen
- Unterstützung beliebiger Alarm-Integrationen (`alarm_control_panel`)
- Auswahl eines ESPHome-Geräts über die Home-Assistant-Oberfläche
- Übertragung von:
  - Alarmstatus (`armed_*`, `disarmed`, `triggered`)
  - optional: Alarm-Auslöser-Text
  - optional: Name des Alarm-Panels
- Einrichtung vollständig über die Home-Assistant-UI

---

### Installation über HACS (empfohlen)

#### HACS installieren (falls noch nicht vorhanden)
Wenn **HACS** noch nicht installiert ist, folge bitte der offiziellen Anleitung:  
👉 https://hacs.xyz/docs/setup/prerequisites

Kurzfassung:
1. Terminal / SSH in Home Assistant öffnen
2. Installationsskript ausführen
3. Home Assistant neu starten
4. HACS unter **Einstellungen → Geräte & Dienste** hinzufügen

---

### Einrichtung der Integration (nach HACS-Installation)

Nach dem Neustart von Home Assistant:

1. **Einstellungen → Geräte & Dienste**
2. **Integration hinzufügen**
3. **VibeAlarmSys Bridge** auswählen  
   oder direkt über den Button oben starten

Im Einrichtungsdialog:
4. Alarm-System auswählen (`alarm_control_panel.*`)
5. ESPHome-Vibrationsalarm-Gerät auswählen
6. Optionale Einstellungen nach Bedarf aktivieren
7. **Speichern**

Die Integration ist nun aktiv.

---

### Test
- Alarm scharf / unscharf schalten
- Testalarm auslösen
- Prüfen, ob das ESPHome-Gerät reagiert  
  (z. B. Vibration, Anzeige, Status)

---

### Hinweis zum Feld „Node Name“
Das Feld **Node Name** ist ein optionales Fallback.

- In den meisten Fällen kann es **leer bleiben**
- Es wird nur benötigt, wenn das ESPHome-Gerät nicht automatisch erkannt wird
- Der Wert entspricht dem ESPHome-`name:` (mit Unterstrichen)

---

## 🇬🇧 English

### Description
**VibeAlarmSys Bridge** connects an existing Home Assistant alarm system  
(`alarm_control_panel`, e.g. Alarmo or other integrations) to an  
ESPHome-based vibration alarm device.

The current alarm state is automatically sent to the ESPHome device.

---

### Features
- Supports any alarm integration using `alarm_control_panel`
- Select an ESPHome device via the Home Assistant UI
- Sends:
  - Alarm state (`armed_*`, `disarmed`, `triggered`)
  - optional: alarm source text
  - optional: alarm panel name
- Configuration via the Home Assistant user interface

---

### Installation via HACS (recommended)

#### Install HACS (if not already installed)
If **HACS** is not installed yet, follow the official guide:  
👉 https://hacs.xyz/docs/setup/prerequisites

---

### Integration setup (after HACS installation)

After restarting Home Assistant:

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Select **VibeAlarmSys Bridge**  
   or start the setup directly using the button above

In the setup dialog:
4. Select the alarm system (`alarm_control_panel.*`)
5. Select the ESPHome vibration alarm device
6. Enable optional settings if required
7. **Save**

The integration is now active.

---

### Testing
- Arm / disarm the alarm system
- Trigger a test alarm
- Verify that the ESPHome device reacts  
  (e.g. vibration, display update)

---

### Note about the “Node Name” field
The **Node Name** field is an optional fallback.

- In most cases it can be left empty
- It is only required if the ESPHome device cannot be detected automatically
- The value corresponds to the ESPHome `name:` (using underscores)

---

## ⚙️ ESPHome Requirements

The ESPHome device must provide the following API action:

```yaml
set_alarm_state(alarm_state: string)

This software is provided “as is”. It is not a certified alarm system and must not be relied upon for life or property safety.

```
