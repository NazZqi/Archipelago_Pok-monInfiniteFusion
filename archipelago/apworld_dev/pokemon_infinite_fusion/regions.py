from typing import Dict, List, TYPE_CHECKING
from BaseClasses import Region, Location, Entrance

if TYPE_CHECKING:
    from . import PokemonIFWorld

# Con medallas/MOs vanilla el juego las entrega en su sitio original; la lógica
# necesita saber dónde para no exigirlas antes de tiempo.
VANILLA_BADGE_LOCATIONS = {
    "Boulder Badge": ("Pewter Gym", "Pewter City"),
    "Cascade Badge": ("Cerulean Gym", "Cerulean City"),
    "Thunder Badge": ("Vermillion Gym", "Vermillion City"),
    "Rainbow Badge": ("Celadon Gym", "Celadon City"),
    "Soul Badge": ("Fuchsia Gym", "Fuchsia City"),
    "Marsh Badge": ("Saffron Gym", "Saffron City"),
    "Volcano Badge": ("Cinnabar Gym", "Cinnabar Island"),
    "Earth Badge": ("Viridian Gym", "Viridian City"),
}

# Solo las MOs que usa la lógica (rules.py).
VANILLA_HM_LOCATIONS = {
    "HM01": ("S.S. Anne Captain", "Vermillion City"),
    "HM03": ("Safari Zone Secret House", "Fuchsia City"),
    "HM04": ("Safari Zone Warden", "Fuchsia City"),
    "HM05": ("Route 2 Aide", "Route 2"),
}

def create_regions(world: "PokemonIFWorld"):
    from .map_ids import REGION_MAP_IDS

    multiworld = world.multiworld
    player = world.player

    # Crear la región inicial
    menu = Region("Menu", player, multiworld)
    multiworld.regions.append(menu)

    # Diccionario para buscar rápidamente la región a la que pertenece un Map ID
    map_to_region_obj = {}

    # Mapas sin región conocida. Se conecta desde Menu en rules.py, con requisitos de fin de juego.
    kanto_fallback = Region("Kanto Fallback", player, multiworld)
    multiworld.regions.append(kanto_fallback)

    # Iterar sobre el diccionario plano
    for region_name, map_id_list in REGION_MAP_IDS.items():
        region_obj = Region(region_name, player, multiworld)
        multiworld.regions.append(region_obj)

        # Mapear los IDs
        for map_id in map_id_list:
            map_to_region_obj[map_id] = region_obj

    # Conectar el Menu al inicio del juego
    menu.connect(multiworld.get_region("Pallet Town", player), "Start Game")

    # Asignar cada ubicación a su región correspondiente
    from .locations import location_table
    import re

    is_random = world.options.randomize_everything.value
    for location_name, loc_data in location_table.items():
        # Filtros de opciones
        if loc_data.type == "itemball" and not (is_random or world.options.overworld_items):
            continue
        if loc_data.type == "npc" and not (is_random or world.options.npc_gifts):
            continue
        if loc_data.type == "hidden_item" and not (is_random or world.options.hidden_items):
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

    # Eventos vanilla (sin ID: no son checks, solo informan a la lógica)
    vanilla = {}
    if world.badges_vanilla:
        vanilla.update(VANILLA_BADGE_LOCATIONS)
    if world.hms_vanilla:
        vanilla.update(VANILLA_HM_LOCATIONS)
    for item_name, (location_name, region_name) in vanilla.items():
        region = multiworld.get_region(region_name, player)
        loc = Location(player, location_name, None, region)
        loc.place_locked_item(world.create_event(item_name))
        region.locations.append(loc)

    # Event Location for the Goal
    indigo_plateau = multiworld.get_region("Indigo Plateau", player)
    goal_loc = Location(player, "Defeat Champion", None, indigo_plateau)
    goal_loc.place_locked_item(world.create_event("BEAT CHAMPION"))
    indigo_plateau.locations.append(goal_loc)
