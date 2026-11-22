"""Animated pictures for the side panel: one themed scene per page.

A rotating globe for the dashboard, a spinning disk for storage, a radar for cleanup
and so on. Everything is drawn with plain canvas shapes (no image files), on a canvas
with the page's own colour, so it reads as part of the background.

Only the page you are looking at animates, and it all stops (leaving one still
picture) if animations are turned off in Settings.
"""
import math
import random
import time
import tkinter as tk

from . import anim, theme

FPS = 20

SCENE_BY_PAGE = {
    "Dashboard": "globe", "Processes": "galaxy", "Storage": "disk", "Network": "network",
    "Hardware": "chip", "Cleanup": "radar", "App Launcher": "tiles",
    "Startup Manager": "power", "Voice Control": "voice", "Settings": "gears",
}


class Backdrop(tk.Canvas):
    def __init__(self, master, kind="globe"):
        super().__init__(master, width=10, height=10, highlightthickness=0, bd=0,
                         bg=theme.resolve(theme.BG))
        self.kind = kind if kind in KINDS else "globe"
        self._job = None
        self._t0 = time.monotonic()
        self._pings = []
        self.bg = theme.resolve(theme.BG)
        self.base = theme.accent("main")
        theme.on_change(self._recolor)
        self._redraw_job = None
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, _event=None):
        """Resizing fires this dozens of times a second. Draw once, when it settles."""
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
        self._redraw_job = self.after(90, self._settled)

    def _settled(self):
        self._redraw_job = None
        self.draw()

    def set_kind(self, kind):
        self.kind = kind if kind in KINDS else "globe"
        self._pings = []
        self.draw()

    # ---- running -------------------------------------------------------------------
    def start(self):
        if self._job is not None:
            return
        if not anim.is_enabled("scenes"):
            self.draw()               # one still picture
            return
        self._loop()

    def stop(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _loop(self):
        self.draw()
        if anim.is_enabled("scenes"):
            self._job = self.after(int(1000 / FPS), self._loop)
        else:
            self._job = None          # switched off while running: keep the still picture

    def _recolor(self):
        try:
            self.configure(bg=theme.resolve(theme.BG))
        except tk.TclError:
            return
        self.draw()

    # ---- drawing ---------------------------------------------------------------------
    def K(self, amount):
        """The accent colour blended into the background: 0 = background, 1 = full accent."""
        return theme.lerp(self.bg, self.base, amount)

    def draw(self):
        try:
            width, height = self.winfo_width(), self.winfo_height()
            if width < 60 or height < 60:
                return
            self.bg = theme.resolve(theme.BG)
            self.base = theme.accent("main")
            self.delete("all")
            t = time.monotonic() - self._t0 if anim.is_enabled("scenes") else 1.7
            _stars(self, width, height, t)
            KINDS[self.kind](self, width, height, t)
        except tk.TclError:
            pass

    def circle(self, cx, cy, r, **kw):
        return self.create_oval(cx - r, cy - r, cx + r, cy + r, **kw)

    def dot(self, x, y, r, color):
        return self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")


_star_list = []


def _stars(c, w, h, t):
    if not _star_list:
        rng = random.Random(11)
        _star_list.extend((rng.random(), rng.random(), rng.random() * 6.28, rng.choice((1, 1, 1.4)))
                          for _ in range(55))
    for fx, fy, phase, size in _star_list:
        glow = (math.sin(t * 1.4 + phase) + 1) / 2
        c.dot(fx * w, fy * h, size, c.K(0.10 + 0.32 * glow))


def _glow(c, cx, cy, r, strength=0.02, steps=9):
    for i in range(steps, 0, -1):
        c.circle(cx, cy, r * (1 + 0.06 * i), fill=c.K(strength * (steps + 1 - i)), outline="")


# Rough outlines of the continents as (longitude, latitude). Deliberately low-poly:
# it suits the "network" look and keeps drawing cheap.
LAND = [
    # North America
    [(-167, 65), (-157, 71), (-141, 70), (-125, 70), (-110, 68), (-95, 69), (-85, 70),
     (-82, 63), (-93, 59), (-92, 57), (-82, 55), (-79, 52), (-78, 62), (-72, 61),
     (-65, 60), (-60, 55), (-56, 52), (-66, 45), (-70, 43), (-76, 39), (-76, 35),
     (-81, 31), (-80, 26), (-83, 29), (-90, 30), (-97, 27), (-97, 22), (-92, 19),
     (-88, 21), (-87, 16), (-83, 15), (-83, 10), (-79, 9), (-85, 10), (-87, 13),
     (-92, 15), (-97, 16), (-105, 20), (-106, 23), (-112, 29), (-114, 31), (-117, 32),
     (-121, 35), (-124, 40), (-124, 47), (-128, 51), (-134, 58), (-141, 60),
     (-152, 59), (-158, 56), (-164, 55), (-158, 58), (-165, 61)],
    # Greenland
    [(-73, 78), (-60, 82), (-30, 83), (-20, 80), (-20, 72), (-30, 68), (-43, 60),
     (-50, 63), (-55, 70), (-67, 76)],
    # South America
    [(-80, 8), (-72, 12), (-62, 10), (-52, 5), (-50, 0), (-44, -2), (-35, -6),
     (-39, -14), (-41, -22), (-48, -26), (-53, -34), (-58, -38), (-63, -41),
     (-65, -47), (-68, -52), (-72, -54), (-75, -48), (-73, -38), (-71, -30),
     (-70, -18), (-76, -14), (-81, -6), (-80, -1), (-78, 3), (-77, 8)],
    # Europe and Asia
    [(-9, 37), (-9, 43), (-1, 44), (-4, 48), (2, 51), (8, 54), (10, 57), (12, 55),
     (14, 54), (20, 55), (24, 59), (30, 60), (22, 61), (25, 65), (21, 65), (17, 61),
     (18, 59), (15, 56), (11, 59), (5, 59), (5, 62), (14, 67), (20, 70), (30, 71),
     (41, 67), (44, 68), (60, 69), (70, 73), (80, 73), (100, 77), (113, 74),
     (130, 71), (140, 72), (160, 70), (170, 70), (180, 68), (180, 65), (170, 60),
     (163, 60), (156, 51), (143, 59), (135, 55), (140, 48), (130, 43), (127, 39),
     (129, 35), (126, 35), (125, 39), (121, 40), (118, 38), (122, 37), (120, 32),
     (122, 30), (119, 25), (110, 21), (108, 16), (109, 12), (105, 9), (101, 13),
     (100, 8), (104, 1), (100, 3), (98, 8), (98, 16), (94, 17), (91, 22), (87, 21),
     (80, 15), (77, 8), (73, 16), (72, 21), (67, 24), (61, 25), (57, 26), (56, 27),
     (50, 30), (48, 29), (51, 25), (56, 25), (59, 22), (52, 16), (43, 13), (39, 21),
     (35, 28), (34, 31), (36, 36), (30, 36), (27, 37), (26, 40), (29, 41), (23, 40),
     (22, 37), (19, 42), (13, 45), (16, 41), (18, 40), (16, 38), (12, 42), (8, 44),
     (3, 43), (-1, 37), (-5, 36)],
    # Africa
    [(-17, 21), (-16, 28), (-10, 30), (-6, 36), (10, 37), (11, 33), (20, 31), (32, 31),
     (34, 28), (38, 19), (43, 12), (51, 12), (51, 2), (41, -3), (39, -8), (40, -15),
     (35, -20), (33, -27), (27, -34), (19, -35), (16, -28), (12, -17), (14, -9),
     (9, -1), (9, 4), (5, 5), (-4, 5), (-8, 4), (-13, 8), (-17, 14)],
    # Australia
    [(114, -22), (122, -18), (130, -12), (137, -12), (142, -11), (146, -19), (153, -26),
     (150, -37), (141, -38), (135, -34), (129, -32), (116, -35), (113, -26)],
    # smaller ones: Britain, Japan, Borneo, Sumatra, Madagascar, Iceland, Cuba, New Zealand
    [(-5, 50), (1, 51), (-2, 56), (-5, 58), (-6, 55), (-3, 53)],
    [(130, 31), (135, 34), (141, 38), (142, 45), (140, 41), (135, 36)],
    [(109, 1), (117, 7), (119, 1), (116, -4), (110, -3)],
    [(95, 5), (104, -5), (106, -6), (98, 0)],
    [(44, -25), (50, -15), (49, -12), (44, -17)],
    [(-24, 65), (-14, 66), (-14, 64), (-22, 63.5)],
    [(-85, 22), (-74, 20), (-80, 23)],
    [(173, -35), (178, -38), (174, -41), (172, -45), (167, -46), (172, -41)],
]

# (name, latitude, longitude) of the glowing network nodes. Bratislava is yours.
CITIES = [
    ("Bratislava", 48.1, 17.1), ("New York", 40.7, -74.0), ("Los Angeles", 34.0, -118.2),
    ("Sao Paulo", -23.5, -46.6), ("London", 51.5, -0.1), ("Lagos", 6.5, 3.4),
    ("Cairo", 30.0, 31.2), ("Moscow", 55.7, 37.6), ("Dubai", 25.2, 55.3),
    ("Mumbai", 19.1, 72.9), ("Singapore", 1.3, 103.8), ("Beijing", 39.9, 116.4),
    ("Tokyo", 35.7, 139.7), ("Sydney", -33.9, 151.2), ("Johannesburg", -26.2, 28.0),
    ("Mexico City", 19.4, -99.1),
]
LINKS = [(0, 4), (0, 1), (0, 8), (0, 7), (0, 6), (1, 2), (1, 3), (1, 15), (4, 5), (8, 9),
         (9, 10), (10, 13), (11, 12), (11, 7), (14, 5), (2, 12), (6, 14), (10, 11)]

_earth_cache = {}


def _xyz(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo))


