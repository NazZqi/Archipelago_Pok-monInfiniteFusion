import json
import os

ITEMS_JSON_PATH = r"c:\Users\mendo\Documents\PokemonIF_AP\infinitefusion-e18\ap_items_dump.json"
OUTPUT_DIR = r"c:\Users\mendo\Documents\PokemonIF_AP\apworld_dev\pokemon_infinite_fusion"

def generate():
    # GENERATE ITEMS
    print("Cargando objetos desde el dump del juego...")
    with open(ITEMS_JSON_PATH, "r", encoding="utf-8") as f:
        raw_items = json.load(f)
        
    # Filtrar IDs numéricos y objetos sin nombre (dejamos solo los IDs simbólicos reales)
    real_items = []
    seen_ids = set()
    for item in raw_items:
        if item["id"].isdigit(): continue
        if item["id"] in seen_ids: continue
        # Ignore strange blank names
        if not item["name"] or item["name"] == "Unnamed": continue
        real_items.append(item)
        seen_ids.add(item["id"])
        
    print(f"Objetos reales únicos encontrados: {len(real_items)}")

    items_py = os.path.join(OUTPUT_DIR, "items.py")
    client_items_dict = {}
    
    with open(items_py, "w", encoding="utf-8") as f:
        f.write('from BaseClasses import ItemClassification\n')
        f.write('from typing import Dict, NamedTuple\n\n')
        f.write('class IFItemData(NamedTuple):\n')
        f.write('    code: int\n')
        f.write('    classification: ItemClassification\n\n')
        f.write('item_table: Dict[str, IFItemData] = {\n')
        
        # Medallas (Manuales, porque no existen en el dump como items)
        base_item_id = 2660000
        badges = [
            "Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge",
            "Soul Badge", "Marsh Badge", "Volcano Badge", "Earth Badge"
        ]
        for i, badge in enumerate(badges):
            code = base_item_id + i
            f.write(f'    "{badge}": IFItemData({code}, ItemClassification.progression),\n')
            client_items_dict[str(code)] = {
                "name": badge,
                "type": "badge",
                "badge_id": i
            }
            
        # Objetos del juego (ap_items_dump)
        current_id = 2660100
        for item in real_items:
            classification = f"ItemClassification.{item['classification']}"
            f.write(f'    "{item["name"]}": IFItemData({current_id}, {classification}),\n')
            client_items_dict[str(current_id)] = {
                "name": item["name"],
                "type": "item",
                "game_id": item["id"] # Simbólico como "POTION"
            }
            current_id += 1
        
        f.write('}\n')
    print(f"Generado {items_py}")
    
    client_items_path = r"c:\Users\mendo\Documents\PokemonIF_AP\client_items.json"
    with open(client_items_path, "w", encoding="utf-8") as f:
        json.dump(client_items_dict, f, indent=4)
    print(f"Generado {client_items_path}")

if __name__ == "__main__":
    generate()


