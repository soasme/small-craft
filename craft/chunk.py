"""A chunk: a 32 x 32 column of the world and its mesh.

Its blocks are one bytearray with a byte for each block, layer by layer
from the ground up, covering one block beyond each side so the chunk can
tell which faces show without its neighbours. A neighbour is one index
away, and bytes.translate finds every opaque block at C speed."""
from noise import simplex2
from .config import CHUNK_SIZE
from .cube import make_cube, make_plant
from .item import OPAQUE, PLANTS

S = CHUNK_SIZE + 2  # blocks along a side, with the border
L = S * S  # blocks in a layer
HEADROOM = 10  # empty layers kept above the highest block


class Chunk:
    def __init__(self, p, q):
        self.p, self.q = p, q
        self.x0, self.z0 = p * CHUNK_SIZE - 1, q * CHUNK_SIZE - 1
        self.blocks = bytearray(L * HEADROOM)
        self.mesh = None
        self.faces = 0
        self.miny, self.maxy = 0, 0
        self.dirty = True
        self.version = 0  # counts the changes that call for a new mesh

    def touch(self):
        """Mark the mesh out of date."""
        self.dirty = True
        self.version += 1

    def index(self, x, y, z):
        """Where block (x, y, z) is in blocks, or -1 outside this chunk.
        Layer 0 lies below the world, so every block has one beneath it."""
        dx, dz = x - self.x0, z - self.z0
        if 0 <= dx < S and 0 <= dz < S and 0 <= y < 256:
            return (y + 1) * L + dx * S + dz
        return -1

    def get(self, x, y, z):
        i = self.index(x, y, z)
        return self.blocks[i] if 0 <= i < len(self.blocks) else 0

    def set(self, x, y, z, w):
        """Store w at (x, y, z); return whether the block changed."""
        i = self.index(x, y, z)
        if i < 0:
            return False
        self.reserve(y)
        if self.blocks[i] == w:
            return False
        self.blocks[i] = w
        return True

    def fill(self, x, z, h, w):
        """Fill blocks 0 to h - 1 of column (x, z) with w."""
        i = self.index(x, 0, z)
        if i >= 0 and h > 0:
            self.reserve(h - 1)
            self.blocks[i:i + h * L:L] = bytes((w,)) * h

    def reserve(self, y):
        need = (y + 1 + HEADROOM) * L
        if len(self.blocks) < need:
            self.blocks += bytes(need - len(self.blocks))


