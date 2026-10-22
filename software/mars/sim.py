"""Discrete-time simulation of the reference mine for end-to-end testing.

Truth model -> noisy sensor readings and encoded wearable frames -> lossy radio
(fixed gateway + optional rover relay) -> Engine -> alerts -> workers react
(evacuate) -> rover reacts (rescue-assist). Every number here is a modelling
ASSUMPTION chosen to exercise the software, not a measurement.
"""

import math

import numpy as np

from . import packet
from .engine import Engine
from .zones import FIXED_LINK_P, SUB_ZONES, ZONES, distance, downstream, patrol_route, shortest_path, zone_code

BASELINE = {"ch4_lel": 0.8, "co_ppm": 3.0, "h2s_ppm": 0.1, "o2_pct": 20.8,
            "co2_ppm": 900.0, "temp_c": 29.0, "pm25": 35.0, "vib_mm_s": 0.6}
NOISE = {"ch4_lel": 0.25, "co_ppm": 0.8, "h2s_ppm": 0.05, "o2_pct": 0.05,
         "co2_ppm": 40.0, "temp_c": 0.15, "pm25": 4.0, "vib_mm_s": 0.15}

WORKERS = [  # id, start zone, age
    (1, "A1", 34), (2, "A2", 45), (3, "B2", 29), (4, "B2", 38),
    (5, "B3", 41), (6, "C2", 33), (7, "C3", 27), (8, "B1", 50),
]

DEMO_EVENTS = {
    "sensor_stuck":      {"t": 10 * 60, "zone": "C1", "channel": "co_ppm"},
    "ventilation_fault": {"t": 15 * 60, "zone": "B2", "rate_lel_per_min": 1.0, "restored_t": 47 * 60},
    "heat_stress":       {"t": 20 * 60, "worker": 2, "end_t": 36 * 60},
    "blast":             {"t": 28 * 60, "zone": "A3", "window": (27 * 60, 35 * 60)},
    "fall":              {"t": 40 * 60, "worker": 6},
}

ROVER_SPEED = 1.5        # m/s
ROVER_DWELL_S = 60
ROVER_RELAY_P = 0.9      # assumed worker->rover->gateway success when co-located
AUTO_SOS_AFTER_S = 60    # wearable escalates fall + no motion to SOS
EVENT_RETRIES = 3        # fall/SOS frames are retried until acknowledged (3 tries per 10 s slot)


class Rover:
    """Patrols the closed route; on an SOS it drives the shortest path to the zone."""

    def __init__(self):
        self.seq = patrol_route()
        self.leg = 0
        self.pos = 0.0           # metres along the current leg
        self.dwell = 0.0
        self.mode = "patrol"
        self.visits = {z: [] for z in SUB_ZONES}

    def _leg(self):
        if self.leg >= len(self.seq) - 1:
            return self.seq[-1], self.seq[-1]
        return self.seq[self.leg], self.seq[self.leg + 1]

    @property
    def here(self):
        a, b = self._leg()
        L = distance(a, b)
        return a if L == 0 or self.pos < L / 2 else b

    def xy(self):
        a, b = self._leg()
        L = distance(a, b)
        f = 0.0 if L == 0 else min(self.pos / L, 1.0)
        (x0, y0), (x1, y1) = ZONES[a]["xy"], ZONES[b]["xy"]
        return x0 + f * (x1 - x0), y0 + f * (y1 - y0)

    def rescue(self, target):
        if self.mode != "patrol":
            return
        self.seq = shortest_path(self.here, target)
        self.leg, self.pos, self.dwell = 0, 0.0, 0.0
        self.mode = "rescue" if len(self.seq) > 1 else "on_scene"

    def step(self, dt, t):
        if self.mode == "on_scene":
            return
        if self.dwell > 0:
            self.dwell -= dt
            return
        a, b = self._leg()
        self.pos += ROVER_SPEED * dt
        if self.pos < distance(a, b):
            return
        self.pos = 0.0
        self.leg += 1
        if self.mode == "rescue":
            if self.leg >= len(self.seq) - 1:
                self.mode = "on_scene"
            return
        if self.leg >= len(self.seq) - 1:
            self.leg = 0
        if b in SUB_ZONES and (not self.visits[b] or t - self.visits[b][-1] > 600):
            self.visits[b].append(t)
            self.dwell = ROVER_DWELL_S


