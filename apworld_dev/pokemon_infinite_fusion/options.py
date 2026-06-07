from dataclasses import dataclass
from Options import Toggle, PerGameCommonOptions

class RandomizeHiddenItems(Toggle):
    """Include hidden items in the randomization pool."""
    display_name = "Randomize Hidden Items"
    default = 1

class RandomizeStarters(Toggle):
    """Randomize the starter Pokemon."""
    display_name = "Randomize Starters"
    default = 1

@dataclass
class PokemonIFOptions(PerGameCommonOptions):
    randomize_hidden_items: RandomizeHiddenItems
    randomize_starters: RandomizeStarters
