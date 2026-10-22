"""0-100 risk scoring with an explainable, trend-based prediction term.

Zone score   = combine(sub-scores of every gas/environment channel), where a
               channel's sub-score is max(current, PREDICT_WEIGHT * projected),
               projected = score of the value expected HORIZON_S from now.
Worker score = combine(vitals sub-scores, fall, inactivity, SOS).

combine() is dominated by the worst channel, with a smaller contribution from
the next two so that several simultaneous moderate problems rank above one.
"""

from dataclasses import dataclass, field

import numpy as np

from .thresholds import CATEGORIES, FALL_SCORE, SOS_SCORE, WORKER_CHANNELS, ZONE_CHANNELS

HORIZON_S = 600          # predict 10 minutes ahead
TREND_WINDOW = 30        # samples used for the trend fit (5 min at 10 s)
MIN_T_STAT = 4.0         # slope must be this many standard errors from zero
PREDICT_WEIGHT = 0.8


def category(score: float) -> str:
    for upper, name in CATEGORIES:
        if score <= upper:
            return name
    return CATEGORIES[-1][1]


def combine(scores) -> float:
    s = sorted((float(x) for x in scores), reverse=True) + [0.0, 0.0, 0.0]
    return min(100.0, s[0] + 0.25 * s[1] + 0.10 * s[2])


@dataclass
class Trend:
    slope_per_s: float
    t_stat: float
    fitted_now: float

    def project(self, seconds: float) -> float:
        return self.fitted_now + self.slope_per_s * seconds


def fit_trend(values, dt: float):
    """Least-squares line through the last TREND_WINDOW samples (None if too short)."""
    y = np.asarray(values, dtype=float)[-TREND_WINDOW:]
    n = len(y)
    if n < TREND_WINDOW // 2:
        return None
    t = np.arange(n) * dt
    tm, ym = t.mean(), y.mean()
    sxx = ((t - tm) ** 2).sum()
    slope = ((t - tm) * (y - ym)).sum() / sxx
    resid = y - (ym + slope * (t - tm))
    dof = max(n - 2, 1)
    se = np.sqrt((resid ** 2).sum() / dof / sxx)
    t_stat = slope / se if se > 0 else (np.inf if slope else 0.0)
    return Trend(slope, float(t_stat), float(ym + slope * (t[-1] - tm)))


def time_to_value(trend: Trend, target: float, bad_when: str):
    """Seconds until the fitted trend reaches `target`, if it is heading there."""
    if trend is None or abs(trend.t_stat) < MIN_T_STAT or trend.slope_per_s == 0:
        return None
    rising = trend.slope_per_s > 0
    if (bad_when == "high") != rising:
        return None
    eta = (target - trend.fitted_now) / trend.slope_per_s
    return max(eta, 0.0)


def sensor_health(values, lo=None, hi=None) -> str:
    """'ok', 'stuck' (no variation over the window) or 'out_of_range'."""
    y = np.asarray(values, dtype=float)[-TREND_WINDOW:]
    if len(y) == 0:
        return "no_data"
    if (lo is not None and y[-1] < lo) or (hi is not None and y[-1] > hi):
        return "out_of_range"
    if len(y) >= 18 and np.ptp(y) == 0.0:
        return "stuck"
    return "ok"


@dataclass
class Driver:
    key: str
    label: str
    value: float
    unit: str
    current: float
    predicted: float = 0.0
    eta_danger_s: float = None

    @property
    def score(self) -> float:
        return max(self.current, PREDICT_WEIGHT * self.predicted)


@dataclass
class Assessment:
    score: float
    category: str
    drivers: list = field(default_factory=list)

    def top(self, n=3):
        return sorted(self.drivers, key=lambda d: d.score, reverse=True)[:n]


def assess_zone(history: dict, dt: float) -> Assessment:
    """history: channel key -> sequence of readings (latest last)."""
    drivers = []
    for key, ch in ZONE_CHANNELS.items():
        values = history.get(key)
        if values is None or len(values) == 0:
            continue
        current_value = float(values[-1])
        d = Driver(key, ch.label, current_value, ch.unit, ch.score(current_value))
        trend = fit_trend(values, dt)
        if trend is not None and abs(trend.t_stat) >= MIN_T_STAT:
            d.predicted = ch.score(trend.project(HORIZON_S))
            danger_value = ch.value_at_score(80.0)
            if danger_value is not None and d.current < 80.0:
                d.eta_danger_s = time_to_value(trend, danger_value, ch.bad_when)
        drivers.append(d)
    score = combine(d.score for d in drivers)
    return Assessment(round(score, 1), category(score), drivers)


def assess_worker(vitals: dict, age: int = 35) -> Assessment:
    """vitals keys: hr, spo2, core_temp, inactivity_s, fall (bool), sos (bool)."""
    drivers = []
    hr = vitals.get("hr")
    if hr:
        frac = hr / (220.0 - age)
        drivers.append(Driver("hr_frac", "Heart rate", hr, "bpm", WORKER_CHANNELS["hr_frac"].score(frac)))
        drivers.append(Driver("hr_low", "Low heart rate", hr, "bpm", WORKER_CHANNELS["hr_low"].score(hr)))
    for key in ("spo2", "core_temp", "inactivity_s"):
        if vitals.get(key) is not None:
            ch = WORKER_CHANNELS[key]
            drivers.append(Driver(key, ch.label, vitals[key], ch.unit, ch.score(vitals[key])))
    if vitals.get("fall"):
        drivers.append(Driver("fall", "Fall detected", 1, "", FALL_SCORE))
    if vitals.get("sos"):
        drivers.append(Driver("sos", "SOS pressed", 1, "", SOS_SCORE))
    score = combine(d.score for d in drivers)
    return Assessment(round(score, 1), category(score), drivers)
