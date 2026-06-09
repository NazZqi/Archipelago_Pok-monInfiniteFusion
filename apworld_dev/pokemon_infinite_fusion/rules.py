from typing import TYPE_CHECKING
from BaseClasses import MultiWorld, Entrance
from worlds.generic.Rules import set_rule, add_rule

if TYPE_CHECKING:
    from . import PokemonIFWorld

def set_rules(world: "PokemonIFWorld"):
    multiworld = world.multiworld
    player = world.player

    def connect(source, target, rule=None):
        try:
            source_region = multiworld.get_region(source, player)
            target_region = multiworld.get_region(target, player)
            ent = Entrance(player, f"{source} to {target}", source_region)
            ent.connect(target_region)
            if rule:
                set_rule(ent, rule)
            source_region.exits.append(ent)
        except Exception:
            pass

    def connect_both_ways(r1, r2, rule=None):
        connect(r1, r2, rule)
        connect(r2, r1, rule)

    # -------------------------------------------------------------
    # KANTO MAP CONNECTIONS AND LOGIC
    # -------------------------------------------------------------
    
    # Pallet to Pewter
    connect_both_ways("Pallet Town", "Route 1")
    connect_both_ways("Route 1", "Viridian City")
    connect_both_ways("Viridian City", "Route 22")
    connect_both_ways("Viridian City", "Route 2")
    connect_both_ways("Route 2", "Pewter City")
    connect_both_ways("Route 2", "Viridian Forest")
    connect_both_ways("Viridian Forest", "Pewter City")

    # Pewter to Cerulean
    connect_both_ways("Pewter City", "Route 3")
    connect_both_ways("Route 3", "Mt. Moon")
    connect_both_ways("Mt. Moon", "Route 4")
    connect_both_ways("Route 4", "Cerulean City")

    # Cerulean North
    connect_both_ways("Cerulean City", "Route 24")
    connect_both_ways("Route 24", "Route 25")

    # Cerulean South & East (requires Cut logically in gen 1, or Cascade Badge)
    connect_both_ways("Cerulean City", "Route 5")
    connect_both_ways("Cerulean City", "Route 9")
    
    # Route 5 to Vermillion (Underground path bypasses Saffron)
    connect_both_ways("Route 5", "Route 6")
    connect_both_ways("Route 6", "Vermillion City")

    # Vermillion East
    connect_both_ways("Vermillion City", "Route 11")
    # Route 11 to 12 requires Poke Flute usually, or Snorlax bypass
    connect_both_ways("Route 11", "Route 12", lambda state: state.has("Poké Flute", player))

    # Route 9 to Lavender
    connect_both_ways("Route 9", "Route 10")
    connect_both_ways("Route 10", "Rock Tunnel")
    connect_both_ways("Rock Tunnel", "Lavender Town", lambda state: state.has("HM05", player)) # Flash
    
    # Lavender connections
    connect_both_ways("Lavender Town", "Route 8")
    connect_both_ways("Lavender Town", "Route 12")

    # Celadon connections
    connect_both_ways("Celadon City", "Route 7")
    connect_both_ways("Route 7", "Route 8") # Underground Path
    connect_both_ways("Celadon City", "Route 16")

    # Fuchsia connections
    connect_both_ways("Route 16", "Route 17") # Cycling Road
    connect_both_ways("Route 17", "Route 18")
    connect_both_ways("Route 18", "Fuchsia City")
    connect_both_ways("Route 12", "Route 13")
    connect_both_ways("Route 13", "Route 14")
    connect_both_ways("Route 14", "Route 15")
    connect_both_ways("Route 15", "Fuchsia City")

    # Sea Routes (Require Surf)
    connect_both_ways("Fuchsia City", "Route 19", lambda state: state.has("HM03", player))
    connect_both_ways("Route 19", "Route 20")
    connect_both_ways("Route 20", "Cinnabar Island")
    connect_both_ways("Pallet Town", "Route 21", lambda state: state.has("HM03", player))
    connect_both_ways("Route 21", "Cinnabar Island")

    # Saffron City is the central hub, accessible from Routes 5, 6, 7, 8
    connect_both_ways("Route 5", "Saffron City")
    connect_both_ways("Route 6", "Saffron City")
    connect_both_ways("Route 7", "Saffron City")
    connect_both_ways("Route 8", "Saffron City")

    # -------------------------------------------------------------
    # ENDGAME CONNECTIONS
    # -------------------------------------------------------------
    # Requires 8 badges to enter Indigo Plateau
    connect("Route 22", "Route 23", lambda state: 
        state.has("Boulder Badge", player) and 
        state.has("Cascade Badge", player) and 
        state.has("Thunder Badge", player) and 
        state.has("Rainbow Badge", player) and 
        state.has("Soul Badge", player) and 
        state.has("Marsh Badge", player) and 
        state.has("Volcano Badge", player) and 
        state.has("Earth Badge", player)
    )
    connect_both_ways("Route 23", "Indigo Plateau")

    # -------------------------------------------------------------
    # JOHTO MAP CONNECTIONS AND LOGIC
    # -------------------------------------------------------------
    # Connection from Kanto to Johto
    connect_both_ways("Route 22", "Route 27", lambda state: state.has("HM03", player)) # Surf
    connect_both_ways("Route 27", "Route 26")
    connect_both_ways("Route 26", "New Bark Town")
    
    # Magnet Train
    connect_both_ways("Saffron City", "Goldenrod City")
    
    # Johto Routes
    connect_both_ways("New Bark Town", "Route 29")
    connect_both_ways("Route 29", "Cherrygrove City")
    connect_both_ways("Cherrygrove City", "Route 30")
    connect_both_ways("Route 30", "Route 31")
    connect_both_ways("Route 31", "Violet City")
    
    connect_both_ways("Violet City", "Route 32")
    connect_both_ways("Route 32", "Route 33")
    connect_both_ways("Route 33", "Azalea Town")
    
    # Ilex Forest (usually requires Cut)
    connect_both_ways("Azalea Town", "Route 34", lambda state: state.has("HM01", player))
    connect_both_ways("Route 34", "Goldenrod City")
    
    connect_both_ways("Goldenrod City", "Route 35")
    connect_both_ways("Route 35", "Route 36")
    connect_both_ways("Route 36", "Violet City") # Route 36 connects back to Violet
    connect_both_ways("Route 36", "Route 37")
    connect_both_ways("Route 37", "Ecruteak City")
    
    connect_both_ways("Ecruteak City", "Route 38")
    connect_both_ways("Route 38", "Route 39")
    connect_both_ways("Route 39", "Olivine City")
    
    connect_both_ways("Olivine City", "Route 40", lambda state: state.has("HM03", player)) # Surf to Cianwood
    connect_both_ways("Route 40", "Cianwood City")
    
    connect_both_ways("Ecruteak City", "Route 42", lambda state: state.has("HM03", player)) # Surf over Mt Mortar waters
    connect_both_ways("Route 42", "Mahogany Town")
    
    connect_both_ways("Mahogany Town", "Route 43")
    connect_both_ways("Route 43", "Route 44")
    connect_both_ways("Route 44", "Blackthorn City", lambda state: state.has("HM03", player)) # Ice Path
    
    connect_both_ways("Blackthorn City", "Route 46")
    connect_both_ways("Route 46", "Route 29")

    # -------------------------------------------------------------
    # SEVII ISLANDS CONNECTIONS
    # -------------------------------------------------------------
    # Accessible via Ferry from Vermillion City
    connect_both_ways("Vermillion City", "Knot Island")
    connect_both_ways("Knot Island", "Boon Island")
    connect_both_ways("Boon Island", "Kin Island")
    connect_both_ways("Kin Island", "Chrono Island")

    # -------------------------------------------------------------
    # CONDICIÓN DE VICTORIA (GOAL)
    # -------------------------------------------------------------
    goal = world.options.goal.value

    if goal == 0:  # Beat Champion
        multiworld.completion_condition[player] = lambda state: state.has("BEAT CHAMPION", player)
    else:
        multiworld.completion_condition[player] = lambda state: True
