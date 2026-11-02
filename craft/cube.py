"""The vertices of blocks, plants, the sky and the
wireframe. A vertex of a block is ten numbers: position, normal, texture
coordinate, ambient occlusion and light."""
from libm import acos, cos, sin
from .item import BLOCKS, PLANTS
from .matrix import PI, normalize

# For each face (left, right, top, bottom, front, back): its four corners,
# normal, and corner texture coordinates; then the corners of its two
# triangles, in the order that splits the quad along its brighter diagonal.
POSITIONS = (
    ((-1, -1, -1), (-1, -1, +1), (-1, +1, -1), (-1, +1, +1)),
    ((+1, -1, -1), (+1, -1, +1), (+1, +1, -1), (+1, +1, +1)),
    ((-1, +1, -1), (-1, +1, +1), (+1, +1, -1), (+1, +1, +1)),
    ((-1, -1, -1), (-1, -1, +1), (+1, -1, -1), (+1, -1, +1)),
    ((-1, -1, -1), (-1, +1, -1), (+1, -1, -1), (+1, +1, -1)),
    ((-1, -1, +1), (-1, +1, +1), (+1, -1, +1), (+1, +1, +1)),
)
NORMALS = ((-1, 0, 0), (+1, 0, 0), (0, +1, 0), (0, -1, 0), (0, 0, -1), (0, 0, +1))
UVS = (
    ((0, 0), (1, 0), (0, 1), (1, 1)),
    ((1, 0), (0, 0), (1, 1), (0, 1)),
    ((0, 1), (0, 0), (1, 1), (1, 0)),
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((1, 0), (1, 1), (0, 0), (0, 1)),
)
INDICES = ((0, 3, 2, 0, 1, 3), (0, 3, 1, 0, 2, 3)) * 3
FLIPPED = ((0, 1, 2, 1, 3, 2), (0, 2, 1, 2, 3, 1)) * 3

# A tile is 1/16 of the atlas; a block's texture coordinates stay half a
# texel inside it so neighbouring tiles never bleed in.
S = 0.0625
A, B = 1 / 2048, S - 1 / 2048
# Each face's corners, ready to place: (dx, dy, dz, u, v) for a unit n.
CORNERS = [[(*POSITIONS[i][j], B if UVS[i][j][0] else A, B if UVS[i][j][1] else A) for j in range(4)]
           for i in range(6)]


def make_cube_faces(data, ao, light, faces, tiles, x, y, z, n):
    """Append the faces whose flag is set to data. ao and light hold four
    corner values for each of the six faces."""
    for i in range(6):
        if not faces[i]:
            continue
        tile = tiles[i]
        du, dv = tile % 16 * S, tile // 16 * S
        a, l = ao[i], light[i]
        nx, ny, nz = NORMALS[i]
        corners = [(x + n * px, y + n * py, z + n * pz, nx, ny, nz, du + u, dv + v, a[j], l[j])
                   for j, (px, py, pz, u, v) in enumerate(CORNERS[i])]
        for j in FLIPPED[i] if a[0] + a[3] > a[1] + a[2] else INDICES[i]:
            data += corners[j]


def make_cube(data, ao, light, faces, x, y, z, n, w):
    make_cube_faces(data, ao, light, faces, BLOCKS[w], x, y, z, n)


PLANT_POSITIONS = (
    ((0, -1, -1), (0, -1, +1), (0, +1, -1), (0, +1, +1)),
    ((0, -1, -1), (0, -1, +1), (0, +1, -1), (0, +1, +1)),
    ((-1, -1, 0), (-1, +1, 0), (+1, -1, 0), (+1, +1, 0)),
    ((-1, -1, 0), (-1, +1, 0), (+1, -1, 0), (+1, +1, 0)),
)
PLANT_NORMALS = ((-1, 0, 0), (+1, 0, 0), (0, 0, -1), (0, 0, +1))
PLANT_UVS = (
    ((0, 0), (1, 0), (0, 1), (1, 1)),
    ((1, 0), (0, 0), (1, 1), (0, 1)),
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((1, 0), (1, 1), (0, 0), (0, 1)),
)


def make_plant(data, ao, light, px, py, pz, n, w, rotation):
    """Append two crossed quads, seen from both sides, turned rotation
    degrees about the vertical."""
    tile = PLANTS[w]
    du, dv = tile % 16 * S, tile // 16 * S
    # mat_rotate(0, 1, 0, angle): x' = c x - s z, z' = s x + c z.
    angle = rotation * PI / 180
    c, s = cos(angle), sin(angle)
    for i in range(4):
        nx, _, nz = PLANT_NORMALS[i]
        rnx, rnz = c * nx - s * nz, s * nx + c * nz
        for j in INDICES[i]:
            x, y, z = PLANT_POSITIONS[i][j]
            u, v = PLANT_UVS[i][j]
            data += (px + n * (c * x - s * z), py + n * y, pz + n * (s * x + c * z),
                     rnx, 0, rnz, du + u * S, dv + v * S, ao, light)


def make_cube_wireframe(x, y, z, n):
    """The twelve edges of a cube, as pairs of points."""
    corners = [(x + n * dx, y + n * dy, z + n * dz) for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
    points = []
    for j in (0, 1, 0, 2, 0, 4, 1, 3, 1, 5, 2, 3, 2, 6, 3, 7, 4, 5, 4, 6, 5, 7, 6, 7):
        points += corners[j]
    return points


def make_sphere(r, detail):
    """A sphere of 8 * 4**detail triangles, eight numbers to a vertex:
    position, normal and texture coordinate (whose v runs pole to pole)."""
    data = []

    def triangle(a, b, c, ta, tb, tc, detail):
        if detail == 0:
            for v, t in ((a, ta), (b, tb), (c, tc)):
                data.extend((v[0] * r, v[1] * r, v[2] * r, *v, *t))
            return
        ab = normalize(*[(a[i] + b[i]) / 2 for i in range(3)])
        ac = normalize(*[(a[i] + c[i]) / 2 for i in range(3)])
        bc = normalize(*[(b[i] + c[i]) / 2 for i in range(3)])
        tab, tac, tbc = [(0, 1 - acos(v[1]) / PI) for v in (ab, ac, bc)]
        triangle(a, ab, ac, ta, tab, tac, detail - 1)
        triangle(b, bc, ab, tb, tbc, tab, detail - 1)
        triangle(c, ac, bc, tc, tac, tbc, detail - 1)
        triangle(ab, bc, ac, tab, tbc, tac, detail - 1)

    positions = ((0, 0, -1), (1, 0, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0), (0, 0, 1))
    uvs = ((0, 0.5), (0, 0.5), (0, 0), (0, 0.5), (0, 1), (0, 0.5))
    for i, j, k in ((4, 3, 0), (1, 4, 0), (3, 4, 5), (4, 1, 5), (0, 3, 2), (0, 2, 1), (5, 2, 3), (5, 1, 2)):
        triangle(positions[i], positions[j], positions[k], uvs[i], uvs[j], uvs[k], detail)
    return data