def _earth_data():
    """Turn the lists above into 3-D points once (with extra points on long edges,
    so the coastlines curve with the globe)."""
    if _earth_cache:
        return _earth_cache
    polygons = []
    for outline in LAND:
        points = []
        for i, (lon, lat) in enumerate(outline):
            lon2, lat2 = outline[(i + 1) % len(outline)]
            steps = max(1, int(max(abs(lon2 - lon), abs(lat2 - lat)) // 5))
            for k in range(steps):
                f = k / steps
                points.append(_xyz(lat + (lat2 - lat) * f, lon + (lon2 - lon) * f))
        polygons.append(points)
    nodes = [_xyz(lat, lon) for _name, lat, lon in CITIES]
    arcs = []
    for a, b in LINKS:
        pa, pb = nodes[a], nodes[b]
        omega = math.acos(max(-1, min(1, sum(u * v for u, v in zip(pa, pb)))))
        lift = 0.12 * omega
        samples = []
        for k in range(15):
            f = k / 14
            wa, wb = math.sin((1 - f) * omega) / math.sin(omega), math.sin(f * omega) / math.sin(omega)
            height = 1 + lift * math.sin(math.pi * f)
            samples.append(tuple((wa * u + wb * v) * height for u, v in zip(pa, pb)))
        arcs.append(samples)
    rng = random.Random(3)
    stars = [(rng.random(), rng.random(), rng.random() * 6.28, rng.choice((1, 1, 1.5)))
             for _ in range(45)]
    meridians = []
    for lon in range(0, 360, 30):
        meridians.append([_xyz(lat, lon) for lat in range(-90, 91, 10)])
    parallels = []
    for lat in range(-60, 61, 30):
        parallels.append([_xyz(lat, lon) for lon in range(0, 361, 10)])
    _earth_cache.update(polygons=polygons, nodes=nodes, arcs=arcs, stars=stars,
                        meridians=meridians, parallels=parallels)
    return _earth_cache



def _earth(c, w, h, t, network):
    """A detailed rotating Earth, big and slightly cut off by the window edge."""
    K = c.K
    data = _earth_data()
    r = min(h * 0.40, w * 0.58)
    cx, cy = w - r * 0.72, h / 2

    _glow(c, cx, cy, r)
    c.circle(cx, cy, r, fill=K(0.30), outline="")
    for i in range(1, 8):                                  # lit from the upper left
        shift = r * 0.07 * i
        c.circle(cx - shift, cy - shift, r * (1 - 0.12 * i), fill=K(0.30 + 0.035 * i), outline="")

    spin = t * 0.35 + 0.9
    tilt = math.radians(20)
    cs, sn, ct, st = math.cos(spin), math.sin(spin), math.cos(tilt), math.sin(tilt)

    def project(p):
        x, y, z = p
        x, z = x * cs + z * sn, -x * sn + z * cs
        y, z = y * ct - z * st, y * st + z * ct
        return cx + x * r, cy - y * r, z, x, y

    def line_of(points, color, width=1):
        run = []
        for p in points:
            sx, sy, z, _x, _y = project(p)
            if z > 0:
                run += [sx, sy]
            else:
                if len(run) >= 4:
                    c.create_line(*run, fill=color, width=width)
                run = []
        if len(run) >= 4:
            c.create_line(*run, fill=color, width=width)

    for ring in data["meridians"] + data["parallels"]:
        line_of(ring, K(0.46))

    land, coast = K(0.62), K(0.9)
    for polygon in data["polygons"]:
        flat, seen = [], False
        for p in polygon:
            sx, sy, z, x, y = project(p)
            if z > 0:
                seen = True
            else:                                          # far side: pin it to the edge
                d = math.hypot(x, y) or 1
                sx, sy = cx + x / d * r, cy - y / d * r
            flat += [sx, sy]
        if seen and len(flat) >= 6:
            c.create_polygon(*flat, fill=land, outline=coast)

    if network:
        for n, samples in enumerate(data["arcs"]):
            line_of(samples, K(1.0), 1)
            f = (t * 0.3 + n * 0.37) % 1
            sx, sy, z, _x, _y = project(samples[min(14, int(f * 14))])
            if z > 0:
                c.dot(sx, sy, 2, "#ffffff" if theme.is_dark() else c.base)
        for i, p in enumerate(data["nodes"]):
            sx, sy, z, _x, _y = project(p)
            if z > 0.05:
                home = i == 0
                pulse = (math.sin(t * 2.2 + i) + 1) / 2
                c.circle(sx, sy, (4 if home else 2.5) + pulse * (5 if home else 3),
                         outline=K(0.5 - 0.3 * pulse))
                c.dot(sx, sy, 3.2 if home else 2, "#ffffff" if theme.is_dark() else c.base)
        if len(c._pings) < 4 and random.random() < 0.1:
            c._pings.append((random.uniform(-55, 55), random.uniform(-180, 180), t))
        alive = []
        for lat, lon, born in c._pings:
            age = t - born
            if age > 1.8:
                continue
            alive.append((lat, lon, born))
            sx, sy, z, _x, _y = project(_xyz(lat, lon))
            if z > 0.15:
                c.circle(sx, sy, 2 + age * 10, outline=K(0.8 * (1 - age / 1.8)))
        c._pings = alive
    else:
        # Dashboard: no dots. A glowing meridian scans around the planet, and two
        # orbit rings carry comets with long fading tails.
        scan = [_xyz(lat, (t * 55) % 360) for lat in range(-90, 91, 6)]
        line_of(scan, K(1.0), 2)
        line_of([_xyz(lat, (t * 55 - 6) % 360) for lat in range(-90, 91, 6)], K(0.7), 1)
        for tilt_deg, scale, speed, phase in ((-24, 1.38, 0.55, 0.0), (28, 1.2, -0.8, 2.1)):
            a = math.radians(tilt_deg)
            rx, ry = r * scale, r * scale * 0.30

            def orbit(u, rx=rx, ry=ry, a=a):
                x, y = math.cos(u) * rx, math.sin(u) * ry
                return (cx + x * math.cos(a) - y * math.sin(a),
                        cy + x * math.sin(a) + y * math.cos(a), math.sin(u))

            for k in range(0, 360, 8):                      # the ring: faint, hidden behind the globe
                u1, u2 = math.radians(k), math.radians(k + 8)
                x1, y1, depth = orbit(u1)
                x2, y2, _ = orbit(u2)
                if depth > 0 or math.hypot(x1 - cx, y1 - cy) > r:
                    c.create_line(x1, y1, x2, y2, fill=K(0.62))
            head = t * speed + phase
            direction = 1 if speed > 0 else -1
            for k in range(26):                             # the comet's tail
                u = head - direction * k * 0.045
                x1, y1, depth = orbit(u)
                x2, y2, _ = orbit(u - direction * 0.045)
                if depth > 0 or math.hypot(x1 - cx, y1 - cy) > r:
                    c.create_line(x1, y1, x2, y2, fill=K(1.0 - k / 26 * 0.9),
                                  width=max(1, 3 - k // 9))

    c.circle(cx, cy, r, outline=K(0.9), width=1)                       # bright edge
    c.circle(cx, cy, r * 1.015, outline=K(0.25), width=1)


def _globe(c, w, h, t):
    _earth(c, w, h, t, network=False)


def _network(c, w, h, t):
    _earth(c, w, h, t, network=True)


def _disk(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    R = min(w * 0.40, h * 0.30)
    _glow(c, cx, cy, R)
    c.circle(cx, cy, R, fill=K(0.14), outline=K(0.55), width=2)
    for i in range(1, 6):                                     # soft metallic banding
        c.circle(cx, cy, R * (1 - 0.15 * i), fill=K(0.14 + 0.012 * i), outline="")
    for i in range(16):
        c.circle(cx, cy, R * (0.30 + 0.70 * i / 15), outline=K(0.13))
    rng = random.Random(5)
    for ring in range(10):                                    # stored data, turning at different speeds
        rr = R * (0.36 + 0.60 * ring / 9)
        turn = math.degrees(t) * (0.9 if ring % 2 else -0.6) * (1.2 - ring * 0.07)
        for _ in range(3):
            start, extent = rng.uniform(0, 360), rng.uniform(18, 70)
            tone = rng.choice((0.5, 0.7, 0.95))
            c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=start + turn, extent=extent,
                         style="arc", outline=K(tone), width=3)
    for k in (0, 1):                                          # light sweeping over the platter
        c.create_arc(cx - R * 0.98, cy - R * 0.98, cx + R * 0.98, cy + R * 0.98,
                     start=t * 25 + k * 180, extent=22, style="pieslice", fill=K(0.2),
                     outline="")
    c.circle(cx, cy, R * 0.27, fill=K(0.30), outline=K(0.85), width=2)
    c.circle(cx, cy, R * 0.11, fill=c.bg, outline=K(0.85))
    for k in range(6):
        a = math.tau * k / 6 + t * 0.4
        c.dot(cx + math.cos(a) * R * 0.19, cy + math.sin(a) * R * 0.19, 2, K(0.95))
    # the read arm, sliding in and out
    px, py = cx + R * 1.02, cy + R * 0.98
    angle = math.radians(222)
    length = R * (1.18 + 0.20 * math.sin(t * 0.7))
    hx, hy = px + math.cos(angle) * length, py + math.sin(angle) * length
    c.create_line(px, py, hx, hy, fill=K(0.55), width=6, capstyle="round")
    c.create_line(px, py, hx, hy, fill=K(0.95), width=2, capstyle="round")
    c.circle(px, py, R * 0.09, fill=K(0.40), outline=K(0.9), width=2)
    pulse = (math.sin(t * 5) + 1) / 2
    c.circle(hx, hy, 4 + pulse * 5, outline=K(0.4 + 0.5 * pulse))
    c.dot(hx, hy, 3, K(1.0))


_galaxy = []


def _galaxy_stars():
    if not _galaxy:
        rng = random.Random(21)
        for _ in range(560):
            radius = rng.random() ** 0.62
            arm = rng.randrange(3)
            _galaxy.append((radius, arm * math.tau / 3 + radius * 5.2 + rng.gauss(0, 0.22),
                            rng.choice((1, 1, 1.5, 2.1)), rng.random()))
    return _galaxy


def _galaxy_scene(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    R = min(w * 0.53, h * 0.38)
    tilt = math.radians(-24)
    ct, st = math.cos(tilt), math.sin(tilt)
    _glow(c, cx, cy, R * 0.7, 0.012)
    for scale in (1.0, 0.7, 0.4):
        pts = []
        for k in range(0, 361, 12):
            x, y = math.cos(math.radians(k)) * R * scale, math.sin(math.radians(k)) * R * scale * 0.5
            pts += [cx + x * ct - y * st, cy + x * st + y * ct]
        c.create_line(*pts, fill=K(0.10))
    for radius, theta, size, tone in _galaxy_stars():
        a = theta + t * 0.9 / (0.3 + radius)
        x, y = math.cos(a) * radius * R, math.sin(a) * radius * R * 0.5
        sx, sy = cx + x * ct - y * st, cy + x * st + y * ct
        twinkle = 0.75 + 0.25 * math.sin(t * 2 + tone * 20)
        c.dot(sx, sy, size, K((0.95 - 0.6 * radius) * twinkle))
    for i in range(7, 0, -1):                                 # glowing core
        c.circle(cx, cy, R * 0.05 * i, fill=K(0.95 - 0.12 * i), outline="")
    c.dot(cx, cy, 4, K(1.0))


def _chip(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    H = min(w * 0.21, h * 0.15)
    pulse = (math.sin(t * 1.6) + 1) / 2
    _glow(c, cx, cy, H * 1.5, 0.012)
    pins = 7
    for side in range(4):                                     # pins and the board traces leaving them
        for i in range(pins):
            o = (i - (pins - 1) / 2) * H * 0.26
            if side == 0:   out, sx, sy = (0, -1), cx + o, cy - H
            elif side == 1: out, sx, sy = (0, 1), cx + o, cy + H
            elif side == 2: out, sx, sy = (-1, 0), cx - H, cy + o
            else:           out, sx, sy = (1, 0), cx + H, cy + o
            tip = (sx + out[0] * H * 0.22, sy + out[1] * H * 0.22)
            perp = (out[1], out[0])
            bend = (i - (pins - 1) / 2) * H * 0.22
            reach = (min(cx, w - cx) - 4) if out[0] else (min(cy, h - cy) - 4)
            far = H + H * 0.5 + (reach - H * 1.5) * (0.5 + 0.08 * ((i * 3) % 5))
            p1 = (cx + out[0] * far * 0.55 + (o if out[1] else 0) * 1,
                  cy + out[1] * far * 0.55 + (o if out[0] else 0) * 1)
            p2 = (p1[0] + perp[0] * bend, p1[1] + perp[1] * bend)
            p3 = (p2[0] + out[0] * far * 0.45, p2[1] + out[1] * far * 0.45)
            path = [(sx, sy), tip, p1, p2, p3]
            c.create_line(*[v for p in path for v in p], fill=K(0.22), width=1)
            c.create_line(sx, sy, tip[0], tip[1], fill=K(0.6), width=3)
            lengths = [math.dist(path[k], path[k + 1]) for k in range(4)]
            total = sum(lengths)
            for k in range(3):                                # data pulses flowing outward
                f = (t * 0.32 + i * 0.13 + side * 0.21 - k * 0.025) % 1
                dist, k2 = f * total, 0
                while k2 < 3 and dist > lengths[k2]:
                    dist -= lengths[k2]
                    k2 += 1
                ratio = dist / (lengths[k2] or 1)
                x = path[k2][0] + (path[k2 + 1][0] - path[k2][0]) * ratio
                y = path[k2][1] + (path[k2 + 1][1] - path[k2][1]) * ratio
                c.dot(x, y, 2.4 - k * 0.6, K(1.0 - k * 0.3))
    c.create_rectangle(cx - H * 1.12, cy - H * 1.12, cx + H * 1.12, cy + H * 1.12,
                       outline=K(0.22), width=1)
    c.create_rectangle(cx - H, cy - H, cx + H, cy + H, fill=K(0.12), outline=K(0.95), width=2)
    c.create_polygon(cx - H, cy - H, cx - H * 0.78, cy - H, cx - H, cy - H * 0.78,
                     fill=K(0.95), outline="")                # pin-1 corner mark
    cell = H * 0.52
    for row in range(3):
        for col in range(3):
            heat = (math.sin(t * 1.8 + row * 1.3 + col * 2.1) + 1) / 2
            x, y = cx + (col - 1) * cell * 1.05, cy + (row - 1) * cell * 1.05
            c.create_rectangle(x - cell * 0.42, y - cell * 0.42, x + cell * 0.42,
                               y + cell * 0.42, fill=K(0.18 + 0.6 * heat),
                               outline=K(0.5))
    c.create_rectangle(cx - H * 0.8, cy - H * 0.8, cx + H * 0.8, cy + H * 0.8,
                       outline=K(0.3 + 0.4 * pulse), dash=(3, 4))


def _radar(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    R = min(w * 0.44, h * 0.32)
    _glow(c, cx, cy, R, 0.012)
    c.circle(cx, cy, R, fill=K(0.07), outline=K(0.6), width=2)
    for k in (0.8, 0.6, 0.4, 0.2):
        c.circle(cx, cy, R * k, outline=K(0.2))
    for deg in range(0, 360, 6):                              # compass ticks
        a = math.radians(deg)
        inner = R * (0.93 if deg % 30 == 0 else 0.97)
        c.create_line(cx + math.cos(a) * inner, cy - math.sin(a) * inner,
                      cx + math.cos(a) * R, cy - math.sin(a) * R,
                      fill=K(0.55 if deg % 30 == 0 else 0.3))
    c.create_line(cx - R, cy, cx + R, cy, fill=K(0.18))
    c.create_line(cx, cy - R, cx, cy + R, fill=K(0.18))
    angle = -t * 1.25                                         # clockwise sweep
    for k in range(30):                                       # glowing wedge behind the line
        c.create_arc(cx - R, cy - R, cx + R, cy + R,
                     start=math.degrees(angle) + k * 2.4, extent=2.6, style="pieslice",
                     fill=K(0.05 + 0.33 * (1 - k / 30) ** 1.5), outline="")
    c.create_line(cx, cy, cx + math.cos(angle) * R, cy - math.sin(angle) * R,
                  fill=K(1.0), width=2)
    rng = random.Random(9)
    for _ in range(9):                                        # things it finds
        phi, rad = rng.uniform(0, math.tau), rng.uniform(0.2, 0.92) * R
        since = (phi - angle) % math.tau
        if since < 3.0:
            fade = 1 - since / 3.0
            x, y = cx + math.cos(phi) * rad, cy - math.sin(phi) * rad
            c.dot(x, y, 2 + 3 * fade, K(0.3 + 0.7 * fade))
            c.circle(x, y, 4 + (1 - fade) * 12, outline=K(0.6 * fade))
    c.dot(cx, cy, 3, K(1.0))


def _tiles(c, w, h, t):
    K = c.K
    n = 6
    s = min(w * 0.072, h * 0.045)
    cx, cy = w / 2, h / 2 + s * 1.2
    cells = sorted(((i, j) for i in range(n) for j in range(n)), key=lambda p: p[0] + p[1])
    _glow(c, cx, cy, s * n * 0.9, 0.01)
    for i, j in cells:
        x = cx + (i - j) * s
        y = cy + (i + j - (n - 1)) * s * 0.5
        wave = (math.sin(math.hypot(i - 2.5, j - 2.5) * 1.1 - t * 2.2) + 1) / 2
        lift = s * (0.25 + 1.1 * wave)
        top = [x, y - lift - s * 0.5, x + s * 0.92, y - lift, x, y - lift + s * 0.5,
               x - s * 0.92, y - lift]
        left = [x - s * 0.92, y - lift, x, y - lift + s * 0.5, x, y + s * 0.5,
                x - s * 0.92, y]
        right = [x + s * 0.92, y - lift, x, y - lift + s * 0.5, x, y + s * 0.5,
                 x + s * 0.92, y]
        c.create_polygon(*left, fill=K(0.14 + 0.18 * wave), outline=K(0.45))
        c.create_polygon(*right, fill=K(0.08 + 0.14 * wave), outline=K(0.45))
        c.create_polygon(*top, fill=K(0.30 + 0.62 * wave), outline=K(0.95))


def _power(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    R = min(w * 0.42, h * 0.30)
    breathe = (math.sin(t * 1.6) + 1) / 2
    _glow(c, cx, cy, R * 0.9, 0.012 + 0.006 * breathe)
    for i in range(5, 0, -1):                                 # glow behind the symbol
        c.circle(cx, cy, R * 0.14 * i * (0.92 + 0.08 * breathe), fill=K(0.05 * (6 - i)), outline="")
    head = (t * 1.3) % math.tau
    for k in range(72):                                       # outer tick ring with a bright sweep
        a = math.tau * k / 72
        near = (head - a) % math.tau
        glow = max(0.0, 1 - near / 2.4)
        inner = R * (0.92 if k % 6 else 0.86)
        c.create_line(cx + math.cos(a) * inner, cy - math.sin(a) * inner,
                      cx + math.cos(a) * R, cy - math.sin(a) * R,
                      fill=K(0.32 + 0.68 * glow), width=2 if glow > 0.5 else 1)
    c.circle(cx, cy, R * 0.78, outline=K(0.3))
    for k in range(3):                                        # counter-rotating bands
        c.create_arc(cx - R * 0.72, cy - R * 0.72, cx + R * 0.72, cy + R * 0.72,
                     start=-t * 40 + k * 120, extent=70, style="arc", outline=K(0.8), width=4)
    for k in range(18):                                       # dashed inner ring
        c.create_arc(cx - R * 0.56, cy - R * 0.56, cx + R * 0.56, cy + R * 0.56,
                     start=t * 28 + k * 20, extent=10, style="arc", outline=K(0.5), width=2)
    boot = 90 + 220 * (0.5 + 0.5 * math.sin(t * 0.6))         # a ring that fills and empties
    c.create_arc(cx - R * 0.46, cy - R * 0.46, cx + R * 0.46, cy + R * 0.46, start=90,
                 extent=-boot, style="arc", outline=K(1.0), width=5)
    g = R * 0.2                                               # the power symbol
    c.create_arc(cx - g, cy - g, cx + g, cy + g, start=125, extent=290, style="arc",
                 outline=K(1.0), width=4)
    c.create_line(cx, cy - g * 1.25, cx, cy - g * 0.1, fill=K(1.0), width=4, capstyle="round")


def _voice(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    R = min(w * 0.42, h * 0.30)
    base = R * 0.55
    _glow(c, cx, cy, base, 0.012)
    for k in range(3):                                        # ripples spreading out
        age = (t * 0.45 + k / 3) % 1
        c.circle(cx, cy, base + age * R * 0.9, outline=K(0.5 * (1 - age)))
    bars = 80
    for i in range(bars):                                     # the equaliser ring
        a = math.tau * i / bars + t * 0.15
        amp = abs(math.sin(t * 2.3 + i * 0.35) * math.cos(t * 1.1 - i * 0.17)
                  + 0.4 * math.sin(t * 3.7 + i * 0.8)) / 1.4
        amp = min(1.0, 0.12 + amp)
        inner, outer = base * 1.05, base * 1.05 + R * 0.5 * amp
        c.create_line(cx + math.cos(a) * inner, cy + math.sin(a) * inner,
                      cx + math.cos(a) * outer, cy + math.sin(a) * outer,
                      fill=K(0.35 + 0.65 * amp), width=3, capstyle="round")
    c.circle(cx, cy, base, fill=K(0.12), outline=K(0.8), width=2)
    m = base * 0.5                                            # a microphone
    c.create_line(cx, cy - m * 0.55, cx, cy + m * 0.05, fill=K(1.0), width=m * 0.62,
                  capstyle="round")
    c.create_arc(cx - m * 0.62, cy - m * 0.5, cx + m * 0.62, cy + m * 0.62, start=200,
                 extent=140, style="arc", outline=K(1.0), width=3)
    c.create_line(cx, cy + m * 0.62, cx, cy + m * 0.9, fill=K(1.0), width=3)
    c.create_line(cx - m * 0.3, cy + m * 0.9, cx + m * 0.3, cy + m * 0.9, fill=K(1.0), width=3)


def _gear(c, x, y, R, teeth, angle, fill, edge, hole):
    K = c.K
    step = math.tau / teeth
    pts = []
    for i in range(teeth):
        a = angle + i * step
        for off, rad in ((-0.32, 0.8), (-0.17, 1.0), (0.17, 1.0), (0.32, 0.8)):
            pts += [x + math.cos(a + off * step * 1.6) * R * rad,
                    y + math.sin(a + off * step * 1.6) * R * rad]
    c.create_polygon(*pts, fill=fill, outline=edge, width=2)
    c.circle(x, y, R * 0.6, outline=K(0.35))
    for k in range(6):
        a = angle + k * math.tau / 6
        c.create_line(x + math.cos(a) * R * 0.22, y + math.sin(a) * R * 0.22,
                      x + math.cos(a) * R * 0.6, y + math.sin(a) * R * 0.6,
                      fill=K(0.45), width=2)
    c.circle(x, y, R * 0.2, fill=hole, outline=edge, width=2)


def _gears(c, w, h, t):
    K = c.K
    cx, cy = w / 2, h / 2
    RA = min(w * 0.30, h * 0.20)
    ax, ay = cx - RA * 0.5, cy - RA * 0.55
    RB, RC = RA * 0.6, RA * 0.42
    bx = ax + (RA + RB) * 0.93 * math.cos(math.radians(55))
    by = ay + (RA + RB) * 0.93 * math.sin(math.radians(55))
    cxx = bx + (RB + RC) * 0.93 * math.cos(math.radians(118))
    cyy = by + (RB + RC) * 0.93 * math.sin(math.radians(118))
    _glow(c, cx, cy, RA * 1.2, 0.008)
    turn = t * 0.5
    _gear(c, ax, ay, RA, 20, turn, K(0.16), K(0.9), c.bg)
    _gear(c, bx, by, RB, 12, -turn * 20 / 12 + math.pi / 12, K(0.22), K(0.75), c.bg)
    _gear(c, cxx, cyy, RC, 8, turn * 20 / 8 + math.pi / 8, K(0.12), K(0.55), c.bg)


KINDS = {"globe": _globe, "network": _network, "disk": _disk, "galaxy": _galaxy_scene,
         "chip": _chip, "radar": _radar, "tiles": _tiles, "power": _power,
         "voice": _voice, "gears": _gears}
