from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from BaseClasses import Item, ItemClassification, Location, MultiWorld, Region

from .Entrance import OOTEntrance
from .Hints import GossipText, HintArea
from .Items import OOTItem, item_table
from .Location import DisableType, OOTLocation
from .OcarinaSongs import Song
from .Options import OoTOptions
from .Regions import OOTRegion


OPTION_ATTRIBUTES = tuple(
    name
    for name in OoTOptions.type_hints
    if name not in {"plando_connections", "plandomized_locations"}
)


# These values are produced or normalized during generation and are read by
# patching, hints, cosmetics, music, or model patching after generation is done.
PATCH_RUNTIME_ATTRIBUTES = (
    "added_hint_types",
    "adult_trade_starting_inventory",
    "always_hints",
    "available_tokens",
    "barren_dungeon",
    "clearer_hints",
    "collectible_flag_offsets",
    "collectible_override_flags",
    "disable_trade_revert",
    "dungeon_mq",
    "empty_areas",
    "entrance_rando_reward_hints",
    "entrance_shuffle",
    "file_hash",
    "get_barren_hint_prev",
    "hint_dist_user",
    "hint_exclusions",
    "hint_text_overrides",
    "hint_type_overrides",
    "item_added_hint_types",
    "item_hint_type_overrides",
    "item_hints",
    "keysanity",
    "lacs_condition",
    "misc_hint_items",
    "misc_hint_locations",
    "model_adult",
    "model_adult_filepicker",
    "model_child",
    "model_child_filepicker",
    "mq_dungeons_random",
    "named_item_pool",
    "precompleted_dungeons",
    "randomized_starting_items",
    "required_locations",
    "scrub_prices",
    "selected_adult_trade_item",
    "shop_location_flags",
    "shop_prices",
    "shuffle_special_dungeon_entrances",
    "skip_child_zelda",
    "skipped_trials",
    "songs_as_items",
    "starting_items",
    "trials_random",
    "woth_dungeon",
)


PATCH_WORLD_ATTRIBUTES = tuple(dict.fromkeys((
    *OPTION_ATTRIBUTES,
    *PATCH_RUNTIME_ATTRIBUTES,
)))


@dataclass
class PatchForeignWorld:
    game: str | None


class PatchForeignItem(Item):
    game: str | None
    __slots__ = (
        "game",
        "type",
        "index",
        "special",
        "price",
        "market_price",
        "market_price_non_chu_drops_only",
        "looks_like_item",
    )

    def __init__(
        self,
        name: str,
        player: int,
        game: str | None,
        advancement: bool,
        useful: bool,
        trap: bool,
        type: str | None,
        index: int | None,
        special: dict[str, Any],
        price: int | None,
        market_price: int | None,
        market_price_non_chu_drops_only: bool,
    ):
        classification = ItemClassification.filler
        if advancement:
            classification |= ItemClassification.progression
        if useful:
            classification |= ItemClassification.useful
        if trap:
            classification |= ItemClassification.trap
        super().__init__(name, classification, None, player)
        self.game = game
        self.type = type
        self.index = index
        self.special = special
        self.price = price
        self.market_price = market_price
        self.market_price_non_chu_drops_only = market_price_non_chu_drops_only


def encode_seed_data(world) -> bytes:
    return json.dumps(build_seed_data(world), separators=(",", ":")).encode("utf-8")


def build_world_from_seed_data(data: bytes):
    from . import OOTWorld, _OOTDistribution
    from .Dungeon import Dungeon

    seed_data = json.loads(data.decode("utf-8"))
    multiworld = MultiWorld(seed_data["players"])
    multiworld.player_name = {int(player): name for player, name in seed_data["player_names"].items()}
    multiworld.game = {int(player): game for player, game in seed_data["games"].items()}

    world = OOTWorld(multiworld, seed_data["player"])
    multiworld.worlds = {
        player: world if player == world.player else PatchForeignWorld(seed_data["games"].get(str(player)))
        for player in multiworld.player_ids
    }

    world.random.setstate(restore_json_value(seed_data["random_state"]))
    world.hint_rng = world.random
    world.shortcut_regions = {
        name: bool(value) for name, value in seed_data.get("shortcut_regions", {}).items()
    }

    location_lookup = SeedLocationLookup()
    regions_by_name = restore_regions(world, multiworld, seed_data["regions"])
    world.dungeons = [
        Dungeon(world, dungeon["name"], dungeon.get("hint_text"), dungeon.get("font_color"))
        for dungeon in seed_data["dungeons"]
    ]
    restore_locations(world, regions_by_name, location_lookup, seed_data["locations"])
    restore_entrances(world, regions_by_name, seed_data["entrances"])
    restore_world_attributes(world, location_lookup, seed_data["world_attrs"])
    restore_foreign_filled_locations(multiworld, location_lookup, seed_data["filled_locations"], world.player)
    location_lookup.resolve_deferred_refs()

    multiworld.precollected_items = {
        int(player): [restore_item(item_data, location_lookup) for item_data in items]
        for player, items in seed_data["precollected_items"].items()
    }
    world.distribution = _OOTDistribution(world)
    return world


