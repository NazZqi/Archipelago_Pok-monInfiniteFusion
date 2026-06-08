from dataclasses import dataclass
from Options import Choice, Range, Toggle, OptionSet, OptionList, PerGameCommonOptions

class Goal(Choice):
    """Determines what your goal is to consider the game beaten."""
    display_name = "Goal"
    option_champion = 0
    option_cerulean_cave = 1
    option_fusion_master = 2
    option_legendary_hunt = 3
    default = 0

class Badges(Choice):
    """Adds Badges to the pool."""
    display_name = "Badges"
    option_vanilla = 0
    option_shuffle = 1
    option_completely_random = 2
    default = 2

class HMs(Choice):
    """Adds HMs to the pool."""
    display_name = "HMs"
    option_vanilla = 0
    option_shuffle = 1
    option_completely_random = 2
    default = 2

class KeyItems(Toggle):
    """Adds most key items to the pool."""
    display_name = "Key Items"
    default = 1

class OverworldItems(Toggle):
    """Adds items on the ground with a Pokeball sprite to the pool."""
    display_name = "Overworld Items"
    default = 1

class HiddenItems(Toggle):
    """Adds hidden items to the pool."""
    display_name = "Hidden Items"
    default = 0

class NpcGifts(Toggle):
    """Adds most gifts received from NPCs to the pool."""
    display_name = "NPC Gifts"
    default = 0

class FusionItems(Toggle):
    """Adds fusion-related items to the pool."""
    display_name = "Fusion Items"
    default = 1

class Dexsanity(Toggle):
    """Adding a 'caught' pokedex entry gives you an item."""
    display_name = "Dexsanity"
    default = 0

class Trainersanity(Toggle):
    """Defeating a trainer gives you an item."""
    display_name = "Trainersanity"
    default = 0

class ItemPoolType(Choice):
    """Determines which non-progression items get put into the item pool."""
    display_name = "Item Pool Type"
    option_shuffled = 0
    option_diverse_balanced = 1
    option_diverse = 2
    default = 0

class EliteFourRequirement(Choice):
    """Sets the requirements to challenge the elite four."""
    display_name = "Elite Four Requirement"
    option_badges = 0
    option_gyms = 1
    default = 0

class EliteFourCount(Range):
    """Sets the number of badges/gyms required to challenge the elite four."""
    display_name = "Elite Four Count"
    range_start = 0
    range_end = 8
    default = 8

class CeruleanCaveRequirement(Choice):
    """Sets the requirements to access Cerulean Cave."""
    display_name = "Cerulean Cave Requirement"
    option_badges = 0
    option_gyms = 1
    option_none = 2
    default = 0

class CeruleanCaveCount(Range):
    """Sets the number of badges/gyms required to access Cerulean Cave."""
    display_name = "Cerulean Cave Count"
    range_start = 0
    range_end = 8
    default = 8

class RequireItemfinder(Toggle):
    """The Itemfinder is logically required to pick up hidden items."""
    display_name = "Require Itemfinder"
    default = 1

class RequireFlash(Choice):
    """Determines whether HM05 Flash is logically required to navigate a dark cave in Kanto."""
    display_name = "Require Flash"
    option_neither = 0
    option_only_rock_tunnel = 1
    option_only_victory_road = 2
    option_both = 3
    default = 3

class WildPokemon(Choice):
    """Randomizes wild pokemon encounters."""
    display_name = "Wild Pokemon"
    option_vanilla = 0
    option_match_base_stats = 1
    option_match_type = 2
    option_match_base_stats_and_type = 3
    option_completely_random = 4
    default = 0

class WildEncounterBlacklist(OptionSet):
    """Prevents listed species from appearing in the wild when wild encounters are randomized."""
    display_name = "Wild Encounter Blacklist"

class Starters(Choice):
    """Randomizes the starter pokemon."""
    display_name = "Starters"
    option_vanilla = 0
    option_match_base_stats = 1
    option_match_type = 2
    option_completely_random = 3
    default = 0

class StarterBlacklist(OptionSet):
    """Prevents listed species from appearing as starters when starters are randomized."""
    display_name = "Starter Blacklist"

class TrainerParties(Choice):
    """Randomizes the parties of all trainers."""
    display_name = "Trainer Parties"
    option_vanilla = 0
    option_match_base_stats = 1
    option_match_type = 2
    option_completely_random = 3
    default = 0

