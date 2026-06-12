import json
import os

DUMP_PATH = r"c:\Users\mendo\Documents\PokemonIF_AP\infinitefusion-e18\Data\ap_locations_classified.json"
LOCATIONS_PY = r"c:\Users\mendo\Documents\PokemonIF_AP\apworld_dev\pokemon_infinite_fusion\locations.py"
CLIENT_MAPPING = r"c:\Users\mendo\Documents\PokemonIF_AP\apworld_dev\pokemon_infinite_fusion\client_mapping.json"

def generate():
    with open(DUMP_PATH, "r", encoding="utf-8") as f:
        raw_locations = json.load(f)

    # Dictionary to store for client
    client_mapping = {}

    with open(LOCATIONS_PY, "w", encoding="utf-8") as f:
        f.write('from typing import Dict, NamedTuple\n\n')
        f.write('class IFLocationData(NamedTuple):\n')
        f.write('    code: int\n')
        f.write('    region: str\n')
        f.write('    type: str\n\n')
        f.write('location_table: Dict[str, IFLocationData] = {\n')
        
        for loc in raw_locations:
            loc_id = loc["id"]
            map_id = loc["map_id"]
            event_id = loc["event_id"]
            loc_type = loc["type"]
            code = loc["code"]
            
            # Use map and event id for the name for now
            name = f"Map {map_id} - Event {event_id} ({loc_id})"
            
            f.write(f'    "{name}": IFLocationData({code}, "Kanto", "{loc_type}"),\n')
            
            # Remove the index (_0) for the client mapping if it's the first one, 
            # or keep it. Wait, the Ruby hook sends map_id_event_id.
            # If multiple items exist, we need to map them. For simplicity, we just map map_id_event_id to the first code found.
            # Or we can just use the exact loc_id if Ruby hook sends it? No, Ruby hook doesn't know the index.
            # So we map map_id_event_id to a LIST of AP IDs.
            
            base_key = f"{map_id}_{event_id}"
            if base_key not in client_mapping:
                client_mapping[base_key] = []
            client_mapping[base_key].append(code)
            
        f.write('}\n')

    with open(CLIENT_MAPPING, "w", encoding="utf-8") as f:
        json.dump(client_mapping, f, indent=4)

    print(f"Generado {LOCATIONS_PY} con {len(raw_locations)} ubicaciones.")
    print(f"Generado {CLIENT_MAPPING} con {len(client_mapping)} ubicaciones únicas base.")

if __name__ == "__main__":
    generate()