def build_seed_data(world) -> dict[str, Any]:
    player_ids = tuple(world.multiworld.get_all_ids())
    return {
        "version": 1,
        "player": world.player,
        "players": world.multiworld.players,
        "player_names": {str(player): world.multiworld.get_player_name(player) for player in player_ids},
        "games": {
            str(player): getattr(world.multiworld.worlds[player], "game", None)
            for player in player_ids
        },
        "random_state": serialize_json_value(world.random.getstate()),
        "world_attrs": serialize_world_attributes(world),
        "regions": [serialize_region(region) for region in world.multiworld.regions if region.player == world.player],
        "locations": [serialize_location(location) for location in world.get_locations()],
        "entrances": [serialize_entrance(entrance) for entrance in world.get_entrances()],
        "dungeons": [serialize_dungeon(dungeon) for dungeon in getattr(world, "dungeons", [])],
        "filled_locations": [
            serialize_filled_location(location)
            for location in world.multiworld.get_filled_locations()
        ],
        "precollected_items": {
            str(player): [serialize_item(item) for item in world.multiworld.precollected_items[player]]
            for player in player_ids
        },
        "shortcut_regions": {
            region.name: world.region_has_shortcuts(region.name)
            for region in world.multiworld.regions if region.player == world.player
        },
    }


def serialize_world_attributes(world) -> dict[str, Any]:
    attrs = {
        name: serialize_json_value(getattr(world, name))
        for name in PATCH_WORLD_ATTRIBUTES
        if hasattr(world, name)
    }
    attrs["song_notes"] = {name: str(song) for name, song in world.song_notes.items()}
    attrs["gossip_hints"] = {
        str(stone_id): serialize_gossip_text(gossip_text)
        for stone_id, gossip_text in world.gossip_hints.items()
    }
    attrs["hinted_dungeon_reward_locations"] = {
        reward: serialize_location_ref(location)
        for reward, location in world.hinted_dungeon_reward_locations.items()
    }
    attrs["misc_hint_item_locations"] = {
        hint_type: serialize_location_ref(location)
        for hint_type, location in getattr(world, "misc_hint_item_locations", {}).items()
    }
    attrs["misc_hint_location_items"] = {
        hint_type: serialize_item(item)
        for hint_type, item in getattr(world, "misc_hint_location_items", {}).items()
    }
    attrs["trap_appearances"] = [
        [location_id, serialize_item(item)]
        for location_id, item in getattr(world, "trap_appearances", {}).items()
    ]
    return attrs


def restore_world_attributes(world, location_lookup: "SeedLocationLookup", attrs: dict[str, Any]) -> None:
    special_attrs = {
        "song_notes",
        "gossip_hints",
        "hinted_dungeon_reward_locations",
        "misc_hint_item_locations",
        "misc_hint_location_items",
        "trap_appearances",
    }
    for name, value in attrs.items():
        if name not in special_attrs:
            setattr(world, name, restore_json_value(value))

    world.song_notes = {
        name: Song.from_str(song)
        for name, song in attrs["song_notes"].items()
    }
    world.gossip_hints = {
        int(stone_id): restore_gossip_text(gossip_text)
        for stone_id, gossip_text in attrs["gossip_hints"].items()
    }
    world.hinted_dungeon_reward_locations = {
        reward: restore_location_ref(location_lookup, location_ref)
        for reward, location_ref in attrs["hinted_dungeon_reward_locations"].items()
    }
    world.misc_hint_item_locations = {
        hint_type: restore_location_ref(location_lookup, location_ref)
        for hint_type, location_ref in attrs.get("misc_hint_item_locations", {}).items()
    }
    world.misc_hint_location_items = {
        hint_type: restore_item(item_data, location_lookup)
        for hint_type, item_data in attrs.get("misc_hint_location_items", {}).items()
    }
    world.trap_appearances = {
        int(location_id): restore_item(item_data, location_lookup)
        for location_id, item_data in attrs.get("trap_appearances", [])
    }


