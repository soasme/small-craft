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


# Index offsets of the 27 blocks around and including a block, x, y and z
# each running -1, 0, 1, as occlusion numbers them.
NEIGHBORS = [dx * S + dy * L + dz for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
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
NO_LIGHT = (0, 0, 0, 0)


def occlusion(face, neighbors, shades, lights):
    """Occlusion for one face: the ambient occlusion and light of
    its four corners."""
    ao, light = [], NO_LIGHT if lights is None else []
    for c, s1, s2, k0, k1, k2, k3 in CORNERS[face]:
        side1, side2 = neighbors[s1], neighbors[s2]
        value = 3 if side1 and side2 else neighbors[c] + side1 + side2
        ao.append(min(CURVE[value] + (shades[k0] + shades[k1] + shades[k2] + shades[k3]) / 4, 1))
        if lights is not None:
            total = 600 if lights[13] == 15 else lights[k0] + lights[k1] + lights[k2] + lights[k3]
            light.append(total / 60)
    return ao, light


def compute_chunk(chunk, light=None):
    """The vertices of every face of the chunk that
    is not hidden by an opaque neighbour, with its corners darkened by the
    blocks around and above them. light, when the chunk is lit, maps an
    index to its light level. Return the vertices, the face count, and the
    lowest and highest block drawn."""
    blocks = chunk.blocks
    opaque = blocks.translate(OPAQUE)
    shade_of = {}

    def shade(j):
        # Darkened by the nearest opaque block at most seven above.
        s = shade_of.get(j)
        if s is None:
            s = 0
            for oy in range(8):
                if opaque[j + oy * L]:
                    s = 1 - oy * 0.125
                    break
            shade_of[j] = s
        return s

    data = []
    faces, miny, maxy = 0, 256, 0
    for ly in range(1, len(blocks) // L - HEADROOM + 1):
        base = ly * L
        if blocks.count(0, base + S, base + L - S) == L - 2 * S:
            continue
        y = ly - 1
        for lx in range(1, S - 1):
            row = base + lx * S
            x = chunk.x0 + lx
            for i in range(row + 1, row + S - 1):
                w = blocks[i]
                if not w:
                    continue
                shown = (not opaque[i - S], not opaque[i + S], not opaque[i + L],
                         not opaque[i - L] and y > 0, not opaque[i - 1], not opaque[i + 1])
                if True not in shown:
                    continue
                z = chunk.z0 + i - row
                neighbors = [opaque[i + o] for o in NEIGHBORS]
                shades = [shade(i + o) for o in NEIGHBORS]
                lights = None if light is None else [light.get(i + o, 0) for o in NEIGHBORS]
                if w in PLANTS:
                    corners = [occlusion(f, neighbors, shades, lights) for f in range(6)]
                    ao = min(min(a) for a, _ in corners)
                    lit = max(max(l) for _, l in corners)
                    make_plant(data, ao, lit, x, y, z, 0.5, w, simplex2(x, z, 4, 0.5, 2) * 360)
                    faces += 4
                else:
                    ao, lit = [], []
                    for f in range(6):
                        a, l = occlusion(f, neighbors, shades, lights) if shown[f] else (NO_LIGHT, NO_LIGHT)
                        ao.append(a)
                        lit.append(l)
                    make_cube(data, ao, lit, shown, x, y, z, 0.5, w)
                    faces += shown.count(True)
                miny, maxy = min(miny, y), max(maxy, y)
    return data, faces, miny, maxy
