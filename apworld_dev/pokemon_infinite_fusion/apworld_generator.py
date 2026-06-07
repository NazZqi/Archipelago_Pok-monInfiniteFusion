import json
import os

JSON_PATH = r"c:\Users\mendo\Documents\PokemonIF_AP\infinitefusion-e18\ap_locations.json"
OUTPUT_DIR = r"c:\Users\mendo\Documents\PokemonIF_AP\apworld_dev\pokemon_infinite_fusion"

def generate():
    print("Cargando ubicaciones...")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Filtrar duplicados usando (map_id, event_id)
    unique_locations = {}
    for loc in raw_data:
        key = (loc["map_id"], loc["event_id"])
        # Ignorar eventos sin nombre o problemáticos
        if key not in unique_locations:
            unique_locations[key] = loc

    locations_list = list(unique_locations.values())
    print(f"Ubicaciones únicas encontradas: {len(locations_list)}")

    # 1. Generar locations.py
    locations_py = os.path.join(OUTPUT_DIR, "locations.py")
    with open(locations_py, "w", encoding="utf-8") as f:
        f.write('from typing import Dict, NamedTuple\n\n')
        f.write('class IFLocationData(NamedTuple):\n')
        f.write('    code: int\n')
        f.write('    region: str\n\n')
        f.write('location_table: Dict[str, IFLocationData] = {\n')
        
        base_id = 2560000
        for i, loc in enumerate(locations_list):
            loc_name = f"{loc['map_name']} - Event {loc['event_id']}"
            code = base_id + i
            # Evitar nombres duplicados si dos mapas se llaman igual
            f.write(f'    "{loc_name} (Map {loc["map_id"]})": IFLocationData({code}, "{loc["map_name"]}"),\n')
        
        f.write('}\n')
    print(f"Generado {locations_py}")

    # 2. Generar items.py básico
    items_py = os.path.join(OUTPUT_DIR, "items.py")
    with open(items_py, "w", encoding="utf-8") as f:
        f.write('from BaseClasses import ItemClassification\n')
        f.write('from typing import Dict, NamedTuple\n\n')
        f.write('class IFItemData(NamedTuple):\n')
        f.write('    code: int\n')
        f.write('    classification: ItemClassification\n\n')
        f.write('item_table: Dict[str, IFItemData] = {\n')
        
        # Medallas
        base_item_id = 2660000
        badges = [
            "Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge",
            "Soul Badge", "Marsh Badge", "Volcano Badge", "Earth Badge"
        ]
        for i, badge in enumerate(badges):
            f.write(f'    "{badge}": IFItemData({base_item_id + i}, ItemClassification.progression),\n')
            
        # HMs
        hms = ["HM01 Cut", "HM02 Fly", "HM03 Surf", "HM04 Strength", "HM05 Flash"]
        for i, hm in enumerate(hms):
            f.write(f'    "{hm}": IFItemData({base_item_id + 100 + i}, ItemClassification.progression),\n')
            
        # Filler
        f.write(f'    "Potion": IFItemData({base_item_id + 200}, ItemClassification.filler),\n')
        f.write(f'    "Poke Ball": IFItemData({base_item_id + 201}, ItemClassification.filler),\n')
        f.write(f'    "Rare Candy": IFItemData({base_item_id + 202}, ItemClassification.useful),\n')
        
        f.write('}\n')
    print(f"Generado {items_py}")

    # 3. Generar mapeo para el cliente
    mapping_path = r"c:\Users\mendo\Documents\PokemonIF_AP\client_mapping.json"
    mapping_data = {}
    for i, loc in enumerate(locations_list):
        key = f"{loc['map_id']}_{loc['event_id']}"
        mapping_data[key] = base_id + i
        
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping_data, f, indent=4)
    print(f"Generado {mapping_path}")

if __name__ == "__main__":
    generate()