def serialize_region(region) -> dict[str, Any]:
    return {
        "name": region.name,
        "dungeon": region.dungeon.name if region.dungeon else None,
        "hint": serialize_hint_area(getattr(region, "hint", None)),
        "alt_hint": serialize_hint_area(getattr(region, "alt_hint", None)),
        "price": serialize_json_value(getattr(region, "price", None)),
        "time_passes": getattr(region, "time_passes", False),
        "provides_time": getattr(region, "provides_time", 0),
        "scene": serialize_json_value(getattr(region, "scene", None)),
        "pretty_name": getattr(region, "pretty_name", None),
        "font_color": getattr(region, "font_color", None),
        "is_boss_room": getattr(region, "is_boss_room", False),
    }


def restore_regions(world, multiworld: MultiWorld, regions_data: list[dict[str, Any]]) -> dict[str, OOTRegion]:
    regions_by_name = {}
    for region_data in regions_data:
        region = OOTRegion(region_data["name"], world.player, multiworld)
        region.scene = restore_json_value(region_data["scene"])
        region.price = restore_json_value(region_data["price"])
        region.time_passes = region_data["time_passes"]
        region.provides_time = region_data["provides_time"]
        region.pretty_name = region_data["pretty_name"]
        region.font_color = region_data["font_color"]
        region.is_boss_room = region_data["is_boss_room"]
        region.hint = restore_hint_area(region_data["hint"])
        region.alt_hint = restore_hint_area(region_data["alt_hint"])
        region.dungeon = region_data["dungeon"]
        regions_by_name[region.name] = region
        multiworld.regions.append(region)
    return regions_by_name


def serialize_location(location) -> dict[str, Any]:
    return {
        "name": location.name,
        "address": location.address,
        "address1": serialize_json_value(getattr(location, "address1", None)),
        "address2": serialize_json_value(getattr(location, "address2", None)),
        "default": serialize_json_value(getattr(location, "default", None)),
        "type": getattr(location, "type", None),
        "scene": serialize_json_value(getattr(location, "scene", None)),
        "internal": getattr(location, "internal", False),
        "vanilla_item": serialize_json_value(getattr(location, "vanilla_item", None)),
        "disabled": getattr(location, "disabled", DisableType.ENABLED).name,
        "locked": getattr(location, "_locked", False),
        "show_in_spoiler": getattr(location, "show_in_spoiler", True),
        "price": serialize_json_value(getattr(location, "price", None)),
        "parent_region": location.parent_region.name if location.parent_region else None,
        "item": serialize_item(location.item),
    }


def restore_locations(
    world,
    regions_by_name: dict[str, OOTRegion],
    location_lookup: "SeedLocationLookup",
    locations_data: list[dict[str, Any]],
) -> None:
    for location_data in locations_data:
        location = OOTLocation(
            world.player,
            location_data["name"],
            location_data["address"],
            restore_json_value(location_data["address1"]),
            restore_json_value(location_data["address2"]),
            restore_json_value(location_data["default"]),
            location_data["type"],
            restore_json_value(location_data["scene"]),
            parent=regions_by_name.get(location_data["parent_region"]),
            internal=location_data["internal"],
            vanilla_item=restore_json_value(location_data["vanilla_item"]),
        )
        location.disabled = DisableType[location_data["disabled"]]
        location._locked = location_data["locked"]
        location.show_in_spoiler = location_data["show_in_spoiler"]
        location.price = restore_json_value(location_data["price"])
        location.item = restore_item(location_data["item"], location_lookup)
        if location.item is not None:
            location.item.location = location
        location_lookup.register(location)
        if location.parent_region is not None:
            location.parent_region.locations.append(location)


