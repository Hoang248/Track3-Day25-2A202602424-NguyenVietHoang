"""Reproduce the rubric's ablations without changing final code/config.

All provider calls are offline simulator calls. The unsafe tool-routing
variant is deliberately confined to this experiment, never the factory.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameday_lab.client import ResilientClient
from gameday_lab.factory import build_client
from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import evaluate_checks, run_scenario


class UnfilteredExperimentClient(ResilientClient):
    """Negative control requested by report section 3; tools may be misrouted."""

    def ladder(self, task: str) -> list[str]:
        return list(self.order)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=25)
    ap.add_argument("--out", type=Path, default=ROOT / "reports/experiments")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / "configs/gameday.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tapes = ROOT / "configs/scenarios.yaml"
    cache_tapes = ROOT / "configs/scenarios_cache.yaml"
    cfg = load_config(config_path, tapes)
    cache_cfg = load_config(config_path, cache_tapes)
    disabled_budget = {"retry_budget_ratio": 100, "retry_budget_max_tokens": 1.0e9,
                       "retry_budget_min_per_s": 1.0e6}
    broken_breaker = {"max_attempts_per_provider": 5,
                      "breaker": {**cfg.client["breaker"], "min_calls": 1000000000}}
    experiments = [
        ("control", {}, {}, list(cfg.scenarios), False),
        ("broken_breaker_budget", broken_breaker, {}, ["G2_overload_storm", "G3_brownout"], False),
        ("broken_breaker_no_budget", {**broken_breaker, **disabled_budget}, {},
         ["G2_overload_storm", "G3_brownout"], False),
        ("healthy_breaker_no_budget", disabled_budget, {}, ["G2_overload_storm", "G3_brownout"], False),
        ("timeout_30", {"attempt_timeout_s": 30}, {}, ["G6_provider_outage", "G4_slow_region"], False),
        ("unfiltered_tools", {}, {}, ["G6_provider_outage"], True),
        ("cache_control", {}, {}, ["C1_faq_outage"], False),
        ("cache_threshold_080", {}, {"similarity_threshold": 0.80}, ["C1_faq_outage"], False),
        ("cache_threshold_097", {}, {"similarity_threshold": 0.97}, ["C1_faq_outage"], False),
        ("cache_ttl_60", {}, {"ttl_s": 60}, ["C1_faq_outage"], False),
        ("cache_ttl_300", {}, {"ttl_s": 300}, ["C1_faq_outage"], False),
        ("cache_no_stale", {}, {"max_stale_s": 0}, ["C1_faq_outage"], False),
        ("cache_starter", {}, {"similarity_threshold": 0.80, "ttl_s": 600, "max_stale_s": 0},
         ["C1_faq_outage"], False),
    ]
    runs = {}
    for name, client_changes, cache_changes, scenarios, unfiltered in experiments:
        is_cache = name.startswith("cache_")
        base = cache_cfg if is_cache else cfg
        variant = replace(base, client={**copy.deepcopy(base.client), **client_changes},
                          cache={**base.cache, **cache_changes})
        snapshot = {**raw, "client": variant.client, "cache": variant.cache}
        (args.out / f"{name}.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False), encoding="utf-8")
        rows = {}
        for scenario in scenarios:
            if unfiltered:
                client = UnfilteredExperimentClient(variant.provider_infos(), variant.fallback_order,
                                                    variant.client, seed=1)
            else:
                client = build_client("cached" if is_cache else "resilient", variant, seed=1)
            metrics = run_scenario(variant, scenario, client, args.seed).metrics()
            metrics["checks"] = evaluate_checks(metrics, variant.scenarios[scenario].checks)
            metrics["pass"] = all(metrics["checks"].values())
            rows[scenario] = metrics
            print(f"{name:27s} {scenario:27s} avail={metrics['availability']} "
                  f"ampl={metrics['amplification']} retry={metrics['retry_ratio']} pass={metrics['pass']}")
        runs[name] = {"config": f"{name}.yaml", "unsafe_tool_routing": unfiltered, "metrics": rows}
    input_paths = [Path(__file__).resolve(), config_path, tapes, cache_tapes, *sorted((ROOT / "src").rglob("*.py"))]
    result = {
        "mode": "offline_simulation", "seed": args.seed, "client_rng_seed": 1,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in input_paths},
        "runs": runs,
    }
    (args.out / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
