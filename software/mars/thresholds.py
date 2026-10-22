"""Channel breakpoints that turn a raw reading into a 0-100 sub-score.

Each channel is a list of (value, score) points; scores are interpolated
linearly between points and clamped at both ends. Whether a rising or a falling
reading is dangerous follows from the points themselves (O2 scores rise as the
value falls).

STATUS column
  reference   - value taken from a published exposure/alarm limit (see source)
  indicative  - engineering placeholder, MUST be calibrated on site

None of these values has been cross-checked against the Coal Mines Regulations,
2017 / DGMS circulars yet. That check is a roadmap item (docs/roadmap.md).
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Channel:
    key: str
    label: str
    unit: str
    points: tuple
    source: str
    status: str

    def score(self, value: float) -> float:
        xs = np.array([p[0] for p in self.points], dtype=float)
        ys = np.array([p[1] for p in self.points], dtype=float)
        order = np.argsort(xs)
        return float(np.interp(value, xs[order], ys[order]))

    @property
    def bad_when(self) -> str:
        """'high' if the score grows with the value, otherwise 'low'."""
        pts = sorted(self.points)
        return "high" if pts[-1][1] > pts[0][1] else "low"

    def value_at_score(self, target: float):
        """Smallest-effort value at which the sub-score reaches `target`."""
        pts = sorted(self.points)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            lo, hi = sorted((y0, y1))
            if lo <= target <= hi and y1 != y0:
                return x0 + (target - y0) * (x1 - x0) / (y1 - y0)
        return None


ZONE_CHANNELS = {
    "ch4_lel": Channel(
        "ch4_lel", "Methane", "%LEL",
        ((0, 0), (5, 40), (20, 80), (50, 100)),
        "5 %LEL = raise ventilation, 20 %LEL = withdraw + power off (USACE EM 385-1-1 excerpt)", "reference"),
    "co_ppm": Channel(
        "co_ppm", "Carbon monoxide", "ppm",
        ((0, 0), (10, 10), (25, 35), (35, 45), (200, 80), (1200, 100)),
        "25 ppm ACGIH TWA, 35 ppm OSHA 1989 PEL, 200 ppm ceiling, 1200 ppm NIOSH IDLH", "reference"),
    "h2s_ppm": Channel(
        "h2s_ppm", "Hydrogen sulfide", "ppm",
        ((0, 0), (1, 10), (10, 50), (50, 80), (100, 100)),
        "10 ppm alarm (EM 385-1-1), 100 ppm NIOSH IDLH", "reference"),
    "o2_pct": Channel(
        "o2_pct", "Oxygen", "%vol",
        ((20.9, 0), (19.5, 50), (18.0, 75), (16.0, 90), (12.0, 100)),
        "19.5 % minimum (OSHA 29 CFR 1910.146 oxygen-deficient definition)", "reference"),
    "co2_ppm": Channel(
        "co2_ppm", "Carbon dioxide", "ppm",
        ((400, 0), (5000, 40), (30000, 80), (40000, 100)),
        "5000 ppm TWA, 30000 ppm STEL, 40000 ppm IDLH", "reference"),
    "temp_c": Channel(
        "temp_c", "Air temperature", "degC",
        ((30, 0), (35, 30), (40, 60), (45, 100)),
        "Heat-stress placeholder; production design should use wet-bulb / WBGT", "indicative"),
    "pm25": Channel(
        "pm25", "Particulate / smoke", "ug/m3",
        ((25, 0), (150, 40), (500, 80), (1000, 100)),
        "Smoke indicator placeholder; calibrate against site dust baseline", "indicative"),
    "vib_mm_s": Channel(
        "vib_mm_s", "Vibration (RMS)", "mm/s",
        ((1, 0), (5, 40), (15, 80), (30, 100)),
        "Ground/structure anomaly placeholder; calibrate per site", "indicative"),
}

WORKER_CHANNELS = {
    "spo2": Channel(
        "spo2", "Blood oxygen", "%",
        ((96, 0), (94, 25), (90, 60), (85, 100)),
        "SpO2 < 90 % is clinically hypoxaemic; < 94 % worth attention", "reference"),
    "hr_frac": Channel(
        "hr_frac", "Heart rate / (220 - age)", "fraction",
        ((0.70, 0), (0.85, 40), (0.95, 70), (1.05, 100)),
        "Age-predicted maximum heart-rate fraction (Fox formula)", "reference"),
    "hr_low": Channel(
        "hr_low", "Low heart rate", "bpm",
        ((50, 0), (40, 60), (30, 100)),
        "Bradycardia placeholder", "indicative"),
    "core_temp": Channel(
        "core_temp", "Estimated body temperature", "degC",
        ((37.5, 0), (38.0, 35), (39.0, 70), (40.0, 100)),
        "Heat-illness bands; wearable skin-to-core estimate needs bench calibration", "indicative"),
    "inactivity_s": Channel(
        "inactivity_s", "No-motion time", "s",
        ((0, 0), (30, 50), (60, 80), (120, 100)),
        "Man-down timers; tune with real activity data", "indicative"),
}

FALL_SCORE = 70.0
SOS_SCORE = 100.0

CATEGORIES = ((25.0, "Low"), (50.0, "Moderate"), (75.0, "High"), (100.0, "Critical"))
