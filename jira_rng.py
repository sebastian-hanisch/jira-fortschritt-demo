"""SplitMix64 (Vigna), reine Ganzzahl-Arithmetik: Portfolio-Konvention für allen Zufall der Demos.

`SplitMix64` ist die skalare Fassung für die Simulation; `uniform_block` liefert dieselben Zahlen vektorisiert (numpy uint64
läuft modulo 2^64 über), damit die Messreihen schnell sind und trotzdem auf jeder Plattform dieselben Zahlen liefern."""

import math

import numpy as np

_MASK = (1 << 64) - 1
_GAMMA = 0x9E3779B97F4A7C15
_M1 = 0xBF58476D1CE4E5B9
_M2 = 0x94D049BB133111EB


class SplitMix64:
    def __init__(self, seed):
        self.state = seed & _MASK

    def next(self):
        self.state = (self.state + _GAMMA) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * _M1) & _MASK
        z = ((z ^ (z >> 27)) * _M2) & _MASK
        return z ^ (z >> 31)

    def uniform(self):
        """Gleichverteilt auf [0, 1) mit 53 Bit."""
        return (self.next() >> 11) * (1.0 / (1 << 53))

    def exponential(self):
        """Exponentiell mit Mittel 1 (Inversion; 1 - u liegt in (0, 1])."""
        return -math.log(1.0 - self.uniform())


def uniform_block(seed, count):
    """Die ersten `count` Gleichverteilten des Stroms `SplitMix64(seed)`, vektorisiert (Form (count,))."""
    k = np.arange(1, count + 1, dtype=np.uint64)
    with np.errstate(over="ignore"):
        z = np.uint64(seed & _MASK) + k * np.uint64(_GAMMA)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(_M1)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(_M2)
        z = z ^ (z >> np.uint64(31))
    return (z >> np.uint64(11)).astype(np.float64) * (1.0 / (1 << 53))
