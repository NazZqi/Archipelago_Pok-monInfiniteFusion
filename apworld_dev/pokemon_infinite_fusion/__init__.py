import typing

from BaseClasses import Region, Entrance, Location, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, WebWorld
from .items import item_table, IFItemData
from .locations import location_table, IFLocationData
from .options import PokemonIFOptions

class PokemonIFWeb(WebWorld):
    theme = "ocean"
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

    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = {name: data.code for name, data in location_table.items()}
    
    def create_items(self):
        # 1. Añadir ítems de progresión (Medallas, HMs)
        for name, data in item_table.items():
            if data.classification != ItemClassification.filler:
                self.multiworld.itempool.append(self.create_item(name))
            
        # 2. Rellenar el resto de ubicaciones con items básicos
        locations_count = len(self.multiworld.get_unfilled_locations(self.player))
        items_count = len(self.multiworld.itempool)
        
        while items_count < locations_count:
            self.multiworld.itempool.append(self.create_item("Potion"))
            items_count += 1

    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        kanto = Region("Kanto", self.player, self.multiworld)
        menu.connect(kanto)
        
        # Añadir las 864 ubicaciones a la región base
        for location_name, loc_data in location_table.items():
            loc = Location(self.player, location_name, loc_data.code, kanto)
            kanto.locations.append(loc)
            
        self.multiworld.regions.append(menu)
        self.multiworld.regions.append(kanto)

    def create_item(self, name: str) -> Item:
        item_data = item_table[name]
        return Item(name, item_data.classification, item_data.code, self.player)
