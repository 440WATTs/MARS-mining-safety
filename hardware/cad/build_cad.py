"""Parametric CAD v0 (CadQuery): wearable chest hub + rover-lite envelope.

    python hardware/cad/build_cad.py      -> out/*.step, out/*.stl, renders/*.png

v0 = sizing/packaging study only. Dimensions come from the selected modules
(see hardware/bom.csv); no FEA, tolerancing or print test has been done yet.
"""

import pathlib

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = pathlib.Path(__file__).resolve().parent
OUT, REN = HERE / "out", HERE / "renders"

# ----------------------------------------------------------------- wearable
HUB_L, HUB_W, HUB_H = 72.0, 48.0, 20.0     # outer envelope, mm
WALL = 2.2
LID_H = 5.0
CORNER_R = 8.0
LUG_W, LUG_H, LUG_BAR, SLOT_W = 13.0, 6.0, 4.5, 3.5


def hub_base():
    outer = cq.Workplane("XY").box(HUB_L, HUB_W, HUB_H - LID_H, centered=(True, True, False)) \
        .edges("|Z").fillet(CORNER_R).faces("<Z").edges().fillet(2.0)
    inner = cq.Workplane("XY").workplane(offset=WALL).box(HUB_L - 2 * WALL, HUB_W - 2 * WALL, HUB_H,
                                                          centered=(True, True, False)) \
        .edges("|Z").fillet(CORNER_R - WALL)
    body = outer.cut(inner)
    # strap lugs: 26 mm slots for a standard chest strap. Rev B: outer bar
    # widened 1.75 -> 4.5 mm and lug 5 -> 6 mm tall after the hand calc in
    # hardware/calcs.py showed ~127 MPa at a 100 N strap snag (PETG ~35 MPa).
    for sx in (-1, 1):
        lug = cq.Workplane("XY").box(LUG_W, 34, LUG_H, centered=(True, True, False)) \
            .translate((sx * (HUB_L / 2 + LUG_W / 2 - 1), 0, 0)).edges("|Z").fillet(2.0)
        slot_c = HUB_L / 2 + LUG_W - 1 - LUG_BAR - SLOT_W / 2
        slot = cq.Workplane("XY").box(SLOT_W, 26, 20).translate((sx * slot_c, 0, 0))
        body = body.union(lug).cut(slot)
    # skin side: two ECG snap studs 40 mm apart + PPG/SpO2 window between them
    for sx in (-20, 20):
        stud = cq.Workplane("XY").circle(2.0).extrude(-3.0).translate((sx, 0, 0)) \
            .union(cq.Workplane("XY").circle(3.0).extrude(-1.2).translate((sx, 0, -3.0)))
        body = body.union(stud)
    body = body.cut(cq.Workplane("XY").rect(10, 8).extrude(WALL * 3).translate((0, 0, -WALL)))
    # USB-C charge port on one end
    body = body.cut(cq.Workplane("YZ").rect(9.5, 3.8).extrude(10).translate((HUB_L / 2 - 6, 0, 8)))
    # internal posts for M2 screws
    for x, y in ((-28, -16), (28, -16), (-28, 16), (28, 16)):
        post = cq.Workplane("XY").circle(2.6).circle(0.9).extrude(HUB_H - LID_H - WALL).translate((x, y, WALL))
        body = body.union(post)
    return body


def hub_lid():
    lid = cq.Workplane("XY").box(HUB_L, HUB_W, LID_H, centered=(True, True, False)) \
        .edges("|Z").fillet(CORNER_R).faces(">Z").edges().fillet(2.5)
    lid = lid.cut(cq.Workplane("XY").box(HUB_L - 2 * WALL, HUB_W - 2 * WALL, LID_H - 1.8,
                                         centered=(True, True, False)).edges("|Z").fillet(CORNER_R - WALL))
    # SOS button: raised guard ring around a 12 mm cap
    ring = cq.Workplane("XY").circle(9.5).circle(7.5).extrude(2.0).translate((10, 0, LID_H))
    cap = cq.Workplane("XY").circle(6.0).extrude(1.2).translate((10, 0, LID_H))
    lid = lid.union(ring).union(cap)
    # status LED window and buzzer grille
    lid = lid.cut(cq.Workplane("XY").circle(1.6).extrude(10).translate((-8, 14, 0)))
    for i in range(3):
        for j in range(4):
            lid = lid.cut(cq.Workplane("XY").circle(0.8).extrude(10).translate((-26 + 4 * j, -6 + 6 * i, 0)))
    return lid.translate((0, 0, HUB_H - LID_H))


