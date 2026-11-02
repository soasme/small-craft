"""The game without a window: run by `make test` on the spy command line,
with stand-ins for the host's modules beside it. Each test raises on
failure; the run ends with the number of tests passed."""
import raylib
from craft.builder import parse_command
from craft.chunk import L, Chunk, compute_chunk, shade_levels
from craft.cube import make_sphere
from craft.item import BRICK, CLOUD, EMPTY, GRASS, ITEMS, OPAQUE, STONE, TALL_GRASS
from craft.model import Model, chunked, finish, roundf
from craft.store import Store

SAVE = "test-save.txt"


def fresh_model():
    open(SAVE, "w").close()
    return Model(Store(SAVE))


def settle(m, seconds=3.0):
    for _ in range(int(seconds * 60)):
        m.move(1 / 60, 0, 0, False)


def test_rounding():
    assert [roundf(v) for v in (0.5, 1.5, -0.5, -1.5, 2.4, -2.6)] == [1, 2, -1, -2, 2, -3]
    assert [chunked(v) for v in (0, 31.4, 31.6, -0.4, -0.6, -32.6)] == [0, 0, 1, 0, -1, -2]


def test_player_lands():
    m = fresh_model()
    ground = m.highest_block(m.x, m.z)
    assert ground > 0
    assert m.y == ground + 2
    settle(m)
    assert m.dy == 0 and ground + 1 <= m.y < ground + 2, (ground, m.y)


def test_walking_stops_at_walls():
    m = fresh_model()
    settle(m)
    x, y, z = roundf(m.x), roundf(m.y), roundf(m.z)
    m.rx = m.ry = 0
    # Facing -z; a wall two high one block ahead.
    for dy in (0, 1):
        m.set_block(x, y - dy, z - 1, BRICK)
    for _ in range(60):
        m.move(1 / 60, -1, 0, False)
    assert z - 1 < m.z and abs(m.z - (z - 0.25)) < 1e-9, m.z


def test_border_blocks_reach_neighbours():
    m = fresh_model()
    # x = 31 is the last column of chunk 0 and the border of chunk 1.
    p = chunked(m.x)
    x, z = (p + 1) * 32 - 1, roundf(m.z)
    m.set_block(x, 100, z, STONE)
    here, there = m.find_chunk(p, chunked(z)), m.find_chunk(p + 1, chunked(z))
    assert here.get(x, 100, z) == STONE and there.get(x, 100, z) == STONE
    assert here.dirty and there.dirty


def test_click_builds_and_breaks():
    m = fresh_model()
    settle(m)
    m.ry = -1.5  # look at the ground under the feet
    hx, hy, hz, hw = m.hit_test(False)
    assert hw and hy == roundf(m.y) - 2, (hy, m.y)
    m.rx = 0
    m.ry = -0.6
    hx, hy, hz, hw = m.hit_test(False)
    m.item_index = ITEMS.index(BRICK)
    px, py, pz, _ = m.hit_test(True)
    m.on_right_click()
    assert m.get_block(px, py, pz) == BRICK and m.block0 == (px, py, pz, BRICK)
    m.on_left_click()
    assert m.get_block(px, py, pz) == EMPTY
    assert m.block1 == (px, py, pz, BRICK) and m.block0 == (px, py, pz, 0)
    m.set_block(px, py, pz, STONE)
    m.item_index = 0
    m.on_middle_click()
    assert ITEMS[m.item_index] == STONE


def test_builder_commands():
    m = fresh_model()
    m.block1, m.block0 = (0, 120, 0, STONE), (4, 122, 2, STONE)
    parse_command(m, "/cube")
    shell = sum(m.get_block(x, y, z) == STONE for x in range(5) for y in range(120, 123) for z in range(3))
    assert shell == 5 * 3 * 3 - 3 * 1 * 1, shell
    m.block0 = (0, 140, 0, BRICK)
    parse_command(m, "/fsphere 3")
    assert m.get_block(0, 140, 0) == BRICK and m.get_block(0, 143, 0) == BRICK and m.get_block(0, 144, 0) == EMPTY
    parse_command(m, "/view 3")
    assert (m.create_radius, m.delete_radius) == (3, 7)
    parse_command(m, "/view 30")
    parse_command(m, "/nonsense 1")
    assert m.messages[-2:] == ["Viewing distance must be between 1 and 24.", "Unknown command: /nonsense 1"]


