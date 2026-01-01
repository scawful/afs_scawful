"""Dashboard for AFS training status.

Provides a unified view of all training runs, costs, and system status.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .cost_tracker import VultrCostTracker, InstanceCost
from .budget import BudgetEnforcer, BudgetStatus


@dataclass
class TrainingStatus:
    """Status of a training instance."""

    instance_name: str
    status: str  # running, paused, completed, failed, idle
    model: str
    current_step: int
    total_steps: int
    eta: Optional[str]
    gpu_util: float
    gpu_memory: str
    cost_so_far: float
    hours_running: float
    last_checkpoint: Optional[str]


def get_remote_training_status(instance_ip: str) -> Optional[dict]:
    """Get training status from remote instance."""
    try:
        # Try to get status via SSH
        result = subprocess.run(
            [
                "ssh",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                f"root@{instance_ip}",
                "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null; "
                "pgrep -f 'python.*train' >/dev/null && echo 'TRAINING' || echo 'IDLE'; "
                "ls -t /opt/training/models/*/checkpoint-* 2>/dev/null | head -1 || echo 'NONE'"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            gpu_info = lines[0].split(",") if lines else ["0", "0", "0"]
            status = lines[1] if len(lines) > 1 else "UNKNOWN"
            checkpoint = lines[2] if len(lines) > 2 else "NONE"

            return {
                "gpu_util": float(gpu_info[0].strip().replace(" %", "")),
                "gpu_memory_used": gpu_info[1].strip() if len(gpu_info) > 1 else "0",
                "gpu_memory_total": gpu_info[2].strip() if len(gpu_info) > 2 else "0",
                "training_status": status,
                "last_checkpoint": checkpoint if checkpoint != "NONE" else None,
            }
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass

    return None


def render_dashboard(
    costs: list[InstanceCost],
    budget_status: Optional[BudgetStatus] = None,
) -> str:
    """Render ASCII dashboard."""
    now = datetime.now()

    lines = [
        "=" * 70,
        f"{'AFS Training Dashboard':^70}",
        f"{'Updated: ' + now.strftime('%Y-%m-%d %H:%M:%S'):^70}",
        "=" * 70,
        "",
    ]

    # Budget status
    if budget_status:
        status_emoji = {
            "ok": "[OK]",
            "warning": "[WARN]",
            "critical": "[CRIT]",
            "exceeded": "[!!!!]",
        }.get(budget_status.status, "[?]")

        lines.extend([
            f"Budget: ${budget_status.daily_cost:.2f} / $100.00 "
            f"({budget_status.daily_percent:.0f}%) {status_emoji}",
            "",
        ])

    # Instances
    if not costs:
        lines.append("No active training instances.")
        lines.append("")
    else:
        lines.append(f"Active Instances: {len(costs)}")
        lines.append("-" * 70)

        for cost in costs:
            # Status indicator
            status_indicator = {
                "active": "[RUN]",
                "pending": "[...]",
                "stopped": "[OFF]",
            }.get(cost.status, "[???]")

            lines.extend([
                "",
                f"  {cost.instance_name:20} {status_indicator}",
                f"    Region:  {cost.region:10} Plan: {cost.plan}",
                f"    Runtime: {cost.hours_running:.1f}h @ ${cost.hourly_rate:.2f}/h",
                f"    Cost:    ${cost.total_cost:.2f}",
            ])

        lines.append("")
        lines.append("-" * 70)
        lines.append(f"Total Cost: ${sum(c.total_cost for c in costs):.2f}")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def render_compact_status(costs: list[InstanceCost]) -> str:
    """Render compact single-line status."""
    if not costs:
        return "No active instances"

    total_cost = sum(c.total_cost for c in costs)
    instance_summary = ", ".join(
        f"{c.instance_name}(${c.total_cost:.2f})"
        for c in costs
    )

    return f"Total: ${total_cost:.2f} | {instance_summary}"


class Dashboard:
    """Dashboard controller."""

    def __init__(self):
        self.tracker = VultrCostTracker()
        self.enforcer = BudgetEnforcer(tracker=self.tracker)

    def get_status(self) -> tuple[list[InstanceCost], BudgetStatus]:
        """Get current dashboard data."""
        costs = self.tracker.get_instance_costs()
        budget = self.enforcer.check_budget()
        return costs, budget

    def render(self, compact: bool = False) -> str:
        """Render the dashboard."""
        costs, budget = self.get_status()

        if compact:
            return render_compact_status(costs)
        else:
            return render_dashboard(costs, budget)

    def watch(self, interval: int = 30) -> None:
        """Continuously display dashboard with updates."""
        import time

        try:
            while True:
                # Clear screen
                print("\033[2J\033[H", end="")
                print(self.render())
                print(f"\nRefreshing in {interval}s... (Ctrl+C to exit)")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nExiting dashboard.")


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        command = "show"
    else:
        command = sys.argv[1]

    try:
        dashboard = Dashboard()

        if command == "show":
            print(dashboard.render())

        elif command == "compact":
            print(dashboard.render(compact=True))

        elif command == "watch":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            dashboard.watch(interval=interval)

        elif command == "json":
            import json
            costs, budget = dashboard.get_status()
            output = {
                "instances": [c.to_dict() for c in costs],
                "budget": {
                    "daily_cost": budget.daily_cost,
                    "daily_percent": budget.daily_percent,
                    "status": budget.status,
                },
                "timestamp": datetime.now().isoformat(),
            }
            print(json.dumps(output, indent=2))

        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m afs_scawful.dashboard [show|compact|watch|json]")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
