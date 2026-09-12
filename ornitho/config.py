"""Wing configuration: a dataclass built from the CONFIG dict at the top of wingtip.py."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

from .sections import Planform


@dataclass
class Hole:
    name: str
    x_pct: float  # chordwise centre, % of root chord from the LE
    d_mm: float  # hole diameter
    z_pct: float | None = None  # vertical centre, % of root chord from the chord line; None = camber line

    @classmethod
    def from_any(cls, h) -> Hole:
        if isinstance(h, Hole):
            return h
        if isinstance(h, dict):
            return cls(**h)
        # tuple/list: (name, x_pct, d_mm[, z_pct]) or (x_pct, z_pct, d_mm) as in the original brief
        if len(h) == 3 and not isinstance(h[0], str):
            x, z, d = h
            return cls(name=f"h{x:g}", x_pct=x, z_pct=z, d_mm=d)
        return cls(*h)


@dataclass
class WingConfig:
    airfoil: str = "s1223"  # UIUC name (fetched + cached) or a path to a .dat file
    root_chord_mm: float = 165.0
    tip_chord_mm: float = 80.0
    span_mm: float = 270.0
    le_sweep_deg: float = 15.0
    washout_deg: float = 8.0  # nose-down twist at the tip, linear from root
    dihedral_deg: float = 0.0
    wall_thickness_mm: float = 2.5
    te_truncate_pct: float = 1.0
    gurney_flap_pct: float = 0.0  # tab height, % chord (0 = off)
    gurney_thickness_mm: float = 1.2  # tab chordwise thickness
    mount_holes: list = field(
        default_factory=lambda: [Hole("fwd", 18.0, 4.2), Hole("mid", 40.0, 4.2), Hole("aft", 65.0, 4.2)]
    )
    hole_depth_mm: float = 15.0
    boss_wall_mm: float | None = None  # boss radius = hole r + this (clipped by the skin); None = wall_thickness_mm
    hole_min_wall_mm: float = 1.0  # VALIDATED minimum material between hole edge and outer skin
    root_solid_mm: float = 0.0  # solid block at the root (0 = open root face)
    n_per_surface: int = 80
    n_inner: int = 60
    density_g_cm3: float = 1.20  # TPU 85A
    wall_table_mm: list = field(default_factory=lambda: [1.2, 1.6, 2.0, 2.5, 3.0])
    target_mass_g: float = 110.0

    def __post_init__(self):
        self.mount_holes = [Hole.from_any(h) for h in self.mount_holes]
        if self.boss_wall_mm is None:
            self.boss_wall_mm = self.wall_thickness_mm
        if not 0 < self.tip_chord_mm <= self.root_chord_mm:
            raise ValueError("tip_chord_mm must be in (0, root_chord_mm]")
        if self.span_mm <= 0 or self.wall_thickness_mm <= 0:
            raise ValueError("span_mm and wall_thickness_mm must be positive")
        if self.te_truncate_pct < 0 or self.te_truncate_pct > 10:
            raise ValueError("te_truncate_pct out of range")

    @classmethod
    def from_dict(cls, d: dict) -> WingConfig:
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise KeyError(f"unknown config key(s): {sorted(unknown)}; known: {sorted(known)}")
        return cls(**d)

    def planform(self) -> Planform:
        return Planform(
            self.root_chord_mm, self.tip_chord_mm, self.span_mm, self.le_sweep_deg, self.washout_deg, self.dihedral_deg
        )

    def airfoil_path(self) -> Path | str:
        p = Path(self.airfoil)
        return p if p.suffix == ".dat" or p.exists() else self.airfoil

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["mount_holes"] = [vars(h) for h in self.mount_holes]
        return d
