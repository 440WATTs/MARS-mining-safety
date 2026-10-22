"""Run the 60-minute demo scenario and write figures + logs to results/.

    python software/scripts/run_demo.py
"""

import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from mars.sim import MineSim  # noqa: E402
from mars.zones import EDGES, SUB_ZONES, ZONES  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "results"
CAT_COLOUR = {"Low": "#2e9e5b", "Moderate": "#e0b100", "High": "#e8710a", "Critical": "#c62828"}


def main():
    OUT.mkdir(exist_ok=True)
    sim = MineSim(seed=7)
    steps = sim.run()
    alerts = [a for s in steps for a in s["alerts"]]
    t_min = np.array([s["t"] for s in steps]) / 60

    true_ch4 = np.array(sim.true_ch4_b2)
    meas_ch4 = np.array([s["zones"]["B2"]["readings"]["ch4_lel"] for s in steps])
    score = np.array([s["zones"]["B2"]["score"] for s in steps])
    cross = t_min[np.argmax(true_ch4 >= 20)]
    first_warn = min(a["t"] for a in alerts if a["zone"] == "B2" and a["kind"] == "zone") / 60
    withdraw = min(a["t"] for a in alerts if a["zone"] == "B2" and a["level"] in ("High", "Critical")) / 60
    out_b = [s["t"] / 60 for s in steps
             if all(z not in ("B2", "B3") for z in s["true_zone_of"].values())]
    all_out = out_b[0] if out_b else None
    sos = next(a for a in alerts if a["kind"] == "sos")
    on_scene = next(s["t"] for s in steps if s["rover"]["mode"] == "on_scene") / 60

    # --- figure 1: methane build-up in B2 ---------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=160)
    ax.plot(t_min, meas_ch4, color="#9aa5b1", lw=1, label="Sensor reading (simulated, noisy)")
    ax.plot(t_min, true_ch4, color="#1f3b57", lw=2, label="True CH4 in B2")
    ax.axhline(20, color="#c62828", ls="--", lw=1)
    ax.text(1, 20.6, "Danger: 20 %LEL (withdraw + power off)", color="#c62828", fontsize=8)
    ax.axhline(5, color="#e0b100", ls="--", lw=1)
    ax.text(1, 5.6, "Caution: 5 %LEL", color="#9a7a00", fontsize=8)
    for x, y, label, c in ((first_warn, 34, f"Early warning {first_warn:.1f} min", "#b08a00"),
                           (withdraw, 30.5, f"Withdraw order {withdraw:.1f} min", "#e8710a"),
                           (cross, 34, f"Danger reached {cross:.1f} min", "#c62828")):
        ax.axvline(x, color=c, lw=1.2)
        ax.text(x + 0.4, y, label, fontsize=8, color=c, va="top")
    ax.set_xlabel("Minutes")
    ax.set_ylabel("Methane (%LEL)")
    ax.set_ylim(0, 36)
    ax2 = ax.twinx()
    ax2.fill_between(t_min, score, color="#e8710a", alpha=0.10, label="B2 zone risk score")
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Zone risk score (0-100)")
    ax.legend(loc="center left", fontsize=8, frameon=False)
    ax.set_title("SIMULATION - ventilation fault in zone B2 (synthetic data)", fontsize=10, loc="left")
    for a in (ax, ax2):
        a.spines["top"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_methane_b2.png")
    plt.close(fig)

    # --- figure 2: control-room snapshot ----------------------------------
    snap_t = int(sos["t"] / sim.dt) + 6
    s = steps[snap_t]
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=160)
    for a, b in EDGES:
        (x0, y0), (x1, y1) = ZONES[a]["xy"], ZONES[b]["xy"]
        ax.plot([x0, x1], [y0, y1], color="#cfd8dc", lw=14, solid_capstyle="round", zorder=1)
    for z in SUB_ZONES:
        x, y = ZONES[z]["xy"]
        info = s["zones"][z]
        ax.scatter(x, y, s=1500, color=CAT_COLOUR[info["cat"]], zorder=2, edgecolor="white", lw=2)
        ax.text(x, y + 3, z, ha="center", va="center", color="white", fontsize=12, weight="bold", zorder=3)
        ax.text(x, y - 7, f"{info['score']:.0f}", ha="center", va="center", color="white", fontsize=8, zorder=3)
    ax.scatter(0, 0, s=900, color="#455a64", zorder=2)
    ax.text(0, 0, "J", ha="center", va="center", color="white", weight="bold", zorder=3)
    placed = {}
    for wid, w in s["workers"].items():
        x, y = ZONES[w["zone"]]["xy"]
        k = placed.get(w["zone"], 0)
        placed[w["zone"]] = k + 1
        c = CAT_COLOUR[w["cat"]]
        ax.scatter(x - 24 + 16 * k, y - 28, s=90, color=c, edgecolor="#263238", zorder=4)
        ax.text(x - 24 + 16 * k, y - 38, f"W{wid:02d}", ha="center", fontsize=6.5, zorder=4)
    r = s["rover"]
    ax.scatter(r["x"], r["y"] + 26, marker="s", s=140, color="#1565c0", zorder=5)
    ax.text(r["x"], r["y"] + 38, f"Rover ({r['mode'].replace('_', ' ')})", ha="center", fontsize=7.5,
            color="#1565c0", zorder=5)
    for cat, c in CAT_COLOUR.items():
        ax.scatter([], [], color=c, s=80, label=cat)
    ax.legend(loc="lower left", fontsize=7.5, frameon=False, ncol=4, bbox_to_anchor=(0, -0.08))
    ax.set_xlim(-30, 330)
    ax.set_ylim(-165, 165)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"SIMULATION - control-room view at t = {s['t'] / 60:.0f} min (zone score, worker status, rover)",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_zone_map.png")
    plt.close(fig)

    summary = {
        "note": "Synthetic scenario; every number depends on modelling assumptions in software/mars/sim.py",
        "b2_first_warning_min": round(first_warn, 1),
        "b2_withdraw_order_min": round(withdraw, 1),
        "b2_b3_all_workers_out_min": all_out,
        "b2_true_danger_crossing_min": round(cross, 1),
        "lead_time_withdraw_to_danger_min": round(cross - withdraw, 1),
        "sos_alert_min": round(sos["t"] / 60, 1),
        "rover_on_scene_min": round(on_scene, 1),
        "packets": sim.stats,
    }
    (OUT / "demo_summary.json").write_text(json.dumps(summary, indent=2))
    (OUT / "demo_alerts.json").write_text(json.dumps(alerts, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
