"""Deck-only figures: wearable wiring diagram + repo evidence capture."""
import pathlib
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = pathlib.Path(sys.argv[1])
REPO = pathlib.Path(sys.argv[2])
PY = sys.argv[3]

NAVY, SLATE, GREEN, BLUE, AMBER, RED = "#0F172A", "#475569", "#059669", "#0369A1", "#B45309", "#B91C1C"


def box(ax, x, y, w, h, title, lines, fc="#F8FAFC", ec="#CBD5E1", tc=NAVY):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec=ec, lw=1.2))
    ax.text(x + 0.12, y + h - 0.16, title, fontsize=9.5, weight="bold", color=tc, va="top")
    for i, ln in enumerate(lines):
        ax.text(x + 0.12, y + h - 0.48 - i * 0.27, ln, fontsize=7.6, color=SLATE, va="top")


def wire(ax, pts, label=None, color=BLUE, lw=1.6, ls="-", lpos=None, lalign="left"):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="round")
    if label:
        lx, ly = lpos or ((xs[0] + xs[1]) / 2, ys[0] + 0.06)
        ax.text(lx, ly, label, fontsize=7, color=color, ha=lalign, va="bottom")


def wiring():
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    # MCU board
    box(ax, 3.85, 1.25, 2.3, 3.1, "Heltec WiFi LoRa 32 V3",
        ["ESP32-S3 MCU (240 MHz, BLE)", "SX1262 LoRa 865-867 MHz", "Li-ion charger + 3V3 LDO",
         "USB-C (charge / flash)", "", "I2C: GPIO17/18 (+ OLED 0x3C)", "ADC1: GPIO7 ECG, GPIO1 VBAT",
         "GPIO: 2 INT, 4-6 ECG, 33 SOS", "PWM: 38 buzzer, 39 vibration"], fc="#EFF6FF", ec="#93C5FD")
    # I2C devices
    box(ax, 0.2, 3.75, 2.55, 1.55, "I2C bus @ 400 kHz, 3V3",
        ["MAX30102 SpO2/PPG   0x57", "MPU-6050 IMU          0x68", "MAX30205 body temp  0x48", "4.7 k pull-ups to 3V3"])
    wire(ax, [(2.75, 4.45), (3.85, 4.45)], "SDA 17 / SCL 18", lpos=(2.82, 4.5))
    wire(ax, [(2.75, 3.95), (3.85, 3.95)], "INT -> GPIO2", color=GREEN, lpos=(2.85, 4.0))
    # ECG
    box(ax, 0.2, 1.6, 2.55, 1.75, "AD8232 ECG front end",
        ["RA / LA / RL to strap snaps", "OUTPUT -> ADC (250 Hz)", "LO+ / LO- -> lead-off flag", "SDN <- GPIO (power save)"])
    wire(ax, [(2.75, 2.75), (3.85, 2.75)], "ECG -> GPIO7", color=BLUE, lpos=(2.85, 2.8))
    wire(ax, [(2.75, 2.25), (3.85, 2.25)], "LO\u00b1 5/6, SDN 4", color=GREEN, lpos=(2.85, 2.3))
    # outputs
    box(ax, 7.25, 3.75, 2.55, 1.55, "Alerts + SOS",
        ["SOS switch -> GPIO, pull-up, IRQ", "Buzzer via NPN (2N2222)", "Vibration motor via AO3400", "  + 1N4148 flyback diode"])
    wire(ax, [(6.15, 4.45), (7.25, 4.45)], "SOS -> GPIO33", color=RED, lpos=(6.25, 4.5))
    wire(ax, [(6.15, 3.95), (7.25, 3.95)], "PWM 38 / 39", color=GREEN, lpos=(6.25, 4.0))
    # power
    box(ax, 7.25, 1.6, 2.55, 1.75, "Power",
        ["LiPo 603040, ~700 mAh, PCM", "-> board JST (VBAT)", "VBAT divider -> ADC (low-batt flag)", "Est. 30.5 mA avg -> ~19 h"],
        fc="#FFFBEB", ec="#FCD34D")
    wire(ax, [(6.15, 2.75), (7.25, 2.75)], "VBAT 3.0-4.2V", color=AMBER, lpos=(6.25, 2.8))
    wire(ax, [(6.15, 2.25), (7.25, 2.25)], "VBAT -> GPIO1", color=AMBER, lpos=(6.25, 2.3))
    # antenna + rail
    ax.plot([5.0, 5.0], [4.35, 5.0], color=NAVY, lw=1.6)
    ax.plot([4.8, 5.0, 5.2], [5.25, 5.0, 5.25], color=NAVY, lw=1.6)
    ax.text(5.28, 5.05, "865 MHz antenna (u.FL)", fontsize=7.5, color=NAVY)
    ax.plot([0.35, 9.65], [0.85, 0.85], color=AMBER, lw=2.2)
    ax.text(0.35, 0.55, "3V3 rail from board LDO feeds MAX30102, MPU-6050, MAX30205, AD8232   |   common GND star point at board",
            fontsize=7.5, color=AMBER)
    for x in (1.475, 5.0, 8.525):
        ax.plot([x, x], [0.85, 1.25 if x == 5.0 else 1.6], color=AMBER, lw=1.2, ls=":")
    ax.text(0.2, 0.02, "Wiring v0 - planned ESP32-S3 GPIO map (avoids LoRa 8-14, OLED 17/18/21, strapping 0/3/45/46, flash 26-32).\nConfirm against the Heltec V3 pinout at bring-up; KiCad schematic follows in Stage 3.",
            fontsize=7, color=SLATE, style="italic")
    fig.savefig(OUT / "wiring_v0.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def evidence():
    log = subprocess.run(["git", "-C", str(REPO), "log", "--date=format:%d %b %Y %H:%M", "--pretty=%h  %ad  %s"],
                         capture_output=True, text=True).stdout.strip().splitlines()
    test = subprocess.run([PY, "-m", "pytest", "-q", "tests"], cwd=REPO / "software",
                          capture_output=True, text=True).stdout.strip().splitlines()
    calc = subprocess.run([PY, "hardware/calcs.py"], cwd=REPO, capture_output=True, text=True).stdout.strip().splitlines()
    lines = (["$ git log --oneline (github.com/440WATTs/MARS-mining-safety)"] + log +
             ["", "$ cd software && python -m pytest -q tests"] + test[-2:] +
             ["", "$ python hardware/calcs.py"] + calc)
    fig = plt.figure(figsize=(7.2, 0.21 * len(lines) + 0.4), dpi=200)
    fig.patch.set_facecolor("#0F172A")
    for i, ln in enumerate(lines):
        col = "#7DD3FC" if ln.startswith("$") else ("#86EFAC" if "passed" in ln else "#E2E8F0")
        fig.text(0.02, 1 - (i + 1) * (1 / (len(lines) + 1.5)), ln, family="DejaVu Sans Mono", fontsize=7, color=col)
    fig.savefig(OUT / "repo_evidence.png", facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    wiring()
    evidence()
    print("ok")
