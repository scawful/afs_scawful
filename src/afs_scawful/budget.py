"""Budget enforcement and alerting.

Monitors costs against thresholds and triggers alerts/actions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from .cost_tracker import VultrCostTracker, CostSummary
from .alerting import AlertDispatcher, Alert, AlertLevel


@dataclass
class BudgetConfig:
    """Budget threshold configuration."""

    daily_warning: float = 75.0
    daily_critical: float = 90.0
    daily_limit: float = 100.0
    monthly_warning: float = 500.0
    monthly_critical: float = 750.0

    @classmethod
    def from_toml(cls, config_path: Path) -> "BudgetConfig":
        """Load configuration from TOML file."""
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        daily = data.get("daily", {})
        monthly = data.get("monthly", {})

        return cls(
            daily_warning=daily.get("warning_threshold", 75.0),
            daily_critical=daily.get("critical_threshold", 90.0),
            daily_limit=daily.get("hard_limit", 100.0),
            monthly_warning=monthly.get("warning_threshold", 500.0),
            monthly_critical=monthly.get("critical_threshold", 750.0),
        )


@dataclass
class BudgetStatus:
    """Current budget status."""

    daily_cost: float
    daily_percent: float  # Percent of daily limit used
    status: str  # "ok", "warning", "critical", "exceeded"
    message: str


class BudgetEnforcer:
    """Enforce budget limits with alerts."""

    def __init__(
        self,
        config: Optional[BudgetConfig] = None,
        config_path: Optional[Path] = None,
        tracker: Optional[VultrCostTracker] = None,
        alerter: Optional[AlertDispatcher] = None,
    ):
        # Load config
        if config:
            self.config = config
        elif config_path:
            self.config = BudgetConfig.from_toml(config_path)
        else:
            # Try default path
            default_path = Path(__file__).parent.parent.parent / "config" / "budget.toml"
            if default_path.exists():
                self.config = BudgetConfig.from_toml(default_path)
            else:
                self.config = BudgetConfig()

        # Initialize tracker
        self.tracker = tracker or VultrCostTracker()

        # Initialize alerter
        self.alerter = alerter or AlertDispatcher()

    def check_budget(self) -> BudgetStatus:
        """Check current spending against budget limits."""
        summary = self.tracker.get_daily_summary()
        daily_cost = summary.total_cost
        daily_percent = (daily_cost / self.config.daily_limit) * 100

        # Determine status
        if daily_cost >= self.config.daily_limit:
            status = "exceeded"
            message = f"BUDGET EXCEEDED: ${daily_cost:.2f} >= ${self.config.daily_limit:.2f} limit"
        elif daily_cost >= self.config.daily_critical:
            status = "critical"
            message = f"Critical: ${daily_cost:.2f} ({daily_percent:.0f}% of daily limit)"
        elif daily_cost >= self.config.daily_warning:
            status = "warning"
            message = f"Warning: ${daily_cost:.2f} ({daily_percent:.0f}% of daily limit)"
        else:
            status = "ok"
            message = f"OK: ${daily_cost:.2f} ({daily_percent:.0f}% of daily limit)"

        return BudgetStatus(
            daily_cost=daily_cost,
            daily_percent=daily_percent,
            status=status,
            message=message,
        )

    def enforce(self, dry_run: bool = False) -> BudgetStatus:
        """Check budget and take action if needed.

        Args:
            dry_run: If True, only report without taking action

        Returns:
            BudgetStatus with current state
        """
        status = self.check_budget()

        if status.status == "exceeded":
            alert = Alert(
                level=AlertLevel.CRITICAL,
                title="Budget Limit Exceeded",
                message=status.message,
                cost=status.daily_cost,
            )
            self.alerter.send(alert)

            if not dry_run:
                # Trigger shutdown of all training instances
                self._shutdown_all_instances()

        elif status.status == "critical":
            alert = Alert(
                level=AlertLevel.CRITICAL,
                title="Budget Critical",
                message=status.message,
                cost=status.daily_cost,
            )
            self.alerter.send(alert)

        elif status.status == "warning":
            alert = Alert(
                level=AlertLevel.WARNING,
                title="Budget Warning",
                message=status.message,
                cost=status.daily_cost,
            )
            self.alerter.send(alert)

        return status

    def _shutdown_all_instances(self) -> None:
        """Trigger graceful shutdown of all training instances."""
        # Note: This would need Vultr API delete capability
        # For safety, we only alert - user must manually destroy
        print("WARNING: Budget exceeded - manual intervention required")
        print("Run: terraform destroy")


def format_budget_status(status: BudgetStatus, config: BudgetConfig) -> str:
    """Format budget status as readable text."""
    lines = [
        "=" * 50,
        "AFS Budget Status",
        "=" * 50,
        "",
        f"Daily Spending: ${status.daily_cost:.2f}",
        f"Daily Limit:    ${config.daily_limit:.2f}",
        f"Usage:          {status.daily_percent:.1f}%",
        "",
        f"Status: {status.status.upper()}",
        status.message,
        "",
        "Thresholds:",
        f"  Warning:  ${config.daily_warning:.2f}",
        f"  Critical: ${config.daily_critical:.2f}",
        f"  Limit:    ${config.daily_limit:.2f}",
    ]
    return "\n".join(lines)


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m afs_scawful.budget <check|enforce|status>")
        sys.exit(1)

    command = sys.argv[1]

    try:
        enforcer = BudgetEnforcer()

        if command == "check":
            status = enforcer.check_budget()
            print(format_budget_status(status, enforcer.config))

        elif command == "enforce":
            dry_run = "--dry-run" in sys.argv
            status = enforcer.enforce(dry_run=dry_run)
            print(format_budget_status(status, enforcer.config))
            if status.status == "exceeded":
                sys.exit(2)
            elif status.status == "critical":
                sys.exit(1)

        elif command == "status":
            status = enforcer.check_budget()
            print(f"{status.status}: {status.message}")

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
