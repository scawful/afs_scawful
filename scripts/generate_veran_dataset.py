#!/usr/bin/env python3
"""
Veran Dataset Generator - 2026 Analysis Training
Converts yaze/oracle-of-secrets registries into fine-tuning samples.
"""

import json
import os
from pathlib import Path

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def generate_veran_samples():
    oos_root = Path("/Users/scawful/src/hobby/oracle-of-secrets")
    dungeons_path = oos_root / "Docs/Dev/Planning/dungeons.json"
    overworld_path = oos_root / "Docs/Dev/Planning/overworld.json"
    
    if not dungeons_path.exists() or not overworld_path.exists():
        print("Error: Registries not found.")
        return

    dungeons_data = load_json(dungeons_path)
    overworld_data = load_json(overworld_path)
    
    samples = []

    # 1. Dungeon Room Analysis
    for dungeon in dungeons_data.get("dungeons", []):
        d_name = dungeon.get("name", "Unknown Dungeon")
        for room in dungeon.get("rooms", []):
            r_id = room.get("id", "??")
            r_name = room.get("name", "Unnamed Room")
            r_type = room.get("type", "normal")
            
            # Identify Room Task
            samples.append({
                "instruction": f"Identify the properties and location of Room ID {r_id}.",
                "analysis": f"Room {r_id} is '{r_name}' located in {d_name}. It is classified as a {r_type} room. Technical specs: Palette {room.get('palette', '??')}, Blockset {room.get('blockset', '??')}, Spriteset {room.get('spriteset', '??')}. Logic tags: {room.get('tag1', '??')}, {room.get('tag2', '??')}."
            })
            
            # Reverse Lookup Task
            if "spriteset" in room:
                samples.append({
                    "instruction": f"Which room in {d_name} uses Spriteset {room['spriteset']}?",
                    "analysis": f"Room {r_id} ({r_name}) in {d_name} is configured to use Spriteset {room['spriteset']}."
                })

    # 2. Overworld Area Analysis
    for area in overworld_data.get("areas", []):
        a_id = area.get("area_id", "??")
        a_name = area.get("name", "Unnamed Area")
        world = area.get("world", "Unknown World")
        features = area.get("notable_features", [])
        
        # Area Property Task
        samples.append({
            "instruction": f"Analyze Overworld Area {a_id} in {world}.",
            "analysis": f"Area {a_id} corresponds to '{a_name}' in the {world} world. Notable features include: {', '.join(features) if features else 'None'}. It uses GFX ID {area.get('gfx_id', '??')} and Sprite Set {area.get('sprite_set', '??')}."
        })
        
        # Item Lookup Task
        for item in area.get("items", []):
            item_name = item.get("item_name") or item.get("name") or "Unknown Item"
            samples.append({
                "instruction": f"Where is the {item_name} located in the Overworld?",
                "analysis": f"The {item_name} (ID {item.get('item_id', '??')}) is found in Area {a_id} ({a_name}) at tile coordinates {item.get('tile_pos', '??')}."
            })

    # Write to JSONL
    output_path = Path("afs/training_data/veran_v1_synthetic.jsonl")
    with open(output_path, "w") as f:
        for sample in samples:
            line = json.dumps({
                "messages": [
                    {"role": "system", "content": "You are Veran, the Oracle of Secrets Analysis Expert. You specialize in reverse engineering ROM structures and explaining game logic."},
                    {"role": "user", "content": sample["instruction"]},
                    {"role": "assistant", "content": sample["analysis"]}
                ]
            })
            f.write(line + "\n")
            
    print(f"Success: Generated {len(samples)} samples for Veran training at {output_path}")

if __name__ == "__main__":
    generate_veran_samples()
