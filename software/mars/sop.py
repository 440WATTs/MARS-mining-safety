"""Recommended actions attached to alerts.

ILLUSTRATIVE ONLY. These are drafted from general mine-safety practice to show
how MARS links a hazard to guidance. Before any trial they must be replaced by
the mine's own approved SOPs; the competent official (Manager / Overman /
Sirdar) always makes the final call.
"""

SOP = {
    "ch4_lel": {
        "Moderate": ["Check main and auxiliary fan status; increase ventilation to the zone",
                     "Stop hot work and remove ignition sources in the zone",
                     "Re-test with a hand-held methanometer within 5 min"],
        "High": ["Withdraw all persons from the zone and its return side",
                 "Isolate electrical power to the zone",
                 "Inform Manager / Overman; rescue team on standby",
                 "No re-entry until a competent person clears the zone"],
    },
    "co_ppm": {
        "Moderate": ["Check for fire, spontaneous heating, diesel exhaust or recent blasting",
                     "Persons in the zone keep self-rescuers ready"],
        "High": ["Withdraw persons; don self-rescuers",
                 "Send rover for a thermal scan to locate the source",
                 "Inform Manager; rescue team on standby"],
    },
    "h2s_ppm": {
        "Moderate": ["Increase ventilation; check water/sump areas for H2S release"],
        "High": ["Withdraw persons immediately; re-entry only with breathing apparatus"],
    },
    "o2_pct": {
        "Moderate": ["Check ventilation; persons move to the fresh-air side"],
        "High": ["Withdraw immediately; re-entry only with breathing apparatus"],
    },
    "co2_ppm": {
        "Moderate": ["Increase ventilation; check for blackdamp in old workings"],
        "High": ["Withdraw persons; re-entry only after re-ventilation and testing"],
    },
    "temp_c": {
        "Moderate": ["Schedule rest and hydration breaks; check cooling and ventilation"],
        "High": ["Limit exposure time; rotate workers; inform supervisor"],
    },
    "pm25": {
        "Moderate": ["Check for smoke or fire; activate dust suppression"],
        "High": ["Treat as possible fire: withdraw persons, rover thermal scan, inform Manager"],
    },
    "vib_mm_s": {
        "Moderate": ["Pause work near the face; inspect roof and sides for loose strata"],
        "High": ["Withdraw persons from the face; rover visual inspection against last baseline"],
    },
    "worker_down": {
        "High": ["Call the worker on radio / wearable buzzer",
                 "Nearest rover switches to rescue-assist and heads to last known zone",
                 "Rescue and medical teams dispatched with SOS bundle"],
    },
    "spo2": {
        "Moderate": ["Check on the worker; move to the fresh-air side"],
        "High": ["Worker to leave the zone with a buddy; medical team informed; check zone O2/CO"],
    },
    "core_temp": {
        "Moderate": ["Rest in a cooler area; hydrate"],
        "High": ["Remove worker from the hot zone; first aid for heat illness; medical team informed"],
    },
    "hr_frac": {
        "Moderate": ["Check on the worker; enforce a rest break"],
        "High": ["Stop work; supervisor checks the worker in person"],
    },
}

ESCALATION = "Sound the evacuation alarm for the affected zones"


def actions(hazard_key: str, level: str):
    table = SOP.get(hazard_key, {})
    if level == "Critical":
        return [ESCALATION] + table.get("High", table.get("Moderate", []))
    if level == "High":
        return table.get("High", table.get("Moderate", []))
    return table.get("Moderate", [])
