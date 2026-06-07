from BaseClasses import ItemClassification
from typing import Dict, NamedTuple

class IFItemData(NamedTuple):
    code: int
    classification: ItemClassification

item_table: Dict[str, IFItemData] = {
    "Boulder Badge": IFItemData(2660000, ItemClassification.progression),
    "Cascade Badge": IFItemData(2660001, ItemClassification.progression),
    "Thunder Badge": IFItemData(2660002, ItemClassification.progression),
    "Rainbow Badge": IFItemData(2660003, ItemClassification.progression),
    "Soul Badge": IFItemData(2660004, ItemClassification.progression),
    "Marsh Badge": IFItemData(2660005, ItemClassification.progression),
    "Volcano Badge": IFItemData(2660006, ItemClassification.progression),
    "Earth Badge": IFItemData(2660007, ItemClassification.progression),
    "HM01 Cut": IFItemData(2660100, ItemClassification.progression),
    "HM02 Fly": IFItemData(2660101, ItemClassification.progression),
    "HM03 Surf": IFItemData(2660102, ItemClassification.progression),
    "HM04 Strength": IFItemData(2660103, ItemClassification.progression),
    "HM05 Flash": IFItemData(2660104, ItemClassification.progression),
    "Potion": IFItemData(2660200, ItemClassification.filler),
    "Poke Ball": IFItemData(2660201, ItemClassification.filler),
    "Rare Candy": IFItemData(2660202, ItemClassification.useful),
}
