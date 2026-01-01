import json
import os
from pathlib import Path
import re

def generate_router_dataset(logs_dir, output_path):
    """
    Generates a dataset for the 'Expert Router' model.
    Categorizes user requests into expert domains: asm, cpp, devops, general.
    """
    samples = []
    logs_dir = Path(logs_dir)
    
    # Keyword-based labeling for initial bootstrap
    DOMAIN_KEYWORDS = {
        "asm": ["asm", "65816", "snes", "bank", "org", "asar", "hook", "link.asm", "sprite"],
        "cpp": ["cpp", "c++", "cmake", "imgui", "ftxui", "yaze", "syshub", "pointer", "header"],
        "devops": ["vultr", "ssh", "deploy", "gpu", "a100", "instance", "root@", "scripts/"],
    }

    if not logs_dir.exists():
        print(f"Error: {logs_dir} not found.")
        return

    for log_file in logs_dir.glob("*.json"):
        with open(log_file, 'r') as f:
            try:
                data = json.load(f)
            except:
                continue
                
            messages = data.get("messages", [])
            for msg in messages:
                if msg.get("type") == "user":
                    content = msg.get("content", "").lower()
                    
                    if not content or len(content) < 10:
                        continue
                        
                    # Determine domain
                    domain = "general"
                    for d, keywords in DOMAIN_KEYWORDS.items():
                        if any(k in content for k in keywords):
                            domain = d
                            break
                    
                    # Create sample
                    samples.append({
                        "instruction": "Classify the following user request into one of these expert domains: asm, cpp, devops, general.",
                        "input": msg.get("content"),
                        "output": domain
                    })

    with open(output_path, 'w') as f:
        for sample in samples:
            f.write(json.dumps(sample) + '\n')

    return len(samples)

if __name__ == "__main__":
    logs_dir = "docs/chat_logs"
    out_dir = Path("training/datasets")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    count = generate_router_dataset(logs_dir, out_dir / "expert_router_v1.jsonl")
    print(f"Generated {count} samples for Expert Router dataset at {out_dir / 'expert_router_v1.jsonl'}")