class ForceFullyEvolved(Range):
    """Restricts the species to only fully evolved pokemon at this level or higher."""
    display_name = "Force Fully Evolved"
    range_start = 1
    range_end = 100
    default = 100

class LegendaryEncounters(Choice):
    """Randomizes legendary encounters."""
    display_name = "Legendary Encounters"
    option_vanilla = 0
    option_shuffle = 1
    option_match_base_stats = 2
    option_completely_random = 3
    default = 0

class FusionRandomization(Choice):
    """Controls whether trainer and wild Pokemon fusions are randomized."""
    display_name = "Fusion Randomization"
    option_none = 0
    option_random_head = 1
    option_random_body = 2
    option_completely_random = 3
    default = 0

class Types(Choice):
    """Randomizes the type(s) of every pokemon."""
    display_name = "Types"
    option_vanilla = 0
    option_shuffle = 1
    option_completely_random = 2
    option_follow_evolutions = 3
    default = 0

class Abilities(Choice):
    """Randomizes abilities of every species."""
    display_name = "Abilities"
    option_vanilla = 0
    option_completely_random = 1
    option_follow_evolutions = 2
    default = 0

class AbilityBlacklist(OptionSet):
    """Prevent species from being given these abilities."""
    display_name = "Ability Blacklist"

class LevelUpMoves(Choice):
    """Randomizes the moves a pokemon learns."""
    display_name = "Level Up Moves"
    option_vanilla = 0
    option_randomized = 1
    option_start_with_four_moves = 2
    default = 0

class TmTutorCompatibility(Range):
    """Sets the percent chance that a given TM or move tutor is compatible with a species."""
    display_name = "TM Tutor Compatibility"
    range_start = -1
    range_end = 100
    default = -1
    special_range_names = {
        "vanilla": -1,
        "full": 100
    }

class HmCompatibility(Range):
    """Sets the percent chance that a given HM is compatible with a species."""
    display_name = "HM Compatibility"
    range_start = -1
    range_end = 100
    default = -1
    special_range_names = {
        "vanilla": -1,
        "full": 100
    }

class TmTutorMoves(Toggle):
    """Randomizes the moves taught by TMs and move tutors."""
    display_name = "TM Tutor Moves"
    default = 0

class ReusableTmsTutors(Toggle):
    """Sets TMs to not break after use and move tutors to infinite use."""
    display_name = "Reusable TMs and Tutors"
    default = 0

class MoveBlacklist(OptionSet):
    """Prevents species from learning these moves."""
    display_name = "Move Blacklist"

class MinCatchRate(Range):
    """Sets the minimum catch rate a pokemon can have."""
    display_name = "Min Catch Rate"
    range_start = 3
    range_end = 255
    default = 3

class GuaranteedCatch(Toggle):
    """Every throw is guaranteed to catch a wild pokemon."""
    display_name = "Guaranteed Catch"
    default = 0

class ExpModifier(Range):
    """Multiplies gained experience by a percentage."""
    display_name = "EXP Modifier"
    range_start = 0
    range_end = 1000
    default = 100

class BlindTrainers(Toggle):
    """Trainers will not start a battle with you unless you talk to them."""
    display_name = "Blind Trainers"
    default = 0

class MatchTrainerLevels(Choice):
    """Your party's levels will match the trainer's highest level pokemon."""
    display_name = "Match Trainer Levels"
    option_off = 0
    option_additive = 1
    option_multiplicative = 2
    default = 0

class MatchTrainerLevelsBonus(Range):
    """A level bonus/penalty applied to your team when matching an opponent's levels."""
    display_name = "Match Trainer Levels Bonus"
    range_start = -100
    range_end = 100
    default = 0

class DoubleBattleChance(Range):
    """The percent chance that a trainer battle is converted into a double battle."""
    display_name = "Double Battle Chance"
    range_start = 0
    range_end = 100
    default = 0

class BetterShops(Toggle):
    """Pokemarts sell every item."""
    display_name = "Better Shops"
    default = 0

class TurboA(Toggle):
    """Holding A will advance most text automatically."""
    display_name = "Turbo A"
    default = 0

