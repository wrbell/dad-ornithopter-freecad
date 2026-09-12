"""Airfoil coordinate loading, normalisation and pre-processing.

Pure numpy. Handles Selig (TE -> upper -> LE -> lower -> TE), Lednicer
(two LE -> TE arcs with or without a count line) and SolidWorks-style
3-column exports, in any start point / direction / rotation.

All public geometry is at *unit chord*: LE at (0, 0), nominal TE at (1, 0).
"""
from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "airfoils"
UIUC_URL = "https://m-selig.ae.illinois.edu/ads/coord/{name}.dat"


# --------------------------------------------------------------------------- #
# Fetch / parse
# --------------------------------------------------------------------------- #
def fetch(name: str = "s1223", data_dir: Path = DATA_DIR) -> Path:
    """Return the cached .dat path, downloading from UIUC if missing."""
    path = Path(data_dir) / f"{name}.dat"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(UIUC_URL.format(name=name), path)
    return path


def _numeric_rows(text: str) -> list[list[float]]:
    """Leading float tokens of every line that has at least two of them."""
    rows = []
    for line in text.splitlines():
        vals = []
        for tok in re.split(r"[\s,;]+", line.strip()):
            if not tok:
                continue
            try:
                vals.append(float(tok))
            except ValueError:
                break
        if len(vals) >= 2:
            rows.append(vals)
    return rows


def parse_dat(path: str | Path) -> np.ndarray:
    """Parse a coordinate file into a single closed loop (N, 2), unnormalised.

    Loop order is TE -> one surface -> LE -> other surface -> TE (direction and
    starting surface are NOT guaranteed; see normalize()).
    """
    rows = _numeric_rows(Path(path).read_text())
    if len(rows) < 6:
        raise ValueError(f"{path}: fewer than 6 coordinate rows found")

    ncol = min(len(r) for r in rows)
    arr = np.array([r[:ncol] for r in rows], dtype=float)
    if ncol >= 3:
        # SolidWorks XYZ export: keep the two columns that actually vary.
        var = arr.var(axis=0)
        keep = sorted(np.argsort(var)[-2:])
        arr = arr[:, keep]
    arr = arr[:, :2]

    first = arr[0]
    is_count_line = (
        np.all(first > 1.0)
        and np.all(np.abs(first - np.round(first)) < 1e-9)
    )
    if is_count_line:  # Lednicer with count line
        n_u, n_l = int(round(first[0])), int(round(first[1]))
        pts = arr[1:]
        if len(pts) < n_u + n_l:
            raise ValueError(f"{path}: Lednicer header says {n_u}+{n_l} points, found {len(pts)}")
        upper = pts[:n_u]          # LE -> TE
        lower = pts[n_u:n_u + n_l]  # LE -> TE
        return _arcs_to_loop(upper, lower)

    # Lednicer without count line: two LE->TE arcs -> a big jump in x mid-file.
    dx = np.diff(arr[:, 0])
    jumps = np.where(np.abs(dx) > 0.5 * np.ptp(arr[:, 0]))[0]
    if len(jumps) == 1:
        k = jumps[0] + 1
        return _arcs_to_loop(arr[:k], arr[k:])

    return arr  # Selig-style loop


