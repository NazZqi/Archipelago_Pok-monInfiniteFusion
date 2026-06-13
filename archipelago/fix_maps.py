import json
import ast
import os

MAP_DUMP_PATH = os.path.join(os.path.dirname(__file__), 'apworld_dev', 'pokemon_infinite_fusion', 'map_dump.json')
MAP_IDS_PATH = os.path.join(os.path.dirname(__file__), 'apworld_dev', 'pokemon_infinite_fusion', 'map_ids.py')

with open(MAP_DUMP_PATH, 'r', encoding='utf-8') as f:
    map_dump = json.load(f)

with open(MAP_IDS_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
region_dict = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'REGION_MAP_IDS':
        for key, val in zip(node.value.keys, node.value.values):
            k = key.value if hasattr(key, 'value') else key.s
            v = [elt.value if hasattr(elt, 'value') else elt.n for elt in val.elts]
            region_dict[k] = v

map_to_region = {}
for reg, maps in region_dict.items():
    for m in maps:
        map_to_region[m] = reg

assigned_maps = {}
unassigned_maps = []

def get_region_for_map(m_id, visited=None):
    if visited is None: visited = set()
    if m_id in visited: return None
    visited.add(m_id)
    
    if m_id in map_to_region:
        return map_to_region[m_id]
        
    m_str = str(m_id)
    if m_str in map_dump:
        parent_id = map_dump[m_str]['parent']
        if parent_id != 0 and parent_id != m_id:
            return get_region_for_map(parent_id, visited)
            
    return None

all_maps = list(map_dump.keys())

for m_str in all_maps:
    m_id = int(m_str)
    region = get_region_for_map(m_id)
    if region:
        if region not in assigned_maps:
            assigned_maps[region] = set()
        assigned_maps[region].add(m_id)
    else:
        unassigned_maps.append(m_id)

unassigned_maps.sort()

with open(MAP_IDS_PATH, 'w', encoding='utf-8') as f:
    f.write('FALLBACK_MAP_IDS = ' + str(unassigned_maps) + '\n\n')
    f.write('REGION_MAP_IDS = {\n')
    for reg in region_dict.keys():
        maps = list(assigned_maps.get(reg, []))
        maps.sort()
        f.write(f'    \"{reg}\": {maps},\n')
    f.write('}\n')

print('Map IDs updated successfully!')
