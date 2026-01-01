"""Real-time cost tracking using Vultr API.

Provides cost monitoring, budget enforcement, and historical tracking.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class InstanceCost:
    """Cost information for a single instance."""

    instance_id: str
    instance_name: str
    label: str
    region: str
    plan: str
    hourly_rate: float
    hours_running: float
    total_cost: float
    created_at: datetime
    status: str

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CostSummary:
    """Summary of costs across all instances."""

    date: str
    instances: int
    total_cost: float
    breakdown: list[dict]
    timestamp: datetime


class VultrCostTracker:
    """Track costs using Vultr API."""

    API_BASE = "https://api.vultr.com/v2"

    # Vultr GPU plan pricing (as of Jan 2025)
    # These are approximate - actual pricing may vary
    PLAN_HOURLY_RATES = {
        "vcg-a100-1c-2g-4vram": 0.62,      # A100 4GB
        "vcg-a100-3c-30g-20vram": 1.29,    # A100 20GB
        "vcg-a100-6c-60g-40vram": 2.50,    # A100 40GB
        "vcg-a100-12c-120g-80vram": 4.30,  # A100 80GB
        "vcg-a100-24c-240g-160vram": 8.60, # A100 160GB
        "vcg-l40s-8c-90g-48vram": 1.54,    # L40S 48GB
        "vcg-l40s-16c-180g-96vram": 3.08,  # L40S 96GB
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from argument or environment."""
        self.api_key = api_key or os.environ.get("VULTR_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Vultr API key required. Set VULTR_API_KEY environment variable."
            )

    def _api_get(self, endpoint: str) -> dict:
        """Make GET request to Vultr API."""
        url = f"{self.API_BASE}{endpoint}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Vultr API error {e.code}: {error_body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}") from e

    def get_hourly_rate(self, plan: str) -> float:
        """Get hourly rate for a plan."""
        if plan in self.PLAN_HOURLY_RATES:
            return self.PLAN_HOURLY_RATES[plan]

        # Fallback: estimate from monthly cost if available
        # Most GPU plans are ~$930/month for A100-20GB
        return 1.29  # Default to A100-20GB rate

    def get_all_instances(self) -> list[dict]:
        """Get all Vultr instances."""
        response = self._api_get("/instances")
        return response.get("instances", [])

    def get_training_instances(self) -> list[dict]:
        """Get instances with 'afs-training' in label."""
        instances = self.get_all_instances()
        return [
            inst for inst in instances
            if "afs-training" in inst.get("label", "").lower()
            or "afs" in inst.get("tags", [])
        ]

    def get_instance_costs(self) -> list[InstanceCost]:
        """Get cost breakdown for all training instances."""
        instances = self.get_training_instances()
        costs = []

        now = datetime.now(timezone.utc)

        for inst in instances:
            # Parse creation time
            created_str = inst.get("date_created", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except ValueError:
                created = now

            # Calculate hours running
            hours = (now - created).total_seconds() / 3600

            # Get hourly rate
            plan = inst.get("plan", "")
            hourly_rate = self.get_hourly_rate(plan)

            # Calculate total cost
            total_cost = hours * hourly_rate

            costs.append(
                InstanceCost(
                    instance_id=inst.get("id", ""),
                    instance_name=inst.get("label", "").replace("afs-training-", ""),
                    label=inst.get("label", ""),
                    region=inst.get("region", ""),
                    plan=plan,
                    hourly_rate=hourly_rate,
                    hours_running=round(hours, 2),
                    total_cost=round(total_cost, 2),
                    created_at=created,
                    status=inst.get("status", "unknown"),
                )
            )

        return costs

    def get_daily_summary(self) -> CostSummary:
        """Get today's total cost across all training instances."""
        costs = self.get_instance_costs()
        return CostSummary(
            date=datetime.now().strftime("%Y-%m-%d"),
            instances=len(costs),
            total_cost=round(sum(c.total_cost for c in costs), 2),
            breakdown=[
                {
                    "name": c.instance_name,
                    "cost": c.total_cost,
                    "hours": c.hours_running,
                    "rate": c.hourly_rate,
                    "status": c.status,
                }
                for c in costs
            ],
            timestamp=datetime.now(timezone.utc),
        )

    def get_account_balance(self) -> dict:
        """Get account balance information."""
        response = self._api_get("/account")
        account = response.get("account", {})
        return {
            "balance": float(account.get("balance", 0)),
            "pending_charges": float(account.get("pending_charges", 0)),
            "last_payment_date": account.get("last_payment_date", ""),
            "last_payment_amount": float(account.get("last_payment_amount", 0)),
        }


def format_cost_report(summary: CostSummary) -> str:
    """Format cost summary as a readable report."""
    lines = [
        "=" * 60,
        f"AFS Training Cost Report - {summary.date}",
        "=" * 60,
        "",
        f"Active Instances: {summary.instances}",
        f"Total Cost Today: ${summary.total_cost:.2f}",
        "",
    ]

    if summary.breakdown:
        lines.append("Breakdown:")
        lines.append("-" * 40)
        for item in summary.breakdown:
            lines.append(
                f"  {item['name']:20} ${item['cost']:7.2f} "
                f"({item['hours']:.1f}h @ ${item['rate']:.2f}/h) [{item['status']}]"
            )
    else:
        lines.append("No active training instances.")

    lines.append("")
    lines.append(f"Report generated: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    return "\n".join(lines)


# CLI interface
if __name__ == "__main__":
    import sys

    try:
        tracker = VultrCostTracker()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python -m afs_scawful.cost_tracker <status|daily|balance|json>")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "status":
            costs = tracker.get_instance_costs()
            if not costs:
                print("No active training instances.")
            else:
                for cost in costs:
                    print(
                        f"{cost.instance_name}: ${cost.total_cost:.2f} "
                        f"({cost.hours_running:.1f}h @ ${cost.hourly_rate:.2f}/h) [{cost.status}]"
                    )
                print(f"\nTotal: ${sum(c.total_cost for c in costs):.2f}")

        elif command == "daily":
            summary = tracker.get_daily_summary()
            print(format_cost_report(summary))

        elif command == "balance":
            balance = tracker.get_account_balance()
            print(f"Balance: ${balance['balance']:.2f}")
            print(f"Pending charges: ${balance['pending_charges']:.2f}")
            if balance['last_payment_date']:
                print(f"Last payment: ${balance['last_payment_amount']:.2f} on {balance['last_payment_date']}")

        elif command == "json":
            summary = tracker.get_daily_summary()
            output = {
                "date": summary.date,
                "instances": summary.instances,
                "total_cost": summary.total_cost,
                "breakdown": summary.breakdown,
                "timestamp": summary.timestamp.isoformat(),
            }
            print(json.dumps(output, indent=2))

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
