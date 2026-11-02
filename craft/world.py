"""The generated terrain of a chunk, from simplex noise.
It writes one block beyond each side as well, so a chunk can tell which of
its faces show without its neighbours."""
from noise import simplex2, simplex3
from .config import CHUNK_SIZE, SHOW_CLOUDS, SHOW_PLANTS, SHOW_TREES
from .item import CLOUD, GRASS, LEAVES, SAND, TALL_GRASS, WOOD, YELLOW_FLOWER


def create_world(chunk):
    p, q = chunk.p, chunk.q
    for dx in range(-1, CHUNK_SIZE + 1):
        x = p * CHUNK_SIZE + dx
        for dz in range(-1, CHUNK_SIZE + 1):
            z = q * CHUNK_SIZE + dz
            f = simplex2(x * 0.01, z * 0.01, 4, 0.5, 2)
            g = simplex2(-x * 0.01, -z * 0.01, 2, 0.9, 2)
            mh = int(g * 32 + 16)
            h = int(f * mh)
            w = GRASS
            t = 12
            if h <= t:
                h = t
                w = SAND
            # sand and grass terrain
            chunk.fill(x, z, h, w)
            if w == GRASS:
                if SHOW_PLANTS:
                    # grass
                    if simplex2(-x * 0.1, z * 0.1, 4, 0.8, 2) > 0.6:
                        chunk.set(x, h, z, TALL_GRASS)
                    # flowers
                    if simplex2(x * 0.05, -z * 0.05, 4, 0.8, 2) > 0.7:
                        chunk.set(x, h, z, int(YELLOW_FLOWER + simplex2(x * 0.1, z * 0.1, 4, 0.8, 2) * 7))
                # trees, wholly inside the chunk
                inside = 4 <= dx < CHUNK_SIZE - 4 and 4 <= dz < CHUNK_SIZE - 4
                if SHOW_TREES and inside and simplex2(x, z, 6, 0.5, 2) > 0.84:
                    for y in range(h + 3, h + 8):
                        for ox in range(-3, 4):
                            for oz in range(-3, 4):
                                if ox * ox + oz * oz + (y - (h + 4)) ** 2 < 11:
                                    chunk.set(x + ox, y, z + oz, LEAVES)
                    for y in range(h, h + 7):
                        chunk.set(x, y, z, WOOD)
            # clouds
            if SHOW_CLOUDS:
                for y in range(64, 72):
                    if simplex3(x * 0.01, y * 0.1, z * 0.01, 8, 0.5, 2) > 0.75:
                        chunk.set(x, y, z, CLOUD)