class ReceiveItemMessages(Choice):
    """Determines whether you receive an in-game notification when receiving an item."""
    display_name = "Receive Item Messages"
    option_all = 0
    option_progression = 1
    option_none = 2
    default = 0

class RemoteItems(Toggle):
    """All items are received from the server."""
    display_name = "Remote Items"
    default = 0

class AllowTripleFusions(Toggle):
    """Permits triple fusions in the game if supported."""
    display_name = "Allow Triple Fusions"
    default = 0

class FusionSpriteStyle(Choice):
    """Controls the visual style of the fusion sprites used in the game."""
    display_name = "Fusion Sprite Style"
    option_custom = 0
    option_generated = 1
    option_vanilla_only = 2
    default = 0

class NpcFusionReveal(Toggle):
    """NPCs can reveal in-game hints or information about optimal fusions."""
    display_name = "NPC Fusion Reveal"
    default = 1

class LegendaryHuntCount(Range):
    """Number of legendaries that must be caught/defeated for the Legendary Hunt goal."""
    display_name = "Legendary Hunt Count"
    range_start = 1
    range_end = 10
    default = 3

class AllowedLegendaryHuntEncounters(OptionSet):
    """Sets which Kanto legendary encounters can contribute to the Legendary Hunt goal."""
    display_name = "Allowed Legendary Hunt Encounters"
    default = frozenset(['Articuno', 'Zapdos', 'Moltres', 'Mewtwo', 'Mew'])

class DeathLink(Toggle):
    """When you die, everyone who enabled death link dies. The reverse is true too."""
    display_name = "Death Link"
    default = 0

class EnableWonderTrading(Toggle):
    """Allows participation in wonder trading with other players in your current multiworld."""
    display_name = "Enable Wonder Trading"
    default = 1

class Music(Toggle):
    """Shuffles music played in any situation where it loops."""
    display_name = "Music"
    default = 0

class Fanfares(Toggle):
    """Shuffles fanfares for item pickups, healing at the pokecenter, etc."""
    display_name = "Fanfares"
    default = 0

@dataclass
class PokemonIFOptions(PerGameCommonOptions):
    goal: Goal
    badges: Badges
    hms: HMs
    key_items: KeyItems
    overworld_items: OverworldItems
    hidden_items: HiddenItems
    npc_gifts: NpcGifts
    fusion_items: FusionItems
    dexsanity: Dexsanity
    trainersanity: Trainersanity
    item_pool_type: ItemPoolType
    elite_four_requirement: EliteFourRequirement
    elite_four_count: EliteFourCount
    cerulean_cave_requirement: CeruleanCaveRequirement
    cerulean_cave_count: CeruleanCaveCount
    require_itemfinder: RequireItemfinder
    require_flash: RequireFlash
    wild_pokemon: WildPokemon
    wild_encounter_blacklist: WildEncounterBlacklist
    starters: Starters
    starter_blacklist: StarterBlacklist
    trainer_parties: TrainerParties
    force_fully_evolved: ForceFullyEvolved
    legendary_encounters: LegendaryEncounters
    fusion_randomization: FusionRandomization
    types: Types
    abilities: Abilities
    ability_blacklist: AbilityBlacklist
    level_up_moves: LevelUpMoves
    tm_tutor_compatibility: TmTutorCompatibility
    hm_compatibility: HmCompatibility
    tm_tutor_moves: TmTutorMoves
    reusable_tms_tutors: ReusableTmsTutors
    move_blacklist: MoveBlacklist
    min_catch_rate: MinCatchRate
    guaranteed_catch: GuaranteedCatch
    exp_modifier: ExpModifier
    blind_trainers: BlindTrainers
    match_trainer_levels: MatchTrainerLevels
    match_trainer_levels_bonus: MatchTrainerLevelsBonus
    double_battle_chance: DoubleBattleChance
    better_shops: BetterShops
    turbo_a: TurboA
    receive_item_messages: ReceiveItemMessages
    remote_items: RemoteItems
    allow_triple_fusions: AllowTripleFusions
    fusion_sprite_style: FusionSpriteStyle
    npc_fusion_reveal: NpcFusionReveal
    legendary_hunt_count: LegendaryHuntCount
    allowed_legendary_hunt_encounters: AllowedLegendaryHuntEncounters
    death_link: DeathLink
    enable_wonder_trading: EnableWonderTrading
    music: Music
    fanfares: Fanfares
