import typing
import json
import os
from . import components as components
from BaseClasses import Region, Entrance, Location, Item, Tutorial, ItemClassification
from NetUtils import Version
from worlds.AutoWorld import World, WebWorld
from .items import item_table, IFItemData
from .locations import location_table, IFLocationData
from .options import PokemonIFOptions

class PokemonIFWeb(WebWorld):
    theme = "ocean"
    bug_report_page = "https://github.com/NazZqi/Archipelago_Pok-monInfiniteFusion/issues"
    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up the Pokemon Infinite Fusion randomizer.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Author"]
    )
    tutorials = [setup_en]

class PokemonIFWorld(World):
    """
    Pokemon Infinite Fusion Randomizer
    Explore Kanto and Johto with fused Pokemon!
    """
    game = "Pokemon Infinite Fusion"
    web = PokemonIFWeb()
    options_dataclass = PokemonIFOptions
    version = Version(1, 0, 0)

    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = {name: data.code for name, data in location_table.items()}
    
    def set_rules(self):
        # 1. Recuperar la meta seleccionada por el jugador
        goal = self.options.goal.value
        
        # Lista de medallas para la condición de victoria
        badges = [
            "Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge", 
            "Soul Badge", "Marsh Badge", "Volcano Badge", "Earth Badge"
        ]
        
        # 2. Definir la condición de victoria (completion_condition)
        if goal == 0:  # Champion
            # Por defecto, requerir las 8 medallas (o las necesarias según Elite Four Count)
            required_badges = self.options.elite_four_count.value
            
            self.multiworld.completion_condition[self.player] = lambda state: \
                sum(state.has(badge, self.player) for badge in badges) >= required_badges
                
        elif goal == 1:  # Cerulean Cave
            required_badges = self.options.cerulean_cave_count.value
            self.multiworld.completion_condition[self.player] = lambda state: \
                sum(state.has(badge, self.player) for badge in badges) >= required_badges
                
        elif goal == 2:  # Fusion Master
            # Fusion master puede requerir un objeto específico o algo de lógica
            # Como ejemplo, requerimos que sea posible llegar al final
            self.multiworld.completion_condition[self.player] = lambda state: True
            
        elif goal == 3:  # Legendary Hunt
            # Requiere cierta cantidad de legendarios, por ahora lo dejamos siempre válido
            self.multiworld.completion_condition[self.player] = lambda state: True
            
        else:
            self.multiworld.completion_condition[self.player] = lambda state: True
    
    def create_items(self):
        filler_item_names = []
        
        # 1. Añadir 1 copia de CADA ítem (progresión, útiles y fillers)
        for name, data in item_table.items():
            self.multiworld.itempool.append(self.create_item(name))
            if data.classification == ItemClassification.filler:
                filler_item_names.append(name)
            
        # 2. Rellenar el resto de ubicaciones con fillers aleatorios
        locations_count = len(self.multiworld.get_unfilled_locations(self.player))
        items_count = len(self.multiworld.itempool)
        
        while items_count < locations_count:
            filler_choice = self.multiworld.random.choice(filler_item_names) if filler_item_names else "Potion"
            self.multiworld.itempool.append(self.create_item(filler_choice))
            items_count += 1


    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        kanto = Region("Kanto", self.player, self.multiworld)
        menu.connect(kanto)
        
        for location_name, loc_data in location_table.items():
            # Filtro según opciones del YAML
            if loc_data.type == "itemball" and not self.options.overworld_items:
                continue
            if loc_data.type == "npc" and not self.options.npc_gifts:
                continue
            if loc_data.type == "hidden_item" and not self.options.hidden_items:
                continue
                
            loc = Location(self.player, location_name, loc_data.code, kanto)
            kanto.locations.append(loc)
            
        self.multiworld.regions.append(menu)
        self.multiworld.regions.append(kanto)

    def fill_slot_data(self) -> dict:
        print(f"\n\n--- DEBUG SLOT DATA ---")
        print(f"wild_pokemon: {self.options.wild_pokemon.value}")
        print(f"starters: {self.options.starters.value}")
        print(f"fusion_randomization: {self.options.fusion_randomization.value}")
        print(f"hidden_items: {self.options.hidden_items.value}")
        print(f"-----------------------\n\n")
        return {
            "goal": self.options.goal.value,
            "badges": self.options.badges.value,
            "hms": self.options.hms.value,
            "key_items": self.options.key_items.value,
            "overworld_items": self.options.overworld_items.value,
            "hidden_items": self.options.hidden_items.value,
            "npc_gifts": self.options.npc_gifts.value,
            "fusion_items": self.options.fusion_items.value,
            "dexsanity": self.options.dexsanity.value,
            "trainersanity": self.options.trainersanity.value,
            "item_pool_type": self.options.item_pool_type.value,
            "elite_four_requirement": self.options.elite_four_requirement.value,
            "elite_four_count": self.options.elite_four_count.value,
            "cerulean_cave_requirement": self.options.cerulean_cave_requirement.value,
            "cerulean_cave_count": self.options.cerulean_cave_count.value,
            "require_itemfinder": self.options.require_itemfinder.value,
            "require_flash": self.options.require_flash.value,
            "wild_pokemon": self.options.wild_pokemon.value,
            "starters": self.options.starters.value,
            "trainer_parties": self.options.trainer_parties.value,
            "force_fully_evolved": self.options.force_fully_evolved.value,
            "legendary_encounters": self.options.legendary_encounters.value,
            "fusion_randomization": self.options.fusion_randomization.value,
            "types": self.options.types.value,
            "abilities": self.options.abilities.value,
            "level_up_moves": self.options.level_up_moves.value,
            "tm_tutor_compatibility": self.options.tm_tutor_compatibility.value,
            "hm_compatibility": self.options.hm_compatibility.value,
            "tm_tutor_moves": self.options.tm_tutor_moves.value,
            "reusable_tms_tutors": self.options.reusable_tms_tutors.value,
            "min_catch_rate": self.options.min_catch_rate.value,
            "guaranteed_catch": self.options.guaranteed_catch.value,
            "exp_modifier": self.options.exp_modifier.value,
            "blind_trainers": self.options.blind_trainers.value,
            "match_trainer_levels": self.options.match_trainer_levels.value,
            "match_trainer_levels_bonus": self.options.match_trainer_levels_bonus.value,
            "double_battle_chance": self.options.double_battle_chance.value,
            "better_shops": self.options.better_shops.value,
            "turbo_a": self.options.turbo_a.value,
            "receive_item_messages": self.options.receive_item_messages.value,
            "remote_items": self.options.remote_items.value,
            "allow_triple_fusions": self.options.allow_triple_fusions.value,
            "fusion_sprite_style": self.options.fusion_sprite_style.value,
            "npc_fusion_reveal": self.options.npc_fusion_reveal.value,
            "legendary_hunt_count": self.options.legendary_hunt_count.value,
            "death_link": self.options.death_link.value,
            "enable_wonder_trading": self.options.enable_wonder_trading.value,
            "music": self.options.music.value,
            "fanfares": self.options.fanfares.value,
            "wild_encounter_blacklist": list(self.options.wild_encounter_blacklist.value),
            "starter_blacklist": list(self.options.starter_blacklist.value),
            "ability_blacklist": list(self.options.ability_blacklist.value),
            "move_blacklist": list(self.options.move_blacklist.value),
            "allowed_legendary_hunt_encounters": list(self.options.allowed_legendary_hunt_encounters.value),
        }

    def create_item(self, name: str) -> Item:
        item_data = item_table[name]
        return Item(name, item_data.classification, item_data.code, self.player)

    def generate_output(self, output_directory: str):
        data = {
            "server": "",
            "port": 38281,
            "player_name": self.multiworld.player_name[self.player],
            "slot_name": self.multiworld.player_name[self.player],
        }
        
        seed_name = self.multiworld.seed_name
        player_name = self.multiworld.get_file_safe_player_name(self.player)
        
        # El formato que pide el usuario: P{player}_{player_name}_{seed_name}.apif
        filename = f"P{self.player}_{player_name}_{seed_name}.apif"
        
        # Archipelago.gg rechaza archivos dentro del ZIP con extensiones desconocidas.
        # Guardaremos una copia local (fuera del zip) para conveniencia,
        # pero también creamos el archivo dentro del zip con extensión .json para WebHost.
        
        # 1. Copia para uso local (fuera del directorio temporal de Archipelago)
        try:
            out_file_path_local = os.path.join(os.path.dirname(output_directory), filename)
            with open(out_file_path_local, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
            
        # 2. Copia segura para WebHost (dentro del zip)
        try:
            out_file_path_zip = os.path.join(output_directory, filename + ".json")
            with open(out_file_path_zip, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
