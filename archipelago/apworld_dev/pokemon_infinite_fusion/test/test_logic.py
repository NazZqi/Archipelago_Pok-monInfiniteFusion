from . import PokemonIFTestBase
from .. import client
from ..locations import location_table
from ..rules import KANTO_BADGES


class TestDefault(PokemonIFTestBase):
    def test_kanto_fallback_is_endgame(self):
        self.assertFalse(self.can_reach_region("Kanto Fallback"))

    def test_route_23_needs_all_badges(self):
        self.collect_by_name(["HM03"] + [b for b in KANTO_BADGES if b != "Earth Badge"])
        self.assertFalse(self.can_reach_region("Route 23"))
        self.collect_by_name("Earth Badge")
        self.assertTrue(self.can_reach_region("Route 23"))


class TestVanilla(PokemonIFTestBase):
    options = {"badges": "vanilla", "hms": "vanilla"}

    def test_badges_and_hms_are_events(self):
        pool = {item.name for item in self.multiworld.itempool}
        for name in KANTO_BADGES + ["HM01", "HM03", "HM04", "HM05"]:
            self.assertNotIn(name, pool)
        self.assertEqual(self.multiworld.get_location("Pewter Gym", 1).item.name, "Boulder Badge")


class TestRandomizeEverything(PokemonIFTestBase):
    options = {"randomize_everything": True}


class TestOnlyNpcGifts(PokemonIFTestBase):
    # Menos ubicaciones que ítems no-relleno: los útiles entran hasta donde quepan
    options = {"overworld_items": False, "npc_gifts": True}


class TestLocationTables(PokemonIFTestBase):
    def test_each_event_has_one_location(self):
        # Un evento con varias ubicaciones deja las últimas sin poder marcarse
        self.assertTrue(all(len(ids) == 1 for ids in client.LOCATION_MAPPING.values()))

    def test_mapping_matches_locations(self):
        mapped = {ap_id for ids in client.LOCATION_MAPPING.values() for ap_id in ids}
        self.assertEqual(mapped, {data.code for data in location_table.values()})