class MineSim:
    def __init__(self, seed=7, dt=10, duration_s=3600, events=None, rover_relay=True):
        self.rng = np.random.default_rng(seed)
        self.dt, self.duration = dt, duration_s
        self.events = DEMO_EVENTS if events is None else events
        self.rover_relay = rover_relay
        self.engine = Engine(dt, ages={w: age for w, _, age in WORKERS})
        self.rover = Rover()
        self.workers = {w: {"zone": z, "age": age, "seq": 0, "fall_t": None, "evac": None}
                        for w, z, age in WORKERS}
        self.true_ch4_b2 = []
        self.stats = {"sent": 0, "delivered": 0, "via_rover": 0}

    # ------------------------------------------------------------ truth model
    def _zone_truth(self, z, t):
        v = dict(BASELINE)
        v["temp_c"] += 0.6 * int(z[1])
        ev = self.events.get("ventilation_fault")
        if ev:
            excess = self._vent_excess(ev, t)
            if z == ev["zone"]:
                v["ch4_lel"] += excess
            elif z in downstream(ev["zone"]):
                v["ch4_lel"] += 0.6 * self._vent_excess(ev, t - 120)
        ev = self.events.get("blast")
        if ev and z == ev["zone"] and t >= ev["t"]:
            k = math.exp(-(t - ev["t"]) / 180)
            v["co_ppm"] += 90 * k
            v["pm25"] += 600 * k
            v["co2_ppm"] += 2500 * k
            v["vib_mm_s"] += 20 if t - ev["t"] < 20 else 0
        return v

    @staticmethod
    def _vent_excess(ev, t):
        if t < ev["t"]:
            return 0.0
        peak_t = min(t, ev["restored_t"])
        level = ev["rate_lel_per_min"] * (peak_t - ev["t"]) / 60
        if t > ev["restored_t"]:
            level *= math.exp(-(t - ev["restored_t"]) / 240)
        return level

    def _vitals(self, wid, s, t):
        rng = self.rng
        hr = 88 + 6 * math.sin(t / 300 + wid) + rng.normal(0, 2)
        spo2 = 97 + rng.normal(0, 0.6)
        temp = 37.0 + rng.normal(0, 0.05)
        flags = 0
        ev = self.events.get("heat_stress")
        if ev and wid == ev["worker"] and ev["t"] <= t < ev["end_t"]:
            f = min((t - ev["t"]) / 900, 1.0)
            hr += 60 * f
            temp += 1.6 * f
        ev = self.events.get("fall")
        if ev and wid == ev["worker"] and t >= ev["t"]:
            flags |= packet.FLAG_FALL
            hr, spo2 = 58 + rng.normal(0, 2), 93 + rng.normal(0, 0.5)
            if t - ev["t"] >= 30:
                flags |= packet.FLAG_INACTIVE
            if t - ev["t"] >= AUTO_SOS_AFTER_S:
                flags |= packet.FLAG_SOS
        return int(round(hr)), int(round(min(spo2, 100))), round(temp, 1), flags

    # ------------------------------------------------------------------ radio
    def _deliver(self, zone, tries=1):
        """Hop count of the first successful path, or None if every try fails."""
        for _ in range(tries):
            if self.rng.random() < FIXED_LINK_P[zone]:
                return 0
            if self.rover_relay and self.rover.here == zone and self.rng.random() < ROVER_RELAY_P:
                return 1
        return None

    # ------------------------------------------------------------------- run
    def run(self):
        steps = []
        stuck = self.events.get("sensor_stuck")
        blast = self.events.get("blast")
        for i in range(int(self.duration / self.dt) + 1):
            t = i * self.dt
            self.engine.blast_zones = {blast["zone"]} if blast and blast["window"][0] <= t < blast["window"][1] else set()

            for z in SUB_ZONES:
                truth = self._zone_truth(z, t)
                if z == "B2":
                    self.true_ch4_b2.append(truth["ch4_lel"])
                meas = {k: max(0.0, v + self.rng.normal(0, NOISE[k])) for k, v in truth.items()}
                if stuck and z == stuck["zone"] and t >= stuck["t"]:
                    meas[stuck["channel"]] = 0.0
                self.engine.ingest_zone(z, meas)

            for wid, s in self.workers.items():
                hr, spo2, temp, flags = self._vitals(wid, s, t)
                msg = packet.Telemetry(wid, s["seq"], t, zone_code(s["zone"]), hr, spo2, temp, flags,
                                       battery_pct=max(5, 100 - int(t / 400)),
                                       msg_type=packet.TYPE_SOS if flags & packet.FLAG_SOS else packet.TYPE_TELEMETRY)
                s["seq"] += 1
                self.stats["sent"] += 1
                urgent = flags & (packet.FLAG_FALL | packet.FLAG_SOS)
                hops = self._deliver(s["zone"], tries=EVENT_RETRIES if urgent else 1)
                if hops is not None:
                    msg.hops = hops
                    self.stats["delivered"] += 1
                    self.stats["via_rover"] += hops
                    self.engine.ingest_frame(msg.encode(), t)

            snap = self.engine.step(t)
            self._react(snap, t)
            self.rover.step(self.dt, t)
            rx, ry = self.rover.xy()
            snap["t"] = t
            snap["rover"] = {"x": round(rx, 1), "y": round(ry, 1), "zone": self.rover.here, "mode": self.rover.mode}
            snap["true_zone_of"] = {f"W{w:02d}": s["zone"] for w, s in self.workers.items()}
            steps.append(snap)
        return steps

    def _react(self, snap, t):
        for a in snap["alerts"]:
            if a["kind"] in ("zone", "prediction") and a["level"] in ("High", "Critical"):
                for name in a.get("workers_affected", []):
                    w = self.workers[int(name[1:])]
                    if w["evac"] is None and w["fall_t"] is None:
                        w["evac"] = {"path": shortest_path(w["zone"], "J"), "next_t": t + 60}
            if a["kind"] == "sos":
                self.rover.rescue(a["zone"])
        fall = self.events.get("fall")
        for wid, w in self.workers.items():
            if fall and wid == fall["worker"] and t >= fall["t"]:
                w["fall_t"] = fall["t"]
                continue
            ev = w["evac"]
            if ev and t >= ev["next_t"] and len(ev["path"]) > 1:
                ev["path"].pop(0)
                w["zone"] = ev["path"][0]
                ev["next_t"] = t + 60
