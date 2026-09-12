"""Analytic NACA 4-digit generator + .dat writers in every format we must accept."""
from __future__ import annotations

import numpy as np
import pytest


def naca4(code: str = "2412", n: int = 60, closed_te: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Return (upper, lower) LE->TE at unit chord for a NACA 4-digit section."""
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    beta = np.linspace(0, np.pi, n)
    x = 0.5 * (1 - np.cos(beta))
    a4 = -0.1036 if closed_te else -0.1015
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 + a4 * x**4)
    if m == 0:
        yc = np.zeros_like(x)
        dyc = np.zeros_like(x)
    else:
        yc = np.where(x < p, m / p**2 * (2 * p * x - x**2), m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x**2))
        dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    th = np.arctan(dyc)
    upper = np.column_stack([x - yt * np.sin(th), yc + yt * np.cos(th)])
    lower = np.column_stack([x + yt * np.sin(th), yc - yt * np.cos(th)])
    return upper, lower


def selig_loop(upper: np.ndarray, lower: np.ndarray) -> np.ndarray:
    """TE -> upper -> LE -> lower -> TE (LE shared once)."""
    return np.vstack([upper[::-1], lower[1:]])


def fmt(rows, ncol=2, sep="  ", eol="\n"):
    out = []
    for r in rows:
        r = list(r) + [0.0] * (ncol - len(r))
        out.append(sep.join(f"{v: .6f}" for v in r[:ncol]))
    return eol.join(out) + eol


@pytest.fixture
def naca2412():
    return naca4("2412")


@pytest.fixture
def dat_writer(tmp_path):
    """Write (upper, lower) in a named format, return the path."""

    def _write(upper, lower, fmt_name: str, name="naca2412") -> str:
        loop = selig_loop(upper, lower)
        if fmt_name == "selig":
            text = "NACA 2412\n" + fmt(loop)
        elif fmt_name == "selig_reversed":
            text = "NACA 2412\n" + fmt(loop[::-1])
        elif fmt_name == "selig_le_start":
            k = len(upper) - 1  # index of LE in the loop
            text = "NACA 2412\n" + fmt(np.roll(loop, -k, axis=0))
        elif fmt_name == "selig_closed":
            text = "NACA 2412\n" + fmt(np.vstack([loop, loop[:1]]))
        elif fmt_name == "lednicer":
            text = ("NACA 2412 AIRFOIL\n\n" + f"{len(upper):5.1f}   {len(lower):5.1f}\n\n"
                    + fmt(upper) + "\n" + fmt(lower))
        elif fmt_name == "lednicer_nocount":
            text = "NACA 2412\n" + fmt(upper) + fmt(lower)
        elif fmt_name == "three_col":
            text = fmt(np.column_stack([loop, np.zeros(len(loop))]), ncol=3, sep=",")
        elif fmt_name == "three_col_mm":
            text = "x y z\n" + fmt(np.column_stack([loop * 165.0, np.zeros(len(loop))]), ncol=3, sep="\t")
        elif fmt_name == "crlf_blank":
            text = "NACA 2412\r\n\r\n" + fmt(loop, eol="\r\n") + "\r\n"
        elif fmt_name == "rotated":
            th = np.radians(3.0)
            R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
            text = "rotated\n" + fmt((loop @ R.T) * 2.5 + np.array([10.0, -4.0]))
        else:
            raise ValueError(fmt_name)
        path = tmp_path / f"{name}_{fmt_name}.dat"
        path.write_text(text)
        return str(path)

    return _write
