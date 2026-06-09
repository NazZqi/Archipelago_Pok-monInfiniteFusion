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

class PokemonIFWorld(World):
    """
    Pokemon Infinite Fusion Randomizer
    Explore Kanto and Johto with fused Pokemon!
    """
    game = "Pokemon Infinite Fusion"
    web = PokemonIFWeb()
    options_dataclass = PokemonIFOptions
    version = Version(1, 0, 0)

    item_name_to_id = {name: data.code for name, data in item_table.items() if data.code is not None}
    location_name_to_id = {name: data.code for name, data in location_table.items() if data.code is not None}
    
    def get_filler_item_name(self) -> str:
        return "Potion"
    def set_rules(self):
        from .rules import set_rules
        set_rules(self)
    
    def create_items(self):
        fillers_in_table = []
        items_added = 0
        
        # Opciones
        skip_hms = (self.options.hms.value == 0) and not self.options.randomize_everything.value
        
        for name, data in item_table.items():
            if data.code is not None:
                # Omitir HMs si están en modo vanilla
                if skip_hms and name.startswith("HM") and len(name) == 4 and name[2:].isdigit():
                    continue
                    
                if data.classification == ItemClassification.filler:
                    fillers_in_table.append(name)
                else:
                    self.multiworld.itempool.append(self.create_item(name))
                    items_added += 1
            
        # Rellenar ubicaciones calculando matemáticamente las ubicaciones restantes
        my_locations = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        locations_count = len(my_locations)
        
        filler_amount = locations_count - items_added
        
        if filler_amount < 0:
            raise Exception(f"Not enough locations for required items! Locations: {locations_count}, Required Items: {items_added}")
        
        # Para dar variedad, intentamos añadir al menos 1 de cada filler de la tabla, y luego aleatorio
        self.multiworld.random.shuffle(fillers_in_table)
        
        if filler_amount > 0:
            for i in range(filler_amount):
                if i < len(fillers_in_table):
                    filler_choice = fillers_in_table[i]
                else:
                    filler_choice = self.multiworld.random.choice(fillers_in_table) if fillers_in_table else "Potion"
                self.multiworld.itempool.append(self.create_item(filler_choice))


    def create_regions(self):
        from .regions import create_regions
        create_regions(self)


    def fill_slot_data(self) -> dict:
        is_random = self.options.randomize_everything.value
        
        return {
            "randomize_everything": is_random,
            "goal": self.options.goal.value,
            "badges": 2 if is_random else self.options.badges.value,
            "hms": 2 if is_random else self.options.hms.value,
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
            "wild_pokemon": 4 if is_random else self.options.wild_pokemon.value,
            "starters": 3 if is_random else self.options.starters.value,
            "trainer_parties": 3 if is_random else self.options.trainer_parties.value,
            "force_fully_evolved": self.options.force_fully_evolved.value,
            "legendary_encounters": 3 if is_random else self.options.legendary_encounters.value,
            "fusion_randomization": 3 if is_random else self.options.fusion_randomization.value,
            "types": 2 if is_random else self.options.types.value,
            "abilities": 1 if is_random else self.options.abilities.value,
            "level_up_moves": 1 if is_random else self.options.level_up_moves.value,
            "tm_tutor_compatibility": self.options.tm_tutor_compatibility.value,
            "hm_compatibility": self.options.hm_compatibility.value,
            "tm_tutor_moves": True if is_random else self.options.tm_tutor_moves.value,
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
            "music": True if is_random else self.options.music.value,
            "fanfares": True if is_random else self.options.fanfares.value,
            "wild_encounter_blacklist": list(self.options.wild_encounter_blacklist.value),
            "starter_blacklist": list(self.options.starter_blacklist.value),
            "ability_blacklist": list(self.options.ability_blacklist.value),
            "move_blacklist": list(self.options.move_blacklist.value),
            "allowed_legendary_hunt_encounters": list(self.options.allowed_legendary_hunt_encounters.value),
        }

    def create_item(self, name: str) -> Item:
        item_data = item_table[name]
        return Item(name, item_data.classification, item_data.code, self.player)

    def create_event(self, name: str) -> Item:
        return Item(name, ItemClassification.progression_skip_balancing, None, self.player)

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
        
        # Escribimos el archivo .apif en el output_directory.
        # No le ponemos extensión .json para evitar que el WebHost de Archipelago intente parsearlo como data de slot y crashee (Error 500).
        out_file_path = os.path.join(output_directory, filename)
        try:
            with open(out_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
