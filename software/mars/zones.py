"""Hierarchical zone model of a reference underground layout.

Three primary zones (A, B, C) branch off the shaft-bottom junction J; each has
three sub-zones along its drift. Every worker, rover, sensor node and alert is
tagged with a sub-zone. Coordinates are metres in plan view; the layout is an
illustrative reference mine (~1.0 km of drifts), not a surveyed mine.

Ventilation is modelled as intake at J flowing outward along each drift, so a
gas release in a sub-zone reaches the next sub-zone downstream.
"""

import heapq
import math

ZONES = {
    "J":  {"name": "Shaft bottom", "xy": (0, 0)},
    "A1": {"name": "Zone A / 1", "xy": (80, 120)},
    "A2": {"name": "Zone A / 2", "xy": (180, 120)},
    "A3": {"name": "Zone A / 3", "xy": (280, 120)},
    "B1": {"name": "Zone B / 1", "xy": (80, 0)},
    "B2": {"name": "Zone B / 2", "xy": (180, 0)},
    "B3": {"name": "Zone B / 3", "xy": (280, 0)},
    "C1": {"name": "Zone C / 1", "xy": (80, -120)},
    "C2": {"name": "Zone C / 2", "xy": (180, -120)},
    "C3": {"name": "Zone C / 3", "xy": (280, -120)},
}

EDGES = [
    ("J", "A1"), ("A1", "A2"), ("A2", "A3"),
    ("J", "B1"), ("B1", "B2"), ("B2", "B3"),
    ("J", "C1"), ("C1", "C2"), ("C2", "C3"),
]

SUB_ZONES = [z for z in ZONES if z != "J"]

# Probability that one telemetry packet from a sub-zone reaches the fixed
# gateway at J. ASSUMED values for the simulation only; real values come from
# the planned LoRa range test (docs/roadmap.md).
FIXED_LINK_P = {"J": 0.99, "A1": 0.92, "B1": 0.95, "C1": 0.92,
                "A2": 0.65, "B2": 0.70, "C2": 0.65,
                "A3": 0.25, "B3": 0.30, "C3": 0.25}


def neighbours(zone):
    out = []
    for a, b in EDGES:
        if a == zone:
            out.append(b)
        elif b == zone:
            out.append(a)
    return out


def downstream(zone):
    """Sub-zone(s) that receive this zone's return air."""
    return [b for a, b in EDGES if a == zone]


def distance(a, b):
    (x0, y0), (x1, y1) = ZONES[a]["xy"], ZONES[b]["xy"]
    return math.hypot(x1 - x0, y1 - y0)


def shortest_path(src, dst):
    best = {src: 0.0}
    prev = {}
    heap = [(0.0, src)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == dst:
            break
        if d > best.get(node, math.inf):
            continue
        for nb in neighbours(node):
            nd = d + distance(node, nb)
            if nd < best.get(nb, math.inf):
                best[nb] = nd
                prev[nb] = node
                heapq.heappush(heap, (nd, nb))
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


def patrol_route():
    """Closed tour J -> each drift to its end and back -> J."""
    route = ["J"]
    for p in "ABC":
        route += [f"{p}1", f"{p}2", f"{p}3", f"{p}2", f"{p}1", "J"]
    return route


def route_length(route):
    return sum(distance(a, b) for a, b in zip(route, route[1:]))


def zone_code(zone):
    """One byte on air: high nibble primary (J=0, A=1, B=2, C=3), low nibble sub-zone."""
    if zone == "J":
        return 0x00
    return ((ord(zone[0]) - ord("A") + 1) << 4) | int(zone[1:])


def zone_from_code(code):
    if code == 0x00:
        return "J"
    return f"{chr(ord('A') + (code >> 4) - 1)}{code & 0x0F}"
