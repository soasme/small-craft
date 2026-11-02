"""The block types, what the player can build, and which
texture tile shows on each face."""

(EMPTY, GRASS, SAND, STONE, BRICK, WOOD, CEMENT, DIRT, PLANK, SNOW, GLASS,
 COBBLE, LIGHT_STONE, DARK_STONE, CHEST, LEAVES, CLOUD, TALL_GRASS,
 YELLOW_FLOWER, RED_FLOWER, PURPLE_FLOWER, SUN_FLOWER, WHITE_FLOWER,
 BLUE_FLOWER) = range(24)
COLOR_00 = 32  # the 32 colors run from 32 to 63

# What the player can build, in the order 1-9, E and R step through.
ITEMS = [*range(GRASS, CLOUD), *range(TALL_GRASS, BLUE_FLOWER + 1), *range(COLOR_00, COLOR_00 + 32)]

# Tiles of the texture atlas, by block: (left, right, top, bottom, front, back).
BLOCKS = [
    (0, 0, 0, 0, 0, 0),  # empty
    (16, 16, 32, 0, 16, 16),  # grass
    (1,) * 6, (2,) * 6, (3,) * 6,  # sand, stone, brick
    (20, 20, 36, 4, 20, 20),  # wood
    (5,) * 6, (6,) * 6, (7,) * 6,  # cement, dirt, plank
    (24, 24, 40, 8, 24, 24),  # snow
    *[(t,) * 6 for t in range(9, 16)],  # glass ... cloud
    *[(0,) * 6] * 15,  # plants (see PLANTS) and unused
    *[(176 + i,) * 6 for i in range(32)],  # colors
]
# The tile of each plant, drawn as two crossed quads.
PLANTS = {TALL_GRASS: 48, YELLOW_FLOWER: 49, RED_FLOWER: 50, PURPLE_FLOWER: 51,
          SUN_FLOWER: 52, WHITE_FLOWER: 53, BLUE_FLOWER: 54}


def is_plant(w):
    return w in PLANTS


def is_obstacle(w):
    return not (w in PLANTS or w == EMPTY or w == CLOUD)


def is_transparent(w):
    return w in PLANTS or w == EMPTY or w == GLASS or w == LEAVES


def is_destructable(w):
    return not (w == EMPTY or w == CLOUD)


# Byte tables for bytes.translate: 1 where a block hides its neighbours' faces.
OPAQUE = bytes(0 if is_transparent(w) else 1 for w in range(256))
