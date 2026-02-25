#!/usr/bin/env python3
"""
dataset_audit - Training pipeline health dashboard for afs-scawful.

Usage:
  dataset_audit                  # Full report
  dataset_audit --section logs   # Just log extraction status
  dataset_audit --section data   # Just training data counts
  dataset_audit --section gaps   # Just gap/recommendation analysis
  dataset_audit --json           # Machine-readable JSON output
"""

import argparse
import json
import importlib.util
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich import box
    from rich.text import Text
    RICH = True
except ImportError:
    RICH = False

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "training_data"
EVAL_DIR = ROOT / "docs" / "eval"
HOME     = Path.home()

# ── load logprune ─────────────────────────────────────────────────────────────

def _load_logprune():
    spec = importlib.util.spec_from_file_location("logprune", Path(__file__).parent / "logprune.py")
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    return lp

# ── helpers ───────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out

def fmt_size(b: int) -> str:
    if b < 1024:       return f"{b}B"
    if b < 1024 ** 2:  return f"{b // 1024}K"
    return f"{b // 1024 ** 2}M"

def age_str(path: Path) -> str:
    if not path.exists():
        return "—"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    now   = datetime.now(timezone.utc)
    d = int((now - mtime).total_seconds() // 86400)
    if d == 0: return "today"
    if d == 1: return "1d ago"
    return f"{d}d ago"

# ── section: training data ────────────────────────────────────────────────────

DATASET_TARGETS = {
    "claude_log_pairs.jsonl":       {"target": 200, "desc": "Claude log extraction"},
    "cpp_log_pairs.jsonl":          {"target": 3000, "desc": "C++ (yaze) log pairs"},
    "anti_slop_v1.jsonl":           {"target": 200, "desc": "Ockham anti-slop pairs (barista+yaze+zelda3)"},
    "memory_muse_distill_v1.jsonl": {"target": 150, "desc": "Memory/Muse distillation"},
    "avatar_mix_v1.jsonl":          {"target": 100, "desc": "Avatar MoE mix"},
    "sibyl_v1.jsonl":               {"target": 28,  "desc": "Sibyl ADHD assistant (14 prompts×2)"},
    "lancer_v1.jsonl":              {"target": 40,  "desc": "Lancer get-unstuck (20 prompts×2)"},
    "morpheus_v1.jsonl":            {"target": 20,  "desc": "Morpheus brainstorm (10 prompts×2)"},
    "anamnesis_v1.jsonl":           {"target": 44,  "desc": "Anamnesis decision recall (22 prompts×2)"},
    "commit_diff_v1.jsonl":         {"target": 2000, "desc": "Commit msg ↔ diff pairs (free)"},
    "weaver_v1.jsonl":              {"target": 50,  "desc": "Weaver cross-project"},
    "weaver_distill_v1.jsonl":      {"target": 30,  "desc": "Weaver distillation"},
    "fs_delta_raw_v1.jsonl":        {"target": 200, "desc": "Filesystem delta"},
}

def audit_datasets() -> list[dict]:
    rows = []
    for fname, meta in DATASET_TARGETS.items():
        path  = DATA_DIR / fname
        recs  = load_jsonl(path)
        n     = len(recs)
        tgt   = meta["target"]
        pct   = int(n / tgt * 100) if tgt else 100
        size  = path.stat().st_size if path.exists() else 0
        rows.append({
            "file":    fname,
            "desc":    meta["desc"],
            "n":       n,
            "target":  tgt,
            "pct":     pct,
            "size":    size,
            "age":     age_str(path),
            "status":  "✓" if pct >= 100 else ("~" if pct >= 60 else "✗"),
        })
    # Any extra files not in targets
    for path in sorted(DATA_DIR.glob("*.jsonl")):
        if path.name not in DATASET_TARGETS:
            recs = load_jsonl(path)
            rows.append({
                "file":    path.name,
                "desc":    "—",
                "n":       len(recs),
                "target":  None,
                "pct":     None,
                "size":    path.stat().st_size,
                "age":     age_str(path),
                "status":  "?",
            })
    return rows

# ── section: log extraction ───────────────────────────────────────────────────

def audit_logs() -> dict:
    lp = _load_logprune()
    sessions = lp.load_all_sessions()
    for s in sessions:
        lp.score_session(s)

    high    = [s for s in sessions if s.quality_score >= 0.6]
    private = [s for s in sessions if s.is_private]
    near    = [s for s in sessions if 0.5 <= s.quality_score < 0.6]

    tag_counts = Counter()
    for s in high:
        tag_counts.update(s.tags)

    proj_counts = Counter(s.project_path for s in high)

    score_dist = {
        ">=0.8":   sum(1 for s in sessions if s.quality_score >= 0.8),
        "0.7-0.8": sum(1 for s in sessions if 0.7 <= s.quality_score < 0.8),
        "0.6-0.7": sum(1 for s in sessions if 0.6 <= s.quality_score < 0.7),
        "0.5-0.6": sum(1 for s in sessions if 0.5 <= s.quality_score < 0.6),
        "<0.5":    sum(1 for s in sessions if s.quality_score < 0.5),
    }

    already_extracted = load_jsonl(DATA_DIR / "claude_log_pairs.jsonl")
    extracted_sids = {r.get("_meta", {}).get("session_id") for r in already_extracted}
    new_sessions = [s for s in high if s.session_id not in extracted_sids]

    return {
        "total":      len(sessions),
        "high":       len(high),
        "private":    len(private),
        "near_miss":  len(near),
        "new_extractable": len(new_sessions),
        "score_dist": score_dist,
        "tags":       dict(tag_counts),
        "projects":   dict(proj_counts.most_common(8)),
        "top_new": [
            {
                "session_id": s.session_id,
                "turns":      len(s.turns),
                "score":      round(s.quality_score, 3),
                "tags":       s.tags,
                "project":    s.project_path,
                "preview":    next((t.content[:80] for t in s.turns if t.role == "user"), ""),
            }
            for s in sorted(new_sessions, key=lambda x: -len(x.turns))[:8]
        ],
    }

# ── section: distillation ─────────────────────────────────────────────────────

def audit_distillation() -> dict:
    prompts_file = EVAL_DIR / "memory_muse_distill_prompts_v1.jsonl"
    done_file    = DATA_DIR / "memory_muse_distill_v1.jsonl"

    if not prompts_file.exists():
        return {"error": f"Prompts file not found: {prompts_file}"}

    prompts = load_jsonl(prompts_file)
    done    = load_jsonl(done_file)

    done_fps = {d.get("instruction", "")[:100] for d in done}
    pending  = [p for p in prompts if p.get("instruction", "")[:100] not in done_fps]

    done_cats    = Counter(d.get("domain", d.get("category", "unknown")) for d in done)
    pending_cats = Counter(p.get("category", p.get("domain", "unknown")) for p in pending)

    return {
        "total_prompts": len(prompts),
        "done":          len(done),
        "pending":       len(pending),
        "pct_done":      int(len(done) / len(prompts) * 100) if prompts else 0,
        "done_by_cat":   dict(done_cats),
        "pending_by_cat": dict(pending_cats),
    }

# ── section: persona raw data ─────────────────────────────────────────────────

def audit_persona_raw() -> list[dict]:
    raw_dir = ROOT / "data" / "persona_raw"
    rows = []
    for path in sorted(raw_dir.glob("*")):
        if path.is_file():
            size  = path.stat().st_size
            lines = len(path.read_text(errors="replace").splitlines()) if size < 10_000_000 else "—"
            rows.append({"file": path.name, "size": size, "lines": lines, "age": age_str(path)})
    return rows

# ── gap analysis ──────────────────────────────────────────────────────────────

def compute_gaps(datasets: list[dict], logs: dict, distill: dict) -> list[dict]:
    gaps = []

    # New extractable sessions
    n_new = logs.get("new_extractable", 0)
    if n_new > 0:
        gaps.append({
            "priority": "HIGH",
            "action":   f"logprune extract: {n_new} new sessions available",
            "cmd":      "python3 scripts/logprune.py extract --min-score 0.6 --format chatml "
                        "--output data/training_data/claude_log_pairs.jsonl",
            "gain":     f"+{n_new} sessions → more training pairs",
        })

    # Pending distillation
    p = distill.get("pending", 0)
    if p > 0:
        gaps.append({
            "priority": "HIGH",
            "action":   f"Memory/Muse: {p} prompts pending ({distill.get('pct_done')}% done)",
            "cmd":      f"python3 scripts/distill_memory_muse.py run",
            "gain":     f"+{p} distilled samples",
        })

    # Anti-slop
    for d in datasets:
        if d["file"] == "anti_slop_v1.jsonl":
            if d["pct"] is not None and d["pct"] < 60:
                gaps.append({
                    "priority": "HIGH",
                    "action":   f"Ockham anti-slop: {d['n']}/{d['target']} pairs ({d['pct']}%)",
                    "cmd":      "python3 scripts/antislop_dataset.py generate --source barista,yaze",
                    "gain":     f"+{d['target'] - d['n']} pairs, improves code minimalism training",
                })

    # Dataset diversity: assembly dominance
    tags = logs.get("tags", {})
    total_high = logs.get("high", 1)
    asm_pct = int(tags.get("assembly", 0) / max(total_high, 1) * 100)
    swift_pct = int(tags.get("ios_macos", 0) / max(total_high, 1) * 100)
    cpp_pct = int(tags.get("cpp", 0) / max(total_high, 1) * 100)
    if asm_pct > 70:
        gaps.append({
            "priority": "MED",
            "action":   f"Data bias: {asm_pct}% assembly, {cpp_pct}% C++, {swift_pct}% iOS/macOS",
            "cmd":      "python3 scripts/logprune.py extract --project yaze "
                        "--output data/training_data/cpp_log_pairs.jsonl\n"
                        "  python3 scripts/antislop_dataset.py generate --source zelda3,yaze --max-files 70",
            "gain":     "More C++ pairs (yaze log extraction + zelda3/yaze antislop)",
        })

    # Persona completeness
    persona_targets = {"sibyl_v1.jsonl": 30, "lancer_v1.jsonl": 40,
                       "morpheus_v1.jsonl": 30, "anamnesis_v1.jsonl": 20}
    for d in datasets:
        if d["file"] in persona_targets:
            tgt = persona_targets[d["file"]]
            if d["n"] < tgt:
                name = d["file"].replace("_v1.jsonl","").capitalize()
                gaps.append({
                    "priority": "MED",
                    "action":   f"{name} persona: {d['n']}/{tgt} pairs",
                    "cmd":      f"python3 scripts/persona_dataset.py generate "
                                f"--persona {d['file'].split('_')[0]}",
                    "gain":     f"+{tgt - d['n']} persona training pairs",
                })

    return gaps

# ── rendering ─────────────────────────────────────────────────────────────────

def render_rich(datasets, logs, distill, persona_raw, gaps):
    console = Console()

    console.print()
    console.print("[bold]AFS Training Pipeline Audit[/bold]  "
                  f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
    console.print()

    # ── training data table ───────────────────────────────────────────────────
    console.print("[bold cyan]Training Data[/bold cyan]")
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="dim",
              pad_edge=False, expand=False)
    t.add_column("FILE",   max_width=38)
    t.add_column("N",      width=6,  justify="right")
    t.add_column("TARGET", width=7,  justify="right")
    t.add_column("%",      width=6,  justify="right")
    t.add_column("SIZE",   width=7,  justify="right")
    t.add_column("AGE",    width=8)
    t.add_column("ST",     width=3)

    total_records = 0
    for d in datasets:
        st_color = {"✓": "green", "~": "yellow", "✗": "red", "?": "dim"}.get(d["status"], "white")
        pct_str  = f"{d['pct']}%" if d["pct"] is not None else "—"
        tgt_str  = str(d["target"]) if d["target"] is not None else "—"
        t.add_row(
            d["file"],
            str(d["n"]),
            tgt_str,
            pct_str,
            fmt_size(d["size"]),
            d["age"],
            Text(d["status"], style=st_color),
        )
        total_records += d["n"]
    console.print(t)
    console.print(f"  [dim]Total: {total_records} records across {len(datasets)} files[/dim]")
    console.print()

    # ── log extraction ────────────────────────────────────────────────────────
    console.print("[bold cyan]Log Extraction[/bold cyan]")
    lt = Table(box=box.SIMPLE_HEAD, show_header=False, pad_edge=False, expand=False)
    lt.add_column("K", style="dim", width=22)
    lt.add_column("V")
    lt.add_row("Total sessions",      str(logs["total"]))
    lt.add_row("High quality (≥0.6)", f"[green]{logs['high']}[/green]")
    lt.add_row("Private (filtered)",  str(logs["private"]))
    lt.add_row("Near-miss (0.5-0.6)", str(logs["near_miss"]))
    lt.add_row("New (not extracted)", f"[yellow]{logs['new_extractable']}[/yellow]")
    console.print(lt)
    console.print()

    dist = logs["score_dist"]
    console.print("  [dim]Score distribution:[/dim]")
    for band, n in dist.items():
        bar = "█" * min(n, 50)
        console.print(f"  [dim]{band:>8}[/dim]  {bar} {n}")
    console.print()

    console.print("  [dim]High-quality by project:[/dim]")
    for proj, n in logs["projects"].items():
        clean = proj.replace("/Users/scawful/","~/").replace("-Users-scawful-","~/").replace("-","/")
        console.print(f"  [dim]{clean:<45}[/dim] {n}")
    console.print()

    if logs["top_new"]:
        console.print(f"  [bold]Top new sessions to extract ({len(logs['top_new'])} shown):[/bold]")
        for s in logs["top_new"]:
            proj = s["project"].replace("-Users-scawful-","~/").replace("-","/")
            console.print(f"  [dim]{s['score']:.3f}[/dim]  [cyan]{s['turns']}t[/cyan]  "
                          f"[dim]{proj}[/dim]")
            console.print(f"    [italic dim]{s['preview'][:70]}[/italic dim]")
    console.print()

    # ── distillation ──────────────────────────────────────────────────────────
    console.print("[bold cyan]Memory/Muse Distillation[/bold cyan]")
    pct_done = distill.get("pct_done", 0)
    bar = "█" * (pct_done // 5) + "░" * (20 - pct_done // 5)
    status_color = "green" if pct_done >= 90 else ("yellow" if pct_done >= 60 else "red")
    console.print(f"  [{status_color}]{bar}[/{status_color}]  "
                  f"{distill.get('done',0)}/{distill.get('total_prompts',0)}  "
                  f"({pct_done}% done, [yellow]{distill.get('pending',0)} pending[/yellow])")
    if distill.get("pending_by_cat"):
        console.print("  [dim]Pending:[/dim] " + "  ".join(
            f"{cat}:{n}" for cat, n in distill["pending_by_cat"].items()
        ))
    console.print()

    # ── gaps ──────────────────────────────────────────────────────────────────
    console.print("[bold cyan]Gaps & Actions[/bold cyan]")
    for g in gaps:
        color = {"HIGH": "red", "MED": "yellow", "LOW": "dim"}.get(g["priority"], "white")
        console.print(f"  [{color}][{g['priority']}][/{color}]  {g['action']}")
        console.print(f"    [dim]{g['gain']}[/dim]")
        console.print(f"    [dim cyan]{g['cmd']}[/dim cyan]")
        console.print()

    if not gaps:
        console.print("  [green]No critical gaps — pipeline is healthy![/green]")

def render_plain(datasets, logs, distill, gaps):
    print("=== AFS Training Pipeline Audit ===\n")
    print("TRAINING DATA")
    for d in datasets:
        pct = f"{d['pct']}%" if d["pct"] is not None else "?"
        print(f"  {d['status']} {d['file']:<38} {d['n']:>5}/{str(d['target'] or '?'):>6}  {pct:>5}  {fmt_size(d['size'])}")
    print()
    print(f"LOG EXTRACTION: {logs['high']} high-quality  {logs['new_extractable']} new  {logs['private']} private")
    print()
    print(f"DISTILLATION: {distill.get('done',0)}/{distill.get('total_prompts',0)} ({distill.get('pct_done',0)}%)")
    print()
    print("GAPS:")
    for g in gaps:
        print(f"  [{g['priority']}] {g['action']}")
        print(f"    {g['cmd']}")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Training pipeline health dashboard")
    parser.add_argument("--section", choices=["data", "logs", "distill", "gaps"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    datasets    = audit_datasets()
    logs        = audit_logs()
    distill     = audit_distillation()
    persona_raw = audit_persona_raw()
    gaps        = compute_gaps(datasets, logs, distill)

    if args.json:
        print(json.dumps({
            "datasets": datasets,
            "logs": logs,
            "distillation": distill,
            "gaps": gaps,
        }, indent=2))
        return

    if args.section == "data":
        datasets_only = [(d,) for d in datasets]
        if RICH:
            render_rich(datasets, {"total":0,"high":0,"private":0,"near_miss":0,
                                   "new_extractable":0,"score_dist":{},"tags":{},"projects":{},"top_new":[]},
                        {"done":0,"total_prompts":0,"pct_done":0,"pending":0,"pending_by_cat":{}}, [], [])
        return

    if RICH:
        render_rich(datasets, logs, distill, persona_raw, gaps)
    else:
        render_plain(datasets, logs, distill, gaps)


if __name__ == "__main__":
    main()
