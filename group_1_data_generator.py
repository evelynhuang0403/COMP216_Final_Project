import math
import random
from random import uniform, choice

class DataGenerator:
    # simple signal generator with optional wild/corrupt injections
    def __init__(self, base=19.5, amplitude=2.5, frequency=0.08, noise=0.8,
                 wild_rate=0.02, corrupt_rate=0.02):
        self.base = base
        self.amplitude = amplitude
        self.frequency = frequency
        self.noise = noise

        # internal counter for the waveform
        self._x = 0

        # toggles
        self.allow_wild = False
        self.allow_corrupt = False

        # injection probabilities (per sample)
        self.wild_rate = float(wild_rate)
        self.corrupt_rate = float(corrupt_rate)

    # compute base + sine + noise
    def _normalized_value(self):
        wave = self.amplitude * math.sin(self.frequency * self._x)
        jitter = uniform(-self.noise, self.noise)
        return round(self.base + wave + jitter, 2)

    # produce a value for the next tick
    def get_value(self):
        self._x += 1

        # corrupt takes precedence, then wild (only if enabled)
        roll = random.random()
        if self.allow_corrupt and roll < self.corrupt_rate:
            return self.get_corrupt_data()
        if self.allow_wild and roll < (self.corrupt_rate + self.wild_rate):
            return self.get_wild_value()

        return self._normalized_value()

    # unrealistic spikes far outside normal range
    def get_wild_value(self):
        return round(choice([
            uniform(-50, -1),   # too cold
            uniform(51, 100),   # too hot
        ]), 2)

    # intentionally invalid/erroneous payloads
    def get_corrupt_data(self):
        return choice([
            "SENSOR_FAULT",
            "ERROR",
            None,
            "NaN"
        ])

    # toggle wild injection
    def set_wild_enabled(self, status: bool):
        self.allow_wild = bool(status)

    # toggle corrupt injection
    def set_corrupt_enabled(self, status: bool):
        self.allow_corrupt = bool(status)

    # optionally tune injection rates (0.0 .. 1.0); safe to ignore if not needed
    def set_injection_rates(self, wild_rate=None, corrupt_rate=None):
        if wild_rate is not None:
            self.wild_rate = max(0.0, min(1.0, float(wild_rate)))
        if corrupt_rate is not None:
            self.corrupt_rate = max(0.0, min(1.0, float(corrupt_rate)))

    # update signal parameters; any None means "leave as-is"
    def update_parameters(self, base=None, amplitude=None, frequency=None, noise=None):
        if base is not None:
            self.base = base
        if amplitude is not None:
            self.amplitude = amplitude
        if frequency is not None:
            self.frequency = frequency
        if noise is not None:
            self.noise = noise