# -------------------------------------------------------------------- rover
def rover():
    L, W = 420.0, 300.0
    deck = cq.Workplane("XY").box(L, W - 120, 8).translate((0, 0, 70)).edges("|Z").fillet(12)
    body = cq.Workplane("XY").box(360, 170, 110).translate((0, 0, 129)).edges("|Z").fillet(18) \
        .faces(">Z").edges().fillet(6)
    r = deck.union(body)
    for sx in (-1, 1):
        for sy in (-1, 1):
            wheel = cq.Workplane("XZ").circle(65).extrude(55).translate((sx * 140, sy * 120 + (55 if sy > 0 else 0), 65))
            r = r.union(wheel)
    lidar = cq.Workplane("XY").circle(40).extrude(42).translate((-90, 0, 184))
    mast = cq.Workplane("XY").box(20, 20, 120).translate((110, 0, 244))
    head = cq.Workplane("XY").box(60, 90, 45).translate((110, 0, 318)).edges().fillet(5)
    antenna = cq.Workplane("XY").circle(4).extrude(160).translate((-160, 60, 184))
    bumper = cq.Workplane("XY").box(20, 200, 40).translate((L / 2 - 10, 0, 90)).edges("|Z").fillet(6)
    return r.union(lidar).union(mast).union(head).union(antenna).union(bumper)


# ------------------------------------------------------------------- render
def tris(shape, tol=0.2):
    verts, faces = shape.val().tessellate(tol)
    v = np.array([(p.x, p.y, p.z) for p in verts])
    return v[np.array(faces)]


def render(parts, path, elev=24, azim=-58, title=""):
    fig = plt.figure(figsize=(6, 4.5), dpi=200)
    ax = fig.add_subplot(projection="3d")
    light = np.array([0.4, -0.5, 0.8])
    light /= np.linalg.norm(light)
    allv = []
    for shape, rgb in parts:
        t = tris(shape)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        shade = 0.40 + 0.60 * np.abs(n @ light)
        cols = np.clip(np.outer(shade, rgb), 0, 1)
        ax.add_collection3d(Poly3DCollection(t, facecolors=cols, edgecolors="none"))
        allv.append(t.reshape(-1, 3))
    allv = np.vstack(allv)
    lo, hi = allv.min(0), allv.max(0)
    c, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(c[0] - span, c[0] + span)
    ax.set_ylim(c[1] - span, c[1] + span)
    ax.set_zlim(c[2] - span, c[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev, azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=8)
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(path, transparent=True)
    plt.close(fig)
    from PIL import Image
    im = Image.open(path)
    im.crop(im.getbbox()).save(path)


def main():
    OUT.mkdir(exist_ok=True)
    REN.mkdir(exist_ok=True)
    base, lid, rov = hub_base(), hub_lid(), rover()
    for name, shape in (("wearable_hub_base", base), ("wearable_hub_lid", lid), ("rover_lite_envelope", rov)):
        cq.exporters.export(shape, str(OUT / f"{name}.step"))
        cq.exporters.export(shape, str(OUT / f"{name}.stl"))
    amber, grey, red = (0.98, 0.70, 0.15), (0.32, 0.36, 0.40), (0.85, 0.20, 0.18)
    render([(base, grey), (lid, amber)], REN / "wearable_hub_iso.png")
    render([(base, grey), (lid.translate((0, 0, 22)), amber)], REN / "wearable_hub_exploded.png", elev=18)
    render([(base, grey)], REN / "wearable_hub_skin_side.png", elev=-35, azim=-50)
    render([(rov, (0.85, 0.55, 0.12))], REN / "rover_lite_iso.png", elev=20, azim=-50)
    print("wrote", sorted(p.name for p in OUT.iterdir()), sorted(p.name for p in REN.iterdir()))


if __name__ == "__main__":
    main()
