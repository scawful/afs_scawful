import json
import os
from pathlib import Path
import re
import sys

# Ensure we can import from other scripts in the same dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def clean_output(text):
    """Simple cleanup for tool outputs to keep samples concise."""
    if not text:
        return ""
    if len(text) > 500:
        return text[:450] + "... [TRUNCATED]"
    return text

def extract_state_from_content(content):
    """Attempts to extract 'Status', 'Details', or 'Decision' like sections."""
    state_parts = []
    patterns = [
        r'### Current Status:(.*?)(?=###|$)',
        r'### Details:(.*?)(?=###|$)',
        r'### Errors:(.*?)(?=###|$)',
        r'### Next Steps:(.*?)(?=###|$)',
        r'Decision:(.*?)(?=\n\n|$)'
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            state_parts.append(match.group(0).strip())
    return "\n\n".join(state_parts)

def detect_metacognition(history_buffer):
    """Analyzes tool history to detect 'spinning' or 'making_progress'."""
    if len(history_buffer) < 3: return None
    tools = []
    for entry in history_buffer:
        if entry.startswith("Tool:"):
            match = re.match(r"Tool: (\w+)", entry)
            if match:
                tools.append((match.group(1), "Error" in entry or "[STATUS: ERROR]" in entry))
    if len(tools) >= 3:
        last_three = tools[-3:]
        if all(t[0] == last_three[0][0] for t in last_three) and all(t[1] for t in last_three):
            return {"progress_status": "spinning", "reason": f"Repeated failures with {last_three[0][0]} detected."}
        successes = [t for t in tools[-5:] if not t[1]]
        if len(successes) >= 2:
            unique_tools = len(set(t[0] for t in successes))
            if unique_tools >= 2:
                return {"progress_status": "making_progress", "reason": f"Successful execution of {unique_tools} different tools."}
    return None

def generate_conflict_samples(ram_map):
    """Generates synthetic samples where code conflicts with RAM documentation."""
    samples = []
    if not ram_map: return samples
    for addr, label in list(ram_map.items())[:20]:
        bad_label = "LinkHP" if label != "LinkHP" else "EnemyHealth"
        samples.append({
            "instruction": "Identify if the following code change conflicts with the project's RAM documentation.",
            "input": f"Documentation: {label} is at {addr}\nCode Change: STA {addr} ; Store Link's Health",
            "output": f"CONFLICT: The code uses {addr} for Link's Health, but documentation identifies this address as {label}."
        })
        samples.append({
            "instruction": "Identify if the following code change conflicts with the project's RAM documentation.",
            "input": f"Documentation: {label} is at {addr}\nCode Change: LDA !{label} ; Load the {label} state",
            "output": "NO CONFLICT: The code correctly uses the documented label and address."
        })
    return samples

def generate_nerv_watcher_dataset(logs_dir, output_path):
    samples = []
    logs_dir = Path(logs_dir)
    
    # 1. Metacognition & State Samples from Logs
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.json"):
            with open(log_file, 'r') as f:
                try:
                    data = json.load(f)
                    messages = data.get("messages", [])
                    history_buffer = []
                    for msg in messages:
                        role = msg.get("type")
                        content = msg.get("content", "")
                        tool_calls = msg.get("toolCalls", [])
                        for tc in tool_calls:
                            tc_name = tc.get('name', 'unknown')
                            # Check for errors in result
                            res_obj = str(tc.get('result', [{}]))
                            is_error = "Error" in res_obj or "error" in res_obj.lower()
                            tc_summary = f"Tool: {tc_name}({json.dumps(tc.get('args', {}))})\nOutput: {clean_output(tc.get('resultDisplay', ''))}"
                            if is_error: tc_summary += "\n[STATUS: ERROR]"
                            history_buffer.append(tc_summary)
                        
                        meta = detect_metacognition(history_buffer)
                        if meta:
                            samples.append({
                                "instruction": "Analyze the tool execution history and determine the agent's progress status (progress_status, reason).",
                                "input": "\n---\n".join(history_buffer[-10:]),
                                "output": json.dumps(meta, indent=2)
                            })
                        if role == "gemini":
                            state_update = extract_state_from_content(content)
                            if state_update and history_buffer:
                                samples.append({
                                    "instruction": "Synthesize the following tool interactions and assistant thoughts into a structured 'state.md' update.",
                                    "input": "\n---".join(history_buffer[-8:]),
                                    "output": state_update
                                })
                        if content: history_buffer.append(f"{role}: {content[:300]}...")
                except Exception as e:
                    print(f"Error processing {log_file}: {e}")

    # 2. Conflict Samples from RAM Map
    try:
        from generate_oos_enriched_dataset import parse_asm_symbols
        ram_map = parse_asm_symbols("hobby/oracle-of-secrets/Core/ram.asm")
        samples.extend(generate_conflict_samples(ram_map))
    except Exception as e:
        print(f"Error generating conflict samples: {e}")

    # Write samples
    with open(output_path, 'w') as f:
        for sample in samples:
            f.write(json.dumps(sample) + '\n')
    return len(samples)

if __name__ == "__main__":
    logs_dir = "docs/chat_logs"
    out_dir = Path("training/datasets")
    out_dir.mkdir(parents=True, exist_ok=True)
    count = generate_nerv_watcher_dataset(logs_dir, out_dir / "nerv_watcher_v1.jsonl")
    print(f"Generated {count} samples for Nerv Watcher dataset at {out_dir / 'nerv_watcher_v1.jsonl'}")