# The 27 blocks around and including a block are numbered with x, y and z
# each running -1, 0, 1, z fastest.
# For each face and corner: the corner neighbour and the two side neighbours
# that darken it, then the four neighbours whose shade and light it averages.
LOOKUP3 = (
    ((0, 1, 3), (2, 1, 5), (6, 3, 7), (8, 5, 7)),
    ((18, 19, 21), (20, 19, 23), (24, 21, 25), (26, 23, 25)),
    ((6, 7, 15), (8, 7, 17), (24, 15, 25), (26, 17, 25)),
    ((0, 1, 9), (2, 1, 11), (18, 9, 19), (20, 11, 19)),
    ((0, 3, 9), (6, 3, 15), (18, 9, 21), (24, 15, 21)),
    ((2, 5, 11), (8, 5, 17), (20, 11, 23), (26, 17, 23)),
)
LOOKUP4 = (
    ((0, 1, 3, 4), (1, 2, 4, 5), (3, 4, 6, 7), (4, 5, 7, 8)),
    ((18, 19, 21, 22), (19, 20, 22, 23), (21, 22, 24, 25), (22, 23, 25, 26)),
    ((6, 7, 15, 16), (7, 8, 16, 17), (15, 16, 24, 25), (16, 17, 25, 26)),
    ((0, 1, 9, 10), (1, 2, 10, 11), (9, 10, 18, 19), (10, 11, 19, 20)),
    ((0, 3, 9, 12), (3, 6, 12, 15), (9, 12, 18, 21), (12, 15, 21, 24)),
    ((2, 5, 11, 14), (5, 8, 14, 17), (11, 14, 20, 23), (14, 17, 23, 26)),
)
CORNERS = [[(*LOOKUP3[i][j], *LOOKUP4[i][j]) for j in range(4)] for i in range(6)]
CURVE = (0.0, 0.25, 0.5, 0.75)
NO_LIGHT = (0, 0, 0, 0)  # also no occlusion, for faces not drawn
# The 27 neighbours as nine runs of three, z running fastest: each run
# starts at one of these offsets.
RUNS = [dx * S + dy * L - 1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
# Tables for bytes.translate.
NONEMPTY = bytes([0] + [1] * 255)
EIGHT = bytes([0, 8] + [0] * 254)
FADE = bytes(max(v - 1, 0) for v in range(256))
CAP = bytes(min(v, 8) for v in range(256))
# 1 at the 32 x 32 columns of a layer that belong to the chunk.
INSIDE = bytes(1 if 0 < i // S < S - 1 and 0 < i % S < S - 1 else 0 for i in range(L))


def number(data):
    """A bytes-like object as one integer, a byte to each 8 bits, so that
    shifts and bitwise operators work on every byte at once."""
    return int.from_bytes(data, "little")


def runs(data, i):
    return (data[i + RUNS[0]:i + RUNS[0] + 3] + data[i + RUNS[1]:i + RUNS[1] + 3] + data[i + RUNS[2]:i + RUNS[2] + 3]
            + data[i + RUNS[3]:i + RUNS[3] + 3] + data[i + RUNS[4]:i + RUNS[4] + 3] + data[i + RUNS[5]:i + RUNS[5] + 3]
            + data[i + RUNS[6]:i + RUNS[6] + 3] + data[i + RUNS[7]:i + RUNS[7] + 3] + data[i + RUNS[8]:i + RUNS[8] + 3])


def shade_levels(opaque):
    """For each block, 8 - n where the nearest opaque block at most seven
    above it is n above (0 when there is none). A layer's level is 8 where
    it is opaque, else one less than the level above; the OR of 8 with a
    smaller level, capped at 8, picks the 8."""
    levels = bytearray(len(opaque))
    above = bytes(L)
    for base in range(len(opaque) - L, -1, -L):
        level = number(above.translate(FADE)) | number(opaque[base:base + L].translate(EIGHT))
        above = level.to_bytes(L, "little").translate(CAP)
        levels[base:base + L] = above
    return levels


def occlusion(face, neighbors, shades):
    """The ambient occlusion of a face's four corners: darker for each
    opaque block beside or diagonal to the corner, and under opaque blocks
    above. shades are shade levels (see shade_levels)."""
    ao = []
    for c, s1, s2, k0, k1, k2, k3 in CORNERS[face]:
        side1, side2 = neighbors[s1], neighbors[s2]
        dark = 0.75 if side1 and side2 else CURVE[neighbors[c] + side1 + side2]
        ao.append(min(dark + (shades[k0] + shades[k1] + shades[k2] + shades[k3]) / 32, 1))
    return ao


def lighting(face, lights):
    """The light of a face's four corners: the average level of the four
    blocks around each, or full light on a lamp itself."""
    if lights[13] == 15:
        return [10] * 4
    return [(lights[k0] + lights[k1] + lights[k2] + lights[k3]) / 60 for _, _, _, k0, k1, k2, k3 in CORNERS[face]]


def compute_chunk(chunk, light=None):
    """The vertices of every face of the chunk that is not hidden by an
    opaque neighbour, with its corners darkened by the blocks around and
    above them. light, when the chunk is lit, maps an index to its light
    level. A generator: it pauses every few blocks so that the caller can
    spread the work over frames, and returns the vertices, the face count,
    and the lowest and highest block drawn."""
    blocks = chunk.blocks
    opaque = blocks.translate(OPAQUE)
    shades_of = shade_levels(opaque)
    # The blocks of the chunk with an open neighbour, found for all blocks
    # at once; the loop below visits only these.
    o = number(opaque)
    covered = o >> 8 & o << 8 & o >> 8 * S & o << 8 * S & o >> 8 * L & o << 8 * L
    layers = len(blocks) // L - HEADROOM
    inside = number(bytes(L) + INSIDE * layers)
    candidates = (number(blocks.translate(NONEMPTY)) & ~covered & inside).to_bytes(len(blocks), "little")
    data = []
    faces, miny, maxy = 0, 256, 0
    i = candidates.find(1)
    visited = 0
    while i >= 0:
        visited += 1
        if visited % 64 == 0:
            yield
        w = blocks[i]
        y, rest = divmod(i, L)
        y -= 1
        lx, lz = divmod(rest, S)
        shown = (not opaque[i - S], not opaque[i + S], not opaque[i + L],
                 not opaque[i - L] and y > 0, not opaque[i - 1], not opaque[i + 1])
        if True in shown:
            x, z = chunk.x0 + lx, chunk.z0 + lz
            neighbors = runs(opaque, i)
            shades = runs(shades_of, i)
            lights = None if light is None else [light.get(i + o + 1 + dz, 0) for o in RUNS for dz in (-1, 0, 1)]
            if w in PLANTS:
                # A plant takes the darkest occlusion and brightest light
                # of all six faces.
                ao = min(min(occlusion(f, neighbors, shades)) for f in range(6))
                lit = 0 if lights is None else max(max(lighting(f, lights)) for f in range(6))
                make_plant(data, ao, lit, x, y, z, 0.5, w, simplex2(x, z, 4, 0.5, 2) * 360)
                faces += 4
            else:
                ao = [occlusion(f, neighbors, shades) if shown[f] else NO_LIGHT for f in range(6)]
                lit = [NO_LIGHT if lights is None or not shown[f] else lighting(f, lights) for f in range(6)]
                make_cube(data, ao, lit, shown, x, y, z, 0.5, w)
                faces += shown.count(True)
            miny, maxy = min(miny, y), max(maxy, y)
        i = candidates.find(1, i + 1)
    return data, faces, miny, maxy
