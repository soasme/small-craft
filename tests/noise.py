"""A stand-in for the host's noise module: smooth, deterministic, and cheap,
not simplex noise. Terrain from it has hills, sand, plants and trees."""
from libm import sin


def simplex2(x, y, octaves, persistence, lacunarity):
    return 0.6 * sin(x * 1.7 + 0.4) * sin(y * 1.3 + 1.1) + 0.3 * sin(x * 7.1 + y * 5.3)


def simplex3(x, y, z, octaves, persistence, lacunarity):
    return sin(x * 9 + y * 2) * sin(z * 8 - y * 3)
