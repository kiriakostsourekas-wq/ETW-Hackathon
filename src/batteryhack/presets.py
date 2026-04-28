from __future__ import annotations

from dataclasses import dataclass

from .optimizer import BatteryParams


@dataclass(frozen=True)
class BatteryPreset:
    name: str
    power_mw: float
    capacity_mwh: float
    round_trip_efficiency: float
    min_soc_pct: float
    max_soc_pct: float
    initial_soc_pct: float
    terminal_soc_pct: float
    degradation_cost_eur_mwh: float
    max_cycles_per_day: float | None
    note: str = ""

    @property
    def duration_hours(self) -> float:
        return self.capacity_mwh / self.power_mw

    @property
    def usable_energy_mwh(self) -> float:
        return self.capacity_mwh * (self.max_soc_pct - self.min_soc_pct) / 100.0

    def to_params(self) -> BatteryParams:
        return BatteryParams(
            power_mw=self.power_mw,
            capacity_mwh=self.capacity_mwh,
            round_trip_efficiency=self.round_trip_efficiency,
            min_soc_pct=self.min_soc_pct,
            max_soc_pct=self.max_soc_pct,
            initial_soc_pct=self.initial_soc_pct,
            terminal_soc_pct=self.terminal_soc_pct,
            degradation_cost_eur_mwh=self.degradation_cost_eur_mwh,
            max_cycles_per_day=self.max_cycles_per_day,
        )


METLEN_PRESET_NAME = "METLEN-scale 330 MW / 790 MWh"
METLEN_BASE_EFFICIENCY = 0.85
METLEN_OPTIMISTIC_EFFICIENCY = 0.90
METLEN_CYCLE_SENSITIVITIES = (0.5, 1.0, 1.5)
METLEN_DEGRADATION_SENSITIVITIES = (0.0, 2.0, 5.0, 10.0, 20.0)

BATTERY_PRESETS: dict[str, BatteryPreset] = {
    METLEN_PRESET_NAME: BatteryPreset(
        name=METLEN_PRESET_NAME,
        power_mw=330.0,
        capacity_mwh=790.0,
        round_trip_efficiency=METLEN_BASE_EFFICIENCY,
        min_soc_pct=10.0,
        max_soc_pct=90.0,
        initial_soc_pct=50.0,
        terminal_soc_pct=50.0,
        degradation_cost_eur_mwh=5.0,
        max_cycles_per_day=1.0,
        note="Public METLEN/Karatzis case; degradation remains a sensitivity.",
    ),
    "10 MW / 20 MWh": BatteryPreset(
        name="10 MW / 20 MWh",
        power_mw=10.0,
        capacity_mwh=20.0,
        round_trip_efficiency=0.90,
        min_soc_pct=10.0,
        max_soc_pct=90.0,
        initial_soc_pct=50.0,
        terminal_soc_pct=50.0,
        degradation_cost_eur_mwh=4.0,
        max_cycles_per_day=None,
    ),
    "20 MW / 80 MWh": BatteryPreset(
        name="20 MW / 80 MWh",
        power_mw=20.0,
        capacity_mwh=80.0,
        round_trip_efficiency=0.90,
        min_soc_pct=10.0,
        max_soc_pct=90.0,
        initial_soc_pct=50.0,
        terminal_soc_pct=50.0,
        degradation_cost_eur_mwh=4.0,
        max_cycles_per_day=None,
    ),
    "Custom": BatteryPreset(
        name="Custom",
        power_mw=10.0,
        capacity_mwh=40.0,
        round_trip_efficiency=0.90,
        min_soc_pct=10.0,
        max_soc_pct=90.0,
        initial_soc_pct=50.0,
        terminal_soc_pct=50.0,
        degradation_cost_eur_mwh=4.0,
        max_cycles_per_day=None,
    ),
}

