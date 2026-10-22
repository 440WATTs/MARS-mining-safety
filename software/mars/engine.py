"""Control-room engine: ingests sensor readings and wearable frames, scores
every zone and worker, and raises de-duplicated alerts with SOP guidance."""

from collections import deque

from . import packet, sop
from .risk import HORIZON_S, PREDICT_WEIGHT, assess_worker, assess_zone, category, combine, sensor_health
from .thresholds import ZONE_CHANNELS
from .zones import SUB_ZONES, downstream, zone_from_code

RANK = {"Low": 0, "Moderate": 1, "High": 2, "Critical": 3}
LOWER_EDGE = {"Low": 0, "Moderate": 25, "High": 50, "Critical": 75}
HYSTERESIS = 5.0
LINK_TIMEOUT_S = 60
LINK_REARM_S = 300        # re-alert a flaky link only after 5 min of good data
SOS_ROUTES = ["Control room", "Rescue team", "Medical team", "Shift supervisor"]
BLAST_CHANNELS = {"co_ppm", "pm25", "vib_mm_s", "co2_ppm"}
CHANNEL_RANGE = {"o2_pct": (0, 25), "ch4_lel": (0, 100), "co_ppm": (0, 2000)}


class Engine:
    def __init__(self, dt=10, ages=None):
        self.dt = dt
        self.ages = ages or {}
        self.hist = {z: {k: deque(maxlen=60) for k in ZONE_CHANNELS} for z in SUB_ZONES}
        self.workers = {}
        self.blast_zones = set()
        self._zone_rank = {z: 0 for z in SUB_ZONES}
        self._worker_rank = {}
        self._faults = set()
        self._link_lost = {}      # worker -> time the link came back (None while still lost)
        self._sos_open = set()
        self.alerts = []

    # ---------------------------------------------------------------- ingest
    def ingest_zone(self, zone, readings):
        for k, v in readings.items():
            self.hist[zone][k].append(v)

    def ingest_frame(self, frame: bytes, t: float):
        try:
            msg = packet.decode(frame)
        except packet.FrameError:
            return None
        self.workers[msg.worker_id] = {"msg": msg, "rx_t": t, "zone": zone_from_code(msg.zone_code)}
        return msg

    # ------------------------------------------------------------------ step
    def step(self, t):
        new = []
        zones = {z: self._zone_step(z, t, new) for z in SUB_ZONES}
        workers = {wid: self._worker_step(wid, t, new) for wid in sorted(self.workers)}
        for a in new:
            if a["zone"] and a["kind"] == "zone":
                hit = {a["zone"], *downstream(a["zone"])}
                a["workers_affected"] = [f"W{w:02d}" for w, s in self.workers.items() if s["zone"] in hit]
        self.alerts.extend(new)
        return {"zones": zones, "workers": workers, "alerts": new}

    def _alert(self, out, t, level, kind, zone, title, detail, hazard=None, worker=None, extra=None):
        a = {"t": t, "level": level, "kind": kind, "zone": zone, "worker": worker,
             "title": title, "detail": detail,
             "sop": sop.actions(hazard, level) if hazard else []}
        if extra:
            a.update(extra)
        out.append(a)

    def _zone_step(self, z, t, out):
        h = self.hist[z]
        a = assess_zone(h, self.dt)
        blasting = z in self.blast_zones
        if blasting:
            # Scheduled blast: CO/dust/vibration transients are expected. Report
            # them, but do not let them drive the zone into High/Critical.
            for d in a.drivers:
                if d.key in BLAST_CHANNELS:
                    d.current, d.predicted = min(d.current, 50.0), 0.0
            a.score = round(combine(d.score for d in a.drivers), 1)
            a.category = category(a.score)

        rank = RANK[a.category]
        if rank > self._zone_rank[z] and rank >= 1:
            top = a.top(1)[0]
            predicted = PREDICT_WEIGHT * top.predicted > top.current
            detail = f"{top.label} {top.value:.1f} {top.unit} now (zone score {a.score:.0f}/100)"
            if top.eta_danger_s is not None:
                detail += f"; trend reaches danger level in ~{top.eta_danger_s / 60:.0f} min"
            if blasting:
                title = f"Scheduled blast in {z}: {top.label.lower()} transient"
                detail += "; re-entry hold until readings clear"
            else:
                title = f"{a.category} risk in {z}: {top.label.lower()}{' rising' if predicted else ''}"
            self._alert(out, t, "Info" if blasting else a.category, "zone", z, title, detail, hazard=top.key,
                        extra={"predicted": predicted,
                               "eta_s": None if top.eta_danger_s is None else round(top.eta_danger_s)})
            self._zone_rank[z] = rank
        elif a.score < LOWER_EDGE[list(RANK)[self._zone_rank[z]]] - HYSTERESIS:
            self._zone_rank[z] = RANK[a.category]

        for k in ZONE_CHANNELS:
            lo, hi = CHANNEL_RANGE.get(k, (None, None))
            status = sensor_health(h[k], lo, hi)
            if status not in ("ok", "no_data") and (z, k) not in self._faults:
                self._faults.add((z, k))
                self._alert(out, t, "Moderate", "sensor_fault", z,
                            f"Sensor fault in {z}: {ZONE_CHANNELS[k].label} {status.replace('_', ' ')}",
                            "Reading excluded from trust; use hand-held gas testing in this zone until repaired")

        return {"score": a.score, "cat": a.category,
                "readings": {k: round(v[-1], 2) for k, v in h.items() if v},
                "top": [{"label": d.label, "value": round(d.value, 2), "unit": d.unit,
                         "score": round(d.score), "eta_s": None if d.eta_danger_s is None else round(d.eta_danger_s)}
                        for d in a.top(3)],
                "faults": sorted(k for (zz, k) in self._faults if zz == z)}

    def _worker_step(self, wid, t, out):
        s = self.workers[wid]
        m = s["msg"]
        name = f"W{wid:02d}"
        age_s = t - s["rx_t"]
        vitals = {"hr": m.hr_bpm or None,
                  "spo2": None if m.spo2 == packet.SPO2_INVALID else m.spo2,
                  "core_temp": m.temp_c,
                  "fall": bool(m.flags & packet.FLAG_FALL),
                  "sos": bool(m.flags & packet.FLAG_SOS),
                  "inactivity_s": 60.0 if m.flags & packet.FLAG_INACTIVE else 0.0}
        a = assess_worker(vitals, self.ages.get(wid, 35))

        if vitals["sos"] and wid not in self._sos_open:
            self._sos_open.add(wid)
            self._alert(out, t, "Critical", "sos", s["zone"], f"SOS: {name} in {s['zone']}",
                        f"HR {m.hr_bpm} bpm, SpO2 {vitals['spo2']} %, temp {m.temp_c:.1f} C, "
                        f"last zone {s['zone']}, via {'direct link' if m.hops == 0 else f'{m.hops}-hop relay'}",
                        hazard="worker_down", worker=name,
                        extra={"routed_to": SOS_ROUTES, "workers_affected": [name]})
        elif not vitals["sos"]:
            self._sos_open.discard(wid)

        rank = RANK[a.category]
        prev = self._worker_rank.get(wid, 0)
        if rank > prev and rank >= 1 and not vitals["sos"]:
            top = a.top(1)[0]
            hazard = "worker_down" if top.key in ("fall", "inactivity_s") else top.key
            self._alert(out, t, a.category, "worker", s["zone"], f"{name}: {top.label.lower()}",
                        f"{top.label} {top.value:g} {top.unit} (worker score {a.score:.0f}/100)",
                        hazard=hazard, worker=name, extra={"workers_affected": [name]})
            self._worker_rank[wid] = rank
        elif a.score < LOWER_EDGE[list(RANK)[prev]] - HYSTERESIS:
            self._worker_rank[wid] = rank

        if age_s > LINK_TIMEOUT_S and wid not in self._link_lost:
            self._link_lost[wid] = None
            self._alert(out, t, "Moderate", "link_lost", s["zone"], f"No data from {name} for {age_s:.0f} s",
                        f"Last seen in {s['zone']}; rover patrol will relay on its next pass",
                        worker=name, extra={"workers_affected": [name]})
        elif age_s > LINK_TIMEOUT_S:
            self._link_lost[wid] = None
        elif wid in self._link_lost:
            ok_since = self._link_lost[wid] if self._link_lost[wid] is not None else t
            self._link_lost[wid] = ok_since
            if t - ok_since >= LINK_REARM_S:
                del self._link_lost[wid]

        flags = [n for bit, n in ((packet.FLAG_FALL, "fall"), (packet.FLAG_INACTIVE, "inactive"),
                                  (packet.FLAG_SOS, "sos"), (packet.FLAG_LOW_BATT, "low_batt"))
                 if m.flags & bit]
        return {"zone": s["zone"], "hr": m.hr_bpm, "spo2": vitals["spo2"], "temp": m.temp_c,
                "score": a.score, "cat": a.category, "flags": flags, "hops": m.hops,
                "last_seen_s": round(age_s), "battery": m.battery_pct}
