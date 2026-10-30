from typing import TYPE_CHECKING
from worlds.generic.Rules import add_rule

if TYPE_CHECKING:
    from . import PokemonIFWorld

KANTO_BADGES = [
    "Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge",
    "Soul Badge", "Marsh Badge", "Volcano Badge", "Earth Badge",
]


def set_rules(world: "PokemonIFWorld"):
    multiworld = world.multiworld
    player = world.player
    require_flash = world.options.require_flash.value

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    # La lógica es deliberadamente más estricta que el juego: un requisito de más
    # solo reduce las ubicaciones tempranas, uno de menos genera semillas imposibles.
    # Se asume que cada MO necesita su medalla de Kanto (como en Gen 1).
    def can_cut(state):
        return state.has_all(("HM01", "Cascade Badge"), player)

    def can_surf(state):
        return state.has_all(("HM03", "Soul Badge"), player)

    def can_strength(state):
        return state.has_all(("HM04", "Rainbow Badge"), player)

    def can_flash(state):
        return state.has_all(("HM05", "Boulder Badge"), player)

    def has_bike(state):
        return state.has_any(("Bicycle", "Racing Bicycle"), player)

    def beat_champion(state):
        return state.has("BEAT CHAMPION", player)

    def connect(source, target, rule=None):
        # Sin try/except: un nombre de región mal escrito debe romper la generación,
        # no desaparecer en silencio.
        source_region = multiworld.get_region(source, player)
        target_region = multiworld.get_region(target, player)
        return source_region.connect(target_region, f"{source} to {target}", rule)

    def connect_both_ways(r1, r2, rule=None):
        return connect(r1, r2, rule), connect(r2, r1, rule)

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

    # Cerulean South & East (árbol de Corte hacia la Ruta 9)
    connect_both_ways("Cerulean City", "Route 5")
    connect_both_ways("Cerulean City", "Route 9", can_cut)

    # Route 5 to Vermillion (Underground path bypasses Saffron)
    connect_both_ways("Route 5", "Route 6")
    connect_both_ways("Route 6", "Vermillion City")

    # Vermillion East. Snorlax bloquea la Ruta 12 desde ambos lados.
    connect_both_ways("Vermillion City", "Route 11")
    connect_both_ways("Route 11", "Route 12", lambda state: state.has("Poké Flute", player))

    # Route 9 to Lavender
    rock_tunnel_rule = can_flash if require_flash in (1, 3) else None
    connect_both_ways("Route 9", "Route 10")
    connect_both_ways("Route 10", "Rock Tunnel")
    connect_both_ways("Rock Tunnel", "Lavender Town", rock_tunnel_rule)

    # Lavender connections
    connect_both_ways("Lavender Town", "Route 8")
    connect_both_ways("Lavender Town", "Route 12", lambda state: state.has("Poké Flute", player))

    # Celadon connections (Snorlax en la Ruta 16)
    connect_both_ways("Celadon City", "Route 7")
    connect_both_ways("Route 7", "Route 8")  # Underground Path
    connect_both_ways("Celadon City", "Route 16", lambda state: state.has("Poké Flute", player))

    # Fuchsia connections (Cycling Road: Rutas 17 y 18 requieren bicicleta)
    connect_both_ways("Route 16", "Route 17", has_bike)
    connect_both_ways("Route 17", "Route 18", has_bike)
    connect_both_ways("Route 18", "Fuchsia City", has_bike)
    connect_both_ways("Route 12", "Route 13")
    connect_both_ways("Route 13", "Route 14")
    connect_both_ways("Route 14", "Route 15")
    connect_both_ways("Route 15", "Fuchsia City")

    # Sea Routes (Require Surf)
    connect_both_ways("Fuchsia City", "Route 19", can_surf)
    connect_both_ways("Route 19", "Route 20")
    connect_both_ways("Route 20", "Cinnabar Island")
    connect_both_ways("Pallet Town", "Route 21", can_surf)
    connect_both_ways("Route 21", "Cinnabar Island")

    # Saffron City: los guardias piden una bebida, que solo se compra en Celadon.
    celadon = multiworld.get_region("Celadon City", player)

    def reached_celadon(state):
        return state.can_reach_region("Celadon City", player)

    for route in ("Route 5", "Route 6", "Route 7", "Route 8"):
        for entrance in connect_both_ways(route, "Saffron City", reached_celadon):
            multiworld.register_indirect_condition(celadon, entrance)

    # -------------------------------------------------------------
    # ENDGAME CONNECTIONS
    # -------------------------------------------------------------
    # El juego exige las 8 medallas en la Ruta 22, sin importar elite_four_count:
    # esa opción todavía no está implementada del lado del juego.
    connect("Route 22", "Route 23", lambda state: state.has_all(KANTO_BADGES, player) and can_surf(state))
    connect("Route 23", "Route 22")

    # Victory Road
    def victory_road(state):
        return can_strength(state) and (require_flash not in (2, 3) or can_flash(state))

    connect_both_ways("Route 23", "Indigo Plateau", victory_road)

    # -------------------------------------------------------------
    # JOHTO MAP CONNECTIONS AND LOGIC
    # -------------------------------------------------------------
    # Johto es post-juego. Solo Goldenrod se abre antes, con el Magnet Train.
    connect_both_ways("Route 22", "Route 27", lambda state: beat_champion(state) and can_surf(state))
    connect_both_ways("Route 27", "Route 26")
    connect_both_ways("Route 26", "New Bark Town")

    # Magnet Train
    connect_both_ways("Saffron City", "Goldenrod City", lambda state: state.has("Train Pass", player))

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
    connect_both_ways("Azalea Town", "Route 34", can_cut)
    connect_both_ways("Route 34", "Goldenrod City", beat_champion)

    connect_both_ways("Goldenrod City", "Route 35", beat_champion)
    connect_both_ways("Route 35", "Route 36")
    connect_both_ways("Route 36", "Violet City")  # Route 36 connects back to Violet
    connect_both_ways("Route 36", "Route 37")
    connect_both_ways("Route 37", "Ecruteak City")

    connect_both_ways("Ecruteak City", "Route 38")
    connect_both_ways("Route 38", "Route 39")
    connect_both_ways("Route 39", "Olivine City")

    connect_both_ways("Olivine City", "Route 40", can_surf)  # Surf to Cianwood
    connect_both_ways("Route 40", "Cianwood City")

    connect_both_ways("Ecruteak City", "Route 42", can_surf)  # Surf over Mt Mortar waters
    connect_both_ways("Route 42", "Mahogany Town")

    connect_both_ways("Mahogany Town", "Route 43")
    connect_both_ways("Route 43", "Route 44")
    connect_both_ways("Route 44", "Blackthorn City", can_strength)  # Ice Path

    connect_both_ways("Blackthorn City", "Route 46")
    connect_both_ways("Route 46", "Route 29")

    # -------------------------------------------------------------
    # SEVII ISLANDS CONNECTIONS
    # -------------------------------------------------------------
    # Accessible via Ferry from Vermillion City (post-juego, por precaución)
    connect_both_ways("Vermillion City", "Knot Island", beat_champion)
    connect_both_ways("Knot Island", "Boon Island")
    connect_both_ways("Boon Island", "Kin Island")
    connect_both_ways("Kin Island", "Chrono Island")

    # -------------------------------------------------------------
    # MAPAS SIN REGIÓN CONOCIDA
    # -------------------------------------------------------------
    # No sabemos dónde están: se tratan como lo último accesible del juego para
    # que el generador nunca ponga ahí algo necesario para avanzar.
    def everything(state):
        return (beat_champion(state) and can_cut(state) and can_surf(state) and can_strength(state)
                and can_flash(state) and has_bike(state)
                and state.has_all(("Poké Flute", "Train Pass"), player))

    connect("Menu", "Kanto Fallback", everything)

    # -------------------------------------------------------------
    # MEDALLAS VANILLA
    # -------------------------------------------------------------
    if world.badges_vanilla:
        add_rule(multiworld.get_location("Vermillion Gym", player), can_cut)  # árbol del gimnasio
        add_rule(multiworld.get_location("Viridian Gym", player),
                 lambda state: state.has_all([b for b in KANTO_BADGES if b != "Earth Badge"], player))

    # -------------------------------------------------------------
    # CONDICIÓN DE VICTORIA (GOAL)
    # -------------------------------------------------------------
    # Solo existe "champion": el juego avisa la meta al entrar al Salón de la Fama.
    multiworld.completion_condition[player] = beat_champion