def serialize_entrance(entrance) -> dict[str, Any]:
    return {
        "name": entrance.name,
        "type": getattr(entrance, "type", None),
        "shuffled": getattr(entrance, "shuffled", False),
        "data": serialize_json_value(getattr(entrance, "data", None)),
        "primary": getattr(entrance, "primary", False),
        "always": getattr(entrance, "always", False),
        "never": getattr(entrance, "never", False),
        "parent_region": entrance.parent_region.name if entrance.parent_region else None,
        "connected_region": entrance.connected_region.name if entrance.connected_region else None,
        "replaces": entrance.replaces.name if entrance.replaces else None,
        "reverse": entrance.reverse.name if entrance.reverse else None,
    }


def restore_entrances(
    world,
    regions_by_name: dict[str, OOTRegion],
    entrances_data: list[dict[str, Any]],
) -> None:
    entrances_by_name = {}
    for entrance_data in entrances_data:
        parent = regions_by_name.get(entrance_data["parent_region"])
        entrance = OOTEntrance(world.player, world.multiworld, entrance_data["name"], parent)
        entrance.type = entrance_data["type"]
        entrance.shuffled = entrance_data["shuffled"]
        entrance.data = restore_json_value(entrance_data["data"])
        entrance.primary = entrance_data["primary"]
        entrance.always = entrance_data["always"]
        entrance.never = entrance_data["never"]
        entrances_by_name[entrance.name] = entrance
        if parent is not None:
            parent.exits.append(entrance)

    for entrance_data in entrances_data:
        entrance = entrances_by_name[entrance_data["name"]]
        connected_region = entrance_data["connected_region"]
        if connected_region is not None:
            entrance.connected_region = regions_by_name[connected_region]
            entrance.connected_region.entrances.append(entrance)
        if entrance_data["replaces"] is not None:
            entrance.replaces = entrances_by_name[entrance_data["replaces"]]
        if entrance_data["reverse"] is not None:
            entrance.reverse = entrances_by_name[entrance_data["reverse"]]


def serialize_dungeon(dungeon) -> dict[str, Any]:
    return {
        "name": dungeon.name,
        "hint_text": getattr(dungeon, "hint_text", None),
        "font_color": getattr(dungeon, "font_color", None),
    }


def serialize_filled_location(location) -> dict[str, Any]:
    return {
        "name": location.name,
        "player": location.player,
        "game": getattr(location, "game", None),
        "item": serialize_item(location.item),
    }


def restore_foreign_filled_locations(
    multiworld: MultiWorld,
    location_lookup: "SeedLocationLookup",
    filled_locations_data: list[dict[str, Any]],
    oot_player: int,
) -> None:
    for location_data in filled_locations_data:
        if location_data["player"] == oot_player:
            continue
        region = get_foreign_region(multiworld, location_data["player"], location_data.get("game"))
        location = Location(location_data["player"], location_data["name"], parent=region)
        location.game = location_data.get("game")
        location.item = restore_item(location_data["item"], location_lookup)
        if location.item is not None:
            location.item.location = location
        region.locations.append(location)
        location_lookup.register(location)


def get_foreign_region(multiworld: MultiWorld, player: int, game: str | None) -> Region:
    region_name = f"{game or 'Foreign'} Patch Locations"
    try:
        return multiworld.get_region(region_name, player)
    except KeyError:
        region = Region(region_name, player, multiworld)
        multiworld.regions.append(region)
        return region


def serialize_item(item) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "name": item.name,
        "player": item.player,
        "game": getattr(item, "game", None),
        "advancement": item.advancement,
        "useful": item.useful,
        "trap": item.trap,
        "type": getattr(item, "type", None),
        "index": getattr(item, "index", None),
        "special": serialize_json_value(getattr(item, "special", {})),
        "price": serialize_json_value(getattr(item, "price", None)),
        "market_price": serialize_json_value(getattr(item, "market_price", None)),
        "market_price_non_chu_drops_only": getattr(item, "market_price_non_chu_drops_only", False),
        "looks_like_item": serialize_item(getattr(item, "looks_like_item", None)),
    }