def _arcs_to_loop(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Two LE->TE arcs -> TE -> a(rev) -> LE -> b -> TE, dropping a duplicated LE."""
    if np.allclose(a[0], b[0]):
        b = b[1:]
    return np.vstack([a[::-1], b])


# --------------------------------------------------------------------------- #
# Normalise
# --------------------------------------------------------------------------- #
def _dedupe(p: np.ndarray, tol: float) -> np.ndarray:
    keep = [0]
    for i in range(1, len(p)):
        if np.linalg.norm(p[i] - p[keep[-1]]) > tol:
            keep.append(i)
    p = p[keep]
    if len(p) > 1 and np.linalg.norm(p[0] - p[-1]) <= tol:
        p = p[:-1]
    return p


@dataclass
class Frame:
    """How the input coordinates were brought to unit chord."""
    mode: str            # "native" | "scaled" | "refit"
    scale: float         # divisor applied to the input units
    rotation_deg: float  # rotation applied (0 unless refit)
    shift: tuple[float, float]  # translation applied in INPUT units (0 unless refit)
    blunt_te: bool

    def describe(self) -> str:
        if self.mode == "native":
            return "native frame kept (LE at x=0, TE at (1,0))"
        if self.mode == "scaled":
            return f"scaled by 1/{self.scale:.6g} (input units -> unit chord), no rotation"
        return (f"re-fitted: shift ({self.shift[0]:.4g}, {self.shift[1]:.4g}), "
                f"rotation {self.rotation_deg:+.3f} deg, scale 1/{self.scale:.6g}")


def normalize(loop: np.ndarray) -> tuple[np.ndarray, np.ndarray, Frame]:
    """Return (upper, lower, frame), each surface LE->TE at unit chord.

    Frame policy (matters because the root section must match a rib cut from the
    same file):
      * native: TE already at (1,0) and nose at x~0  -> coordinates untouched.
      * scaled: TE on the x-axis and nose at x~0 but chord != 1 (e.g. mm export)
                -> divide by the TE x only.
      * refit : anything else (rotated / offset) -> LE to origin, TE mid to (1,0).
    Makes no assumption about the loop's start index or direction. A blunt TE
    (two distinct TE vertices joined by a cross-chord face) is preserved.
    """
    p = np.asarray(loop, dtype=float)
    scale0 = np.ptp(p, axis=0).max()
    p = _dedupe(p, 1e-7 * scale0)
    n = len(p)

    # Chord = diameter of the point set.
    d = np.linalg.norm(p[:, None, :] - p[None, :, :], axis=-1)
    i, j = np.unravel_index(np.argmax(d), d.shape)
    chord0 = d[i, j]

    # LE is the end with the wider nose: spread of nearby points perpendicular to the chord.
    axis = (p[j] - p[i]) / chord0
    perp = np.array([-axis[1], axis[0]])

    def spread(k):
        near = p[np.linalg.norm(p - p[k], axis=1) < 0.06 * chord0]
        return np.ptp((near - p[k]) @ perp)

    i_le, i_te = (i, j) if spread(i) > spread(j) else (j, i)

    # Blunt TE? The loop segment leaving the TE vertex is a short face that runs
    # mostly ACROSS the chord (a vertical cut), not along it (a converging surface).
    te_a = i_te
    te_b = None
    best = 0.0
    for nb in ((i_te - 1) % n, (i_te + 1) % n):
        seg = p[nb] - p[i_te]
        gap = np.linalg.norm(seg)
        if 0 < gap < 0.05 * chord0:
            across = abs(seg @ perp) / gap  # sin of angle to the chord axis
            if across > 0.77 and across > best:  # > ~50 deg from the chord line
                te_b, best = nb, across

    # Roll so the loop starts at one TE vertex and ends at the other (or closes on itself).
    if te_b is None:
        loop2 = np.vstack([np.roll(p, -te_a, axis=0), p[te_a][None]])
    else:
        rolled = np.roll(p, -te_a, axis=0)
        if not np.allclose(rolled[-1], p[te_b]):
            rolled = np.vstack([rolled[:1], rolled[1:][::-1]])
        loop2 = rolled
    te_mid = 0.5 * (loop2[0] + loop2[-1])
    le = p[i_le]
    k_le = int(np.argmin(np.linalg.norm(loop2 - le, axis=1)))

    # Choose the frame transform.
    x_min = p[:, 0].min()
    tol = 2e-3
    if abs(te_mid[0] - 1.0) < tol and abs(te_mid[1]) < tol and abs(x_min) < tol:
        q = loop2.copy()
        frame = Frame("native", 1.0, 0.0, (0.0, 0.0), te_b is not None)
    elif abs(te_mid[1]) < tol * chord0 and abs(x_min) < tol * chord0:
        q = loop2 / te_mid[0]
        frame = Frame("scaled", float(te_mid[0]), 0.0, (0.0, 0.0), te_b is not None)
    else:
        ax = te_mid - le
        scale = float(np.linalg.norm(ax))
        ax = ax / scale
        R = np.array([[ax[0], ax[1]], [-ax[1], ax[0]]])  # rotates ax onto +x
        q = (loop2 - le) @ R.T / scale
        frame = Frame("refit", scale, float(np.degrees(np.arctan2(ax[1], ax[0]))),
                      (float(-le[0]), float(-le[1])), te_b is not None)

    arc1 = q[: k_le + 1][::-1]  # LE -> TE
    arc2 = q[k_le:]             # LE -> TE
    if arc1[:, 1].mean() >= arc2[:, 1].mean():
        upper, lower = arc1, arc2
    else:
        upper, lower = arc2, arc1
    return upper, lower, frame


# --------------------------------------------------------------------------- #
# Processing
# --------------------------------------------------------------------------- #
def _clip_surface(s: np.ndarray, x_cut: float) -> np.ndarray:
    """Keep the LE->TE polyline up to x_cut, interpolating the crossing."""
    x = s[:, 0]
    idx = np.where(x >= x_cut)[0]
    idx = idx[idx > 0]
    if len(idx) == 0:
        return s
    i = idx[0]
    a, b = s[i - 1], s[i]
    t = (x_cut - a[0]) / (b[0] - a[0])
    cross = a + t * (b - a)
    return np.vstack([s[:i], cross[None]])


def truncate_te(upper: np.ndarray, lower: np.ndarray, pct: float) -> tuple[np.ndarray, np.ndarray]:
    """Cut both surfaces at x = 1 - pct/100. Chord is NOT rescaled.

    pct = 0 leaves the surfaces untouched but requires an already-blunt TE.
    """
    if pct > 0:
        x_cut = 1.0 - pct / 100.0
        upper, lower = _clip_surface(upper, x_cut), _clip_surface(lower, x_cut)
    gap = np.linalg.norm(upper[-1] - lower[-1])
    if gap < 1e-5:
        raise ValueError(
            "sharp trailing edge is unsupported by the loft; set te_truncate_pct > 0"
        )
    return upper, lower


def resample(surface: np.ndarray, n: int) -> np.ndarray:
    """Cosine-spaced resample of a LE->TE polyline in normalised arc length."""
    seg = np.linalg.norm(np.diff(surface, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    s /= s[-1]
    t = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))
    return np.column_stack([np.interp(t, s, surface[:, 0]), np.interp(t, s, surface[:, 1])])


def add_gurney(lower: np.ndarray, pct: float, thickness: float, n: int) -> np.ndarray:
    """Replace the aft end of the LE->TE lower surface with a Gurney tab.

    pct: tab height in % chord (hangs DOWN from the lower TE corner).
    thickness: tab chordwise thickness in chord units.
    The lower surface is clipped at x_te - thickness and resampled to n points,
    then three sharp corners are appended, so the point count is always n + 3:
        ... -> (x_te - w, y_A) -> (x_te - w, y_A - h) -> (x_te, y_A - h)
    The closing edge (x_te, y_A - h) -> TE_upper is the tab's aft face + TE cut.
    """
    if pct <= 0:
        return lower
    h = pct / 100.0
    x_te = lower[-1, 0]
    w = thickness
    clipped = _clip_surface(lower, x_te - w)
    clipped = resample(clipped, n)
    x_a, y_a = clipped[-1]
    corners = np.array([[x_a, y_a - h], [x_te, y_a - h]])
    return np.vstack([clipped, corners])


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #
@dataclass
class Airfoil:
    name: str
    upper: np.ndarray  # (n, 2) LE -> TE, unit chord
    lower: np.ndarray  # (m, 2) LE -> TE, unit chord
    frame: Frame | None = None
    n_corners: int = 0  # trailing points of outline() that are sharp corners (Gurney tab)

    def outline(self) -> np.ndarray:
        """TE_upper -> upper -> LE -> lower -> TE_lower (open at the TE)."""
        return np.vstack([self.upper[::-1], self.lower[1:]])

    def polygon(self) -> np.ndarray:
        """Closed outline (last point == first point)."""
        o = self.outline()
        return np.vstack([o, o[:1]])

    def te_gap(self) -> float:
        u, l = self._surfaces()
        return float(np.linalg.norm(u[-1] - l[-1]))

    def x_te(self) -> float:
        return float(0.5 * (self.upper[-1, 0] + self.lower[-1, 0]))

    def _surfaces(self):
        l = self.lower[: len(self.lower) - self.n_corners] if self.n_corners else self.lower
        return self.upper, l

    def camber(self, x: float | np.ndarray) -> np.ndarray:
        """Mid-thickness y at chord fraction x (from the unit-chord LE)."""
        u, l = self._surfaces()
        yu = np.interp(x, u[:, 0], u[:, 1])
        yl = np.interp(x, l[:, 0], l[:, 1])
        return 0.5 * (yu + yl)

    def thickness(self, x: float | np.ndarray) -> np.ndarray:
        u, l = self._surfaces()
        return np.interp(x, u[:, 0], u[:, 1]) - np.interp(x, l[:, 0], l[:, 1])

    def max_thickness(self) -> tuple[float, float]:
        xs = np.linspace(0.0, self.x_te(), 400)
        t = self.thickness(xs)
        k = int(np.argmax(t))
        return float(xs[k]), float(t[k])

    def area(self) -> float:
        """Enclosed area in chord^2 (shoelace)."""
        p = self.polygon()
        x, y = p[:, 0], p[:, 1]
        return float(0.5 * abs(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1])))


def load(
    path: str | Path,
    te_truncate_pct: float = 1.0,
    n_per_surface: int = 80,
    gurney_pct: float = 0.0,
    gurney_thickness: float = 0.0,
    name: str | None = None,
) -> Airfoil:
    """Parse -> normalise -> truncate TE -> resample -> (Gurney) -> Airfoil."""
    path = Path(path)
    loop = parse_dat(path)
    upper, lower, frame = normalize(loop)
    upper, lower = truncate_te(upper, lower, te_truncate_pct)
    upper, lower = resample(upper, n_per_surface), resample(lower, n_per_surface)
    n_corners = 0
    if gurney_pct > 0:
        lower = add_gurney(lower, gurney_pct, gurney_thickness, n_per_surface)
        n_corners = 2
    return Airfoil(name or path.stem, upper, lower, frame, n_corners)
