"""Closed-loop causal simulator, baseline policies, hindsight oracle and metrics (DES-860 §8)."""

from horizon.sim.manoeuvre import ManoeuvreModel
from horizon.sim.metrics import MissionMetrics, mission_metrics
from horizon.sim.policies import (
    DeterministicMPCPolicy,
    HoldAtPointPolicy,
    OraclePolicy,
    Plan,
    Policy,
    best_climatological_point,
)
from horizon.sim.power import (
    DirectPowerModel,
    EnvelopePowerModel,
    FeasiblePowerModel,
    PowerModel,
)
from horizon.sim.simulator import (
    CausalityError,
    ForecastProvider,
    MissionResult,
    SimState,
    advance,
    energy_on_truth,
    energy_on_truth_ex,
    run_mission,
)

__all__ = [
    "ManoeuvreModel", "CausalityError", "DeterministicMPCPolicy", "DirectPowerModel",
    "EnvelopePowerModel",
    "FeasiblePowerModel", "ForecastProvider", "HoldAtPointPolicy", "MissionMetrics",
    "MissionResult", "SimState", "OraclePolicy", "Plan", "Policy", "PowerModel",
    "advance", "best_climatological_point", "energy_on_truth", "energy_on_truth_ex",
    "mission_metrics", "run_mission",
]