def restore_item(item_data: dict[str, Any] | None, location_lookup: "SeedLocationLookup"):
    if item_data is None:
        return None
    if item_data["game"] == "Ocarina of Time" and item_data["name"] in item_table:
        item = OOTItem(item_data["name"], item_data["player"], item_table[item_data["name"]], False, False)
        item.index = item_data["index"]
        item.special = restore_json_value(item_data["special"])
        item.price = restore_json_value(item_data["price"])
        item.market_price = restore_json_value(item_data["market_price"])
        item.market_price_non_chu_drops_only = item_data["market_price_non_chu_drops_only"]
    else:
        item = PatchForeignItem(
            name=item_data["name"],
            player=item_data["player"],
            game=item_data["game"],
            advancement=item_data["advancement"],
            useful=item_data["useful"],
            trap=item_data["trap"],
            type=item_data["type"],
            index=item_data["index"],
            special=restore_json_value(item_data["special"]),
            price=restore_json_value(item_data["price"]),
            market_price=restore_json_value(item_data["market_price"]),
            market_price_non_chu_drops_only=item_data["market_price_non_chu_drops_only"],
        )
    if item.type == "DungeonReward" and item.index is None:
        item.index = item.special.get("gi_id")
    if item_data["looks_like_item"] is not None:
        item.looks_like_item = restore_item(item_data["looks_like_item"], location_lookup)
    return item


def serialize_location_ref(location) -> dict[str, Any] | None:
    if location is None:
        return None
    return {"name": location.name, "player": location.player}


def restore_location_ref(location_lookup: "SeedLocationLookup", location_ref: dict[str, Any] | None):
    if location_ref is None:
        return None
    return location_lookup.resolve(location_ref["name"], location_ref["player"])


class SeedLocationLookup:
    def __init__(self):
        self.locations_by_key: dict[tuple[int, str], Location] = {}
        self.deferred_refs: list[tuple[Location, str, int]] = []

    def register(self, location: Location) -> None:
        self.locations_by_key[(location.player, location.name)] = location

    def resolve(self, name: str, player: int) -> Location:
        location = self.locations_by_key.get((player, name))
        if location is not None:
            return location
        placeholder = Location(player, name)
        self.deferred_refs.append((placeholder, name, player))
        return placeholder

    def resolve_deferred_refs(self) -> None:
        for placeholder, name, player in self.deferred_refs:
            location = self.locations_by_key.get((player, name))
            if location is not None:
                placeholder.__dict__.update(location.__dict__)


def serialize_gossip_text(gossip_text: GossipText) -> dict[str, Any]:
    return gossip_text.to_json()


def restore_gossip_text(gossip_text_data: dict[str, Any]) -> GossipText:
    gossip_text = GossipText.__new__(GossipText)
    gossip_text.text = gossip_text_data["text"]
    gossip_text.colors = gossip_text_data["colors"]
    gossip_text.hinted_locations = gossip_text_data["hinted_locations"]
    gossip_text.hinted_items = gossip_text_data["hinted_items"]
    return gossip_text


def serialize_hint_area(hint_area: HintArea | None) -> str | None:
    return None if hint_area is None else hint_area.name


def restore_hint_area(hint_area_name: str | None) -> HintArea | None:
    return None if hint_area_name is None else HintArea[hint_area_name]


def serialize_json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return {"bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return {"bytearray": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, HintArea):
        return {"hint_area": value.name}
    if isinstance(value, tuple):
        return {"tuple": [serialize_json_value(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        return {"set": [serialize_json_value(item) for item in sorted(value, key=repr)]}
    if isinstance(value, list):
        return [serialize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(serialize_json_value(key)): serialize_json_value(item)
            for key, item in value.items()
        }
    raise TypeError(f"Cannot store {type(value)!r} in oot_seed.json")


def restore_json_value(value):
    if isinstance(value, list):
        return [restore_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"bytes"}:
        return base64.b64decode(value["bytes"])
    if set(value) == {"bytearray"}:
        return bytearray(base64.b64decode(value["bytearray"]))
    if set(value) == {"hint_area"}:
        return HintArea[value["hint_area"]]
    if set(value) == {"tuple"}:
        return tuple(restore_json_value(item) for item in value["tuple"])
    if set(value) == {"set"}:
        return set(restore_json_value(item) for item in value["set"])
    return {key: restore_json_value(item) for key, item in value.items()}
