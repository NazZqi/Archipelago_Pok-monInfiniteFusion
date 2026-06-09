from typing import Dict, List, TYPE_CHECKING
from BaseClasses import Region, Location, Entrance

if TYPE_CHECKING:
    from . import PokemonIFWorld

def create_regions(world: "PokemonIFWorld"):
    from .map_ids import REGION_MAP_IDS
    
    multiworld = world.multiworld
    player = world.player

    # Crear la región inicial
    menu = Region("Menu", player, multiworld)
    multiworld.regions.append(menu)

    # Diccionario para buscar rápidamente la región a la que pertenece un Map ID
    map_to_region_obj = {}
    
    # Kanto será nuestro fallback por defecto si un mapa no está registrado
    kanto_fallback = Region("Kanto Fallback", player, multiworld)
    multiworld.regions.append(kanto_fallback)
    
    # Conectar Menu al fallback por si acaso
    menu_to_fallback = Entrance(player, "Menu to Kanto Fallback", menu)
    menu_to_fallback.connect(kanto_fallback)
    menu.exits.append(menu_to_fallback)

    # Iterar sobre el diccionario plano
    for region_name, map_id_list in REGION_MAP_IDS.items():
        region_obj = Region(region_name, player, multiworld)
        multiworld.regions.append(region_obj)
        
        # Mapear los IDs
        for map_id in map_id_list:
            map_to_region_obj[map_id] = region_obj

    # Conectar el Menu al inicio del juego
    try:
        pallet_town = multiworld.get_region("Pallet Town", player)
        menu_to_pallet = Entrance(player, "Start Game", menu)
        menu_to_pallet.connect(pallet_town)
        menu.exits.append(menu_to_pallet)
    except Exception:
        pass

    # Asignar cada ubicación a su región correspondiente
    from .locations import location_table
    import re
    
    for location_name, loc_data in location_table.items():
        # Filtros de opciones
        if loc_data.type == "itemball" and not world.options.overworld_items:
            continue
        if loc_data.type == "npc" and not world.options.npc_gifts:
            continue
        if loc_data.type == "hidden_item" and not world.options.hidden_items:
            continue
            
        # Extraer el Map ID del string location_name
        # Formato: "Map X - Event Y"
        match = re.match(r"Map (\d+) -", location_name)
        if match:
            map_id = int(match.group(1))
            target_region = map_to_region_obj.get(map_id, kanto_fallback)
        else:
            target_region = kanto_fallback

        loc = Location(player, location_name, loc_data.code, target_region)
        target_region.locations.append(loc)

    # Event Location for the Goal
    try:
        indigo_plateau = multiworld.get_region("Indigo Plateau", player)
    except Exception:
        indigo_plateau = kanto_fallback
        
    goal_loc = Location(player, "Defeat Champion", None, indigo_plateau)
    goal_loc.place_locked_item(world.create_event("BEAT CHAMPION"))
    indigo_plateau.locations.append(goal_loc)
