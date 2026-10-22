import numpy as np
import pytest

from mars import packet
from mars.risk import assess_worker, assess_zone, category, sensor_health
from mars.sim import MineSim
from mars.thresholds import ZONE_CHANNELS
from mars.zones import SUB_ZONES, zone_code, zone_from_code


def test_crc_check_value():
    assert packet.crc16_ccitt(b"123456789") == 0x29B1


def test_packet_roundtrip_and_corruption():
    msg = packet.Telemetry(6, 41, 2460, zone_code("C2"), 57, 93, 37.1,
                           packet.FLAG_FALL | packet.FLAG_SOS, 94, 1, packet.TYPE_SOS)
    frame = msg.encode()
    assert len(frame) == packet.FRAME_LEN == 20
    assert packet.decode(frame) == msg
    bad = bytearray(frame)
    bad[11] ^= 0x01
    with pytest.raises(packet.FrameError):
        packet.decode(bytes(bad))


def test_zone_codes_roundtrip():
    for z in SUB_ZONES + ["J"]:
        assert zone_from_code(zone_code(z)) == z


def test_categories_and_direction():
    assert [category(s) for s in (0, 30, 60, 90)] == ["Low", "Moderate", "High", "Critical"]
    o2 = ZONE_CHANNELS["o2_pct"]
    assert o2.score(20.9) == 0 and o2.score(19.5) == 50 and o2.bad_when == "low"
    assert ZONE_CHANNELS["ch4_lel"].score(20) == 80


def test_rising_methane_is_flagged_before_it_is_dangerous():
    rng = np.random.default_rng(1)
    ch4 = 3.0 + 1.0 * np.arange(30) * 10 / 60 + rng.normal(0, 0.25, 30)   # +1 %LEL/min
    a = assess_zone({"ch4_lel": ch4}, dt=10)
    top = a.top(1)[0]
    assert top.value < 10 and a.category in ("High", "Critical")
    assert top.eta_danger_s is not None and top.eta_danger_s < 15 * 60


def test_stuck_sensor_detected():
    assert sensor_health([0.0] * 30) == "stuck"
    assert sensor_health(np.random.default_rng(0).normal(3, 0.8, 30)) == "ok"


def test_sos_is_critical():
    assert assess_worker({"hr": 80, "spo2": 97, "core_temp": 37.0, "sos": True}).category == "Critical"


def test_demo_withdraws_workers_before_methane_reaches_danger():
    sim = MineSim(seed=7)
    steps = sim.run()
    crossing = np.argmax(np.array(sim.true_ch4_b2) >= 20) * sim.dt
    evac = min(a["t"] for s in steps for a in s["alerts"]
               if a["zone"] == "B2" and a["level"] in ("High", "Critical"))
    assert evac < crossing - 10 * 60
    assert any(a["kind"] == "sos" for s in steps for a in s["alerts"])
    assert steps[-1]["rover"]["mode"] == "on_scene"