def test_saving():
    m = fresh_model()
    m.set_block(3, 90, 4, BRICK)
    m.toggle_light(3, 90, 4)
    m.store.save((1.5, 30.0, -2.25, 0.5, -0.25))
    again = Model(Store(SAVE))
    assert (again.x, again.y, again.z, again.rx, again.ry) == (1.5, 30.0, -2.25, 0.5, -0.25)
    assert again.get_block(3, 90, 4) == BRICK
    assert again.store.lights[0, 0] == {(3, 90, 4): 15}


def test_lights():
    m = fresh_model()
    chunk = m.find_chunk(0, 0)
    finish(m.gen_chunk_buffer(chunk))
    assert not m.has_lights(chunk)
    m.set_block(10, 100, 10, STONE)
    m.toggle_light(10, 100, 10)
    assert m.has_lights(chunk) and chunk.dirty
    light = m.light_map(chunk)
    assert light[chunk.index(10, 100, 10)] == 15
    assert light[chunk.index(10, 101, 10)] == 14 and light[chunk.index(10, 104, 10)] == 11
    m.set_block(10, 100, 10, EMPTY)  # removing the block puts the light out
    assert not m.has_lights(chunk)


def test_mesh():
    chunk = Chunk(0, 0)
    chunk.fill(5, 5, 5, GRASS)
    chunk.set(5, 5, 5, TALL_GRASS)
    chunk.set(9, 70, 9, CLOUD)
    data = []
    faces, miny, maxy = finish(compute_chunk(chunk, data))
    # The column shows four sides and a top; the plant four quads; the
    # cloud all six faces.
    assert (faces, miny, maxy) == (5 * 4 + 1 + 4 + 6, 0, 70) and len(data) == faces * 60
    tops = {tuple(data[v:v + 3]) for v in range(0, len(data), 10) if data[v + 4] == 1 and data[v] < 6}
    assert tops == {(4.5, 4.5, 4.5), (5.5, 4.5, 5.5), (5.5, 4.5, 4.5), (4.5, 4.5, 5.5)}, tops


def test_shade_levels():
    chunk = Chunk(0, 0)
    chunk.set(1, 20, 1, STONE)
    levels = shade_levels(chunk.blocks.translate(OPAQUE))
    column = [levels[chunk.index(1, y, 1)] for y in range(10, 22)]
    assert column == [0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 0], column


def test_sky():
    data = make_sphere(1, 3)
    assert len(data) == 512 * 3 * 8
    assert all(abs(data[v] ** 2 + data[v + 1] ** 2 + data[v + 2] ** 2 - 1) < 1e-9 for v in range(0, len(data), 8))


def test_chunks_load_over_frames():
    raylib.meshes.clear()  # forget the models of earlier tests
    m = fresh_model()
    m.create_radius = 2
    planes = [(0, 0, 0, 1)] * 6  # everything in view
    frames = 0
    while m.job is not None or m.next_job(planes) is not None:
        raylib.now += 1
        m.ensure_chunks(planes, raylib.now + 0.5)
        frames += 1
        assert frames < 1000
    assert len(m.chunks) == 25 and all(not c.dirty for c in m.chunks.values())
    assert len(raylib.meshes) == sum(c.mesh is not None for c in m.chunks.values())
    m.x += 32 * 20
    m.force_chunks()
    m.delete_chunks()
    assert len(m.chunks) == 9 and len(raylib.meshes) == sum(c.mesh is not None for c in m.chunks.values())


tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
for test in tests:
    test()
print(f"{len(tests)} tests passed")
