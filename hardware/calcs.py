"""Hand calculations behind the Stage 2 target specs (no FEA yet).

    python hardware/calcs.py
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "software"))
from mars.zones import SUB_ZONES, patrol_route, route_length  # noqa: E402

PETG_PRINTED_YIELD_MPA = 35.0     # conservative for FDM PETG loaded in-plane
STRAP_SNAG_N = 100.0              # assumed worst-case strap pull (snag on equipment)


def strap_bar_stress(bar_mm, height_mm, span_mm=26.0, load_n=STRAP_SNAG_N):
    """Outer bar of the strap lug as a simply supported beam with a uniform load."""
    moment = load_n * span_mm / 8.0
    section_modulus = height_mm * bar_mm ** 2 / 6.0
    return moment / section_modulus


def wearable_battery_hours(capacity_mah=700, usable=0.85):
    # Datasheet-typical currents (mA) x duty cycle. TO BE MEASURED on the bench.
    loads = {
        "ESP32-S3 (sampling, light-sleep between)": (22.0, 1.0),
        "SX1262 TX +14 dBm, 57 ms per 10 s": (45.0, 0.057 / 10),
        "SX1262 RX window after TX (ACK), 200 ms per 10 s": (5.0, 0.2 / 10),
        "MAX30102 (LEDs pulsed)": (1.5, 1.0),
        "AD8232 ECG front end": (0.17, 1.0),
        "MPU-6050 accel + gyro": (3.9, 1.0),
        "MAX30205 temperature": (0.6, 1.0),
        "Regulator + indicator LED + losses": (2.0, 1.0),
    }
    avg = sum(i * d for i, d in loads.values())
    return avg, capacity_mah * usable / avg, loads


def lora_airtime_ms(payload=20, sf=7, bw=125e3, cr=1, preamble=8):
    ts = 2 ** sf / bw
    n = 8 + max(math.ceil((8 * payload - 4 * sf + 28 + 16) / (4 * sf)) * (cr + 4), 0)
    return (preamble + 4.25 + n) * ts * 1000


def patrol_cycle_min(speed_m_s=1.5, dwell_s=60, rovers=1):
    length = route_length(patrol_route())
    return (length / speed_m_s + dwell_s * len(SUB_ZONES)) / 60 / rovers, length


if __name__ == "__main__":
    for bar, h in ((1.75, 5.0), (4.5, 6.0)):
        s = strap_bar_stress(bar, h)
        print(f"strap bar {bar} x {h} mm: {s:6.1f} MPa, FoS {PETG_PRINTED_YIELD_MPA / s:4.2f}")
    avg, hours, _ = wearable_battery_hours()
    print(f"wearable average current {avg:.1f} mA -> {hours:.1f} h on 700 mAh")
    print(f"LoRa airtime 20 B @ SF7/125 kHz: {lora_airtime_ms():.1f} ms")
    for v in (1.0, 1.5):
        cyc, L = patrol_cycle_min(v)
        print(f"patrol route {L:.0f} m at {v} m/s with 60 s dwell: {cyc:.1f} min per cycle")
