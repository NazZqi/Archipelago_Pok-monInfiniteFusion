import typing
import json
import os
from . import components as components
from BaseClasses import Region, Entrance, Location, Item, Tutorial, ItemClassification
from NetUtils import Version
from worlds.AutoWorld import World, WebWorld
from .items import item_table, IFItemData
from .locations import location_table, IFLocationData
from Options import OptionError
from .options import PokemonIFOptions, Goal, Badges, HMs
from .rules import KANTO_BADGES

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
    
    badges_vanilla: bool
    hms_vanilla: bool

    def generate_early(self):
        name = self.player_name
        if self.options.goal.value != Goal.option_champion:
            raise OptionError(f"{name}: solo la meta 'champion' está implementada en el juego.")

        is_random = self.options.randomize_everything.value
        self.badges_vanilla = not is_random and self.options.badges.value == Badges.option_vanilla
        self.hms_vanilla = not is_random and self.options.hms.value == HMs.option_vanilla

        # Con npc_gifts los NPC que dan MOs se vuelven checks y dejan de darlas: con
        # MOs vanilla (fuera del pool) nadie las entregaría.
        if self.hms_vanilla and self.options.npc_gifts:
            raise OptionError(f"{name}: 'hms: vanilla' no es compatible con 'npc_gifts: true'.")

    def get_filler_item_name(self) -> str:
        return "Potion"
    def set_rules(self):
        from .rules import set_rules
        set_rules(self)

    def create_items(self):
        fillers_in_table = []
        useful_in_table = []
        items_added = 0

        for name, data in item_table.items():
            if data.code is not None:
                # Medallas y MOs vanilla las entrega el juego (eventos en regions.py)
                if self.badges_vanilla and name in KANTO_BADGES:
                    continue
                if self.hms_vanilla and name.startswith("HM") and len(name) == 4 and name[2:].isdigit():
                    continue
                    
                if data.classification == ItemClassification.filler:
                    fillers_in_table.append(name)
                elif data.classification == ItemClassification.useful:
                    useful_in_table.append(name)
                else:
                    self.multiworld.itempool.append(self.create_item(name))
                    items_added += 1

        # Rellenar ubicaciones calculando matemáticamente las ubicaciones restantes
        my_locations = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        locations_count = len(my_locations)

        # Con pocas ubicaciones (solo npc_gifts) los útiles entran hasta donde quepan
        self.random.shuffle(useful_in_table)
        for name in useful_in_table[:max(0, locations_count - items_added)]:
            self.multiworld.itempool.append(self.create_item(name))
            items_added += 1

        filler_amount = locations_count - items_added
        
        if filler_amount < 0:
            raise Exception(f"Not enough locations for required items! Locations: {locations_count}, Required Items: {items_added}")
        
        # Para dar variedad, intentamos añadir al menos 1 de cada filler de la tabla, y luego aleatorio
        self.random.shuffle(fillers_in_table)

        if filler_amount > 0:
            for i in range(filler_amount):
                if i < len(fillers_in_table):
                    filler_choice = fillers_in_table[i]
                else:
                    filler_choice = self.random.choice(fillers_in_table) if fillers_in_table else "Potion"
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
            "key_items": True if is_random else self.options.key_items.value,
            "overworld_items": True if is_random else self.options.overworld_items.value,
            "hidden_items": True if is_random else self.options.hidden_items.value,
            "npc_gifts": True if is_random else self.options.npc_gifts.value,
            "fusion_items": True if is_random else self.options.fusion_items.value,
            "dexsanity": True if is_random else self.options.dexsanity.value,
            "trainersanity": True if is_random else self.options.trainersanity.value,
            "item_pool_type": self.options.item_pool_type.value,
            "elite_four_requirement": self.options.elite_four_requirement.value,
            "elite_four_count": self.options.elite_four_count.value,
            "cerulean_cave_requirement": self.options.cerulean_cave_requirement.value,
            "cerulean_cave_count": self.options.cerulean_cave_count.value,
            "require_itemfinder": self.options.require_itemfinder.value,
            "require_flash": self.options.require_flash.value,
            "force_fully_evolved": self.options.force_fully_evolved.value,
            "fusion_randomization": 3 if is_random else self.options.fusion_randomization.value,
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
