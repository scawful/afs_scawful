import json
import os
from pathlib import Path
import re

def parse_ram_map(ram_md_path):
    """
    Parses Ram.md to create a mapping of hex addresses to labels.
    """
    addr_to_label = {}
    if not os.path.exists(ram_md_path):
        return addr_to_label
        
    with open(ram_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # Pattern like: **`MODE`** (`$7E0010`):
        # We also need to handle cases with multiple addresses like OWSCR/ROOM
        blocks = re.findall(r'\*\*(.*?)\*\*', content)
        for block in blocks:
            # block looks like: `MODE` (`$7E0010`):
            labels = re.findall(r'`([A-Z0-9_/]+)`', block)
            addrs = re.findall(r'`(\$[0-9A-Fa-f]+)`', block)
            
            if labels and addrs:
                # Map all labels in this block to all addresses found
                # (Simple heuristic for shared blocks like TAG1/TAG2)
                for l_group in labels:
                    for l in l_group.replace('/', ' ').split():
                        for a in addrs:
                            addr = a.upper()
                            addr_to_label[addr] = l
                            if addr.startswith("$7E") and len(addr) == 7:
                                short_addr = "$" + addr[3:]
                                if short_addr not in addr_to_label:
                                    addr_to_label[short_addr] = l
    return addr_to_label

def enrich_sample_with_labels(code, ram_map):
    """
    Replaces hex addresses in ASM code with their OoS labels.
    """
    if not code:
        return code
    new_code = code
    # Match hex addresses like $7E0010 or $0010
    addresses = re.findall(r'\$[0-9A-Fa-f]+', code)
    # Sort by length descending to avoid partial replacements
    addresses = list(set(addresses)) # Unique only
    addresses.sort(key=len, reverse=True)
    
    for addr in addresses:
        clean_addr = addr.upper()
        if clean_addr in ram_map:
            label = ram_map[clean_addr]
            # OoS style uses ! for RAM labels
            new_code = new_code.replace(addr, "!" + label)
            
    return new_code

def parse_asm_symbols(file_path):
    """
    Parses an .asm file for symbols defined as LABEL = $ADDRESS or LABEL = ADDRESS
    """
    symbols = {}
    if not os.path.exists(file_path):
        return symbols
        
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Match: LABEL = $7E0000 or LABEL = $0000
            # Also handle comments with ;
            clean_line = line.split(';')[0].strip()
            match = re.search(r'^([A-Z0-9_]+)\s*=\s*(\$[0-9A-Fa-f]+)', clean_line, re.IGNORECASE)
            if match:
                label = match.group(1)
                addr = match.group(2).upper()
                symbols[addr] = label
                # Add short mirror for $7E bank
                if addr.startswith("$7E") and len(addr) == 7:
                    short_addr = "$" + addr[3:]
                    if short_addr not in symbols:
                        symbols[short_addr] = label
    return symbols

def generate_oos_dataset(gold_dataset_path, ram_md_path, ram_asm_path, hardware_asm_path, output_path):
    """
    Takes an ASM dataset and enriches it with OoS labels.
    """
    # Combine all label sources
    ram_map = parse_ram_map(ram_md_path)
    ram_map.update(parse_asm_symbols(ram_asm_path))
    ram_map.update(parse_asm_symbols(hardware_asm_path))
    
    print(f"Total OoS labels loaded: {len(ram_map)}")
    
    samples = []
    with open(gold_dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                sample = json.loads(line)
                original_output = sample.get("output", "")
                original_input = sample.get("input", "")
                
                # Enrich both input and output
                oos_output = enrich_sample_with_labels(original_output, ram_map)
                oos_input = enrich_sample_with_labels(original_input, ram_map)
                
                if oos_output != original_output or oos_input != original_input:
                    sample["instruction"] = f"{sample['instruction']} (Using Oracle of Secrets symbols)"
                    sample["output"] = oos_output
                    sample["input"] = oos_input
                    sample["domain"] = "oos_asm"
                    samples.append(sample)
            except:
                continue

    with open(output_path, 'w') as f:
        for sample in samples:
            f.write(json.dumps(sample) + '\n')
            
    return len(samples)

if __name__ == "__main__":
    # Use full dataset if available, fallback to gold sample
    full_set = "training/datasets/vultr_train_full.jsonl"
    gold_sample = "training/datasets/vultr_gold_sample.jsonl"
    
    input_set = full_set if os.path.exists(full_set) else gold_sample
    ram_md = "hobby/oracle-of-secrets/Docs/Core/Ram.md"
    ram_asm = "hobby/oracle-of-secrets/Core/ram.asm"
    hardware_asm = "hobby/oracle-of-secrets/Core/hardware.asm"
    out_path = "training/datasets/oos_enriched_v1.jsonl"
    
    print(f"Using input set: {input_set}")
    if os.path.exists(input_set):
        count = generate_oos_dataset(input_set, ram_md, ram_asm, hardware_asm, out_path)
        print(f"Generated {count} OoS-enriched samples at {out_path}")
    else:
        print(f"Error: No input dataset found.")
