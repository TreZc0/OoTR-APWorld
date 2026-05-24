class Dungeon(object):

    def __init__(self, world, name, hint, font_color):

        self.world = world
        self.name = name
        self.hint_text = hint
        self.font_color = font_color
        self.regions = []
        self.boss_key = []
        self.small_keys = []
        self.maps = []
        self.compasses = []
        self.silver_rupees = []

        for region in world.multiworld.regions:
            if region.player == world.player and region.dungeon == self.name:
                region.dungeon = self
                self.regions.append(region)


    def copy(self, new_world):
        new_dungeon = Dungeon(new_world, self.name, self.hint_text, self.font_color)
        new_dungeon.boss_key = [item.copy(new_world) for item in self.boss_key]
        new_dungeon.small_keys = [item.copy(new_world) for item in self.small_keys]
        new_dungeon.maps = [item.copy(new_world) for item in self.maps]
        new_dungeon.compasses = [item.copy(new_world) for item in self.compasses]
        new_dungeon.silver_rupees = [item.copy(new_world) for item in self.silver_rupees]

        return new_dungeon


    @property
    def keys(self):
        return self.small_keys + self.boss_key


    @property
    def shuffle_map(self):
        return self.world.shuffle_map

    @property
    def shuffle_compass(self):
        return self.world.shuffle_compass


    @property
    def shuffle_smallkeys(self):
        return self.world.shuffle_smallkeys


    @property
    def shuffle_bosskeys(self):
        if self.name == 'Ganons Castle':
            return self.world.shuffle_ganon_bosskey
        return self.world.shuffle_bosskeys


    @property
    def shuffle_silver_rupees(self):
        return self.world.shuffle_silver_rupees


    @property
    def precompleted(self):
        return self.world.precompleted_dungeons.get(self.name, False)


    @property
    def dungeon_items(self):
        return self.maps + self.compasses


    @property
    def all_items(self):
        return self.maps + self.compasses + self.keys + self.silver_rupees


    def is_dungeon_item(self, item):
        return item.name in [dungeon_item.name for dungeon_item in self.all_items] or item.name in self.get_silver_rupee_names()


    def get_silver_rupee_names(self):
        from .Items import item_table

        return {name for name, data in item_table.items()
                if data[0] == 'SilverRupee' and self.name in name}


    def item_name(self, name):
        return f"{name} ({self.name})"


    def get_restricted_dungeon_items(self):
        if self.shuffle_map == 'dungeon' or (self.precompleted and self.shuffle_map in ('any_dungeon', 'overworld', 'keysanity', 'regional')):
            yield from self.maps
        if self.shuffle_compass == 'dungeon' or (self.precompleted and self.shuffle_compass in ('any_dungeon', 'overworld', 'keysanity', 'regional')):
            yield from self.compasses
        if self.shuffle_smallkeys == 'dungeon' or (self.precompleted and self.shuffle_smallkeys in ('any_dungeon', 'overworld', 'keysanity', 'regional')):
            yield from self.small_keys
        if self.shuffle_bosskeys == 'dungeon' or (self.precompleted and self.shuffle_bosskeys in ('any_dungeon', 'overworld', 'keysanity', 'regional')):
            yield from self.boss_key
        if self.shuffle_silver_rupees == 'dungeon' or (self.precompleted and self.shuffle_silver_rupees in ('any_dungeon', 'overworld', 'anywhere', 'regional')):
            yield from self.silver_rupees


    def get_unrestricted_dungeon_items(self):
        if self.precompleted:
            return
        if self.shuffle_map in ('any_dungeon', 'overworld', 'keysanity', 'regional'):
            yield from self.maps
        if self.shuffle_compass in ('any_dungeon', 'overworld', 'keysanity', 'regional'):
            yield from self.compasses
        if self.shuffle_smallkeys in ('any_dungeon', 'overworld', 'keysanity', 'regional'):
            yield from self.small_keys
        if self.shuffle_bosskeys in ('any_dungeon', 'overworld', 'keysanity', 'regional'):
            yield from self.boss_key
        if self.shuffle_silver_rupees in ('any_dungeon', 'overworld', 'anywhere', 'regional'):
            yield from self.silver_rupees


    def __str__(self):
        return str(self.__unicode__())


    def __unicode__(self):
        return '%s' % self.name
