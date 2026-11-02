"""The game state: the loaded chunks, the player, the
physics, ray casting, and editing blocks and lights."""
from libm import atan2, cos, sin
from .chunk import Chunk, S, compute_chunk
from .config import CHUNK_SIZE, CREATE_CHUNK_RADIUS, DAY_LENGTH, DELETE_CHUNK_RADIUS, MAX_MESSAGES
from .item import ITEMS, OPAQUE, is_destructable, is_obstacle, is_plant
from .matrix import PI
from .world import create_world
import raylib as rl


def finish(job):
    """Run a generator to its end; return what it returns."""
    while True:
        try:
            next(job)
        except StopIteration as stop:
            return stop.value


def roundf(x):
    """C's roundf: halves round away from zero, unlike Python's round."""
    return int(x + 0.5) if x >= 0 else -int(0.5 - x)


def chunked(x):
    return roundf(x) // CHUNK_SIZE


def radians(degrees):
    return degrees * PI / 180


class Model:
    def __init__(self, store):
        # The saved edits and lights, by chunk: {(p, q): {(x, y, z): w}}.
        self.store = store
        self.chunks = {}
        self.create_radius = self.render_radius = CREATE_CHUNK_RADIUS
        self.delete_radius = DELETE_CHUNK_RADIUS
        self.x, self.y, self.z, self.rx, self.ry = store.state or (0, 0, 0, 0, 0)
        self.dy = 0  # vertical speed
        self.flying = False
        self.item_index = 0
        self.ortho, self.fov = 0, 65
        self.day_length = DAY_LENGTH
        self.messages = []
        self.job = None  # the chunk being loaded, a generator
        # The last two blocks edited, and the two copied, as (x, y, z, w).
        self.block0 = self.block1 = self.copy0 = self.copy1 = (0, 0, 0, 0)
        self.force_chunks()
        if store.state is None:
            self.y = self.highest_block(self.x, self.z) + 2

    def add_message(self, text):
        self.messages = [*self.messages, text][-MAX_MESSAGES:]

    def time_of_day(self):
        if self.day_length <= 0:
            return 0.5
        t = (rl.get_time() + self.day_length / 3) / self.day_length
        return t - int(t)

    def daylight(self):
        timer = self.time_of_day()
        if timer < 0.5:
            return 1 / (1 + 2 ** (-(timer - 0.25) * 100))
        return 1 - 1 / (1 + 2 ** (-(timer - 0.85) * 100))

    # -- chunks --

    def find_chunk(self, p, q):
        return self.chunks.get((p, q))

    def create_chunk(self, p, q):
        """Generate a chunk, then replay the edits saved for it and its
        neighbours. A generator; it returns the chunk."""
        chunk = Chunk(p, q)
        yield from create_world(chunk)
        for dp in (-1, 0, 1):
            for dq in (-1, 0, 1):
                for (x, y, z), w in self.store.blocks.get((p + dp, q + dq), {}).items():
                    chunk.set(x, y, z, w)
        if (p, q) in self.chunks:  # made meanwhile, by force_chunks
            return self.chunks[p, q]
        self.chunks[p, q] = chunk
        self.dirty_chunk(chunk)
        return chunk

    def has_lights(self, chunk):
        return any(self.store.lights.get((chunk.p + dp, chunk.q + dq))
                   for dp in (-1, 0, 1) for dq in (-1, 0, 1))

    def dirty_chunk(self, chunk):
        chunk.touch()
        if self.has_lights(chunk):
            for dp in (-1, 0, 1):
                for dq in (-1, 0, 1):
                    other = self.find_chunk(chunk.p + dp, chunk.q + dq)
                    if other:
                        other.touch()

    def light_map(self, chunk):
        """Flood fill the light of every lamp in and around chunk, each
        level one less than its brightest neighbour's, through blocks that
        are not opaque. Return {index in chunk: level}."""
        level = {}
        lo_x, lo_z = chunk.x0, chunk.z0
        hi_x, hi_z = lo_x + S - 1, lo_z + S - 1

        def fill(x, y, z, w, force):
            if x + w < lo_x or z + w < lo_z or x - w > hi_x or z - w > hi_z or not 0 <= y < 256:
                return
            if level.get((x, y, z), 0) >= w or not force and OPAQUE[self.get_block(x, y, z)]:
                return
            level[x, y, z] = w
            w -= 1
            fill(x - 1, y, z, w, False)
            fill(x + 1, y, z, w, False)
            fill(x, y - 1, z, w, False)
            fill(x, y + 1, z, w, False)
            fill(x, y, z - 1, w, False)
            fill(x, y, z + 1, w, False)

        for dp in (-1, 0, 1):
            for dq in (-1, 0, 1):
                for (x, y, z), w in self.store.lights.get((chunk.p + dp, chunk.q + dq), {}).items():
                    fill(x, y, z, w, True)
        light = {}
        for (x, y, z), w in level.items():
            i = chunk.index(x, y, z)
            if i >= 0:
                light[i] = w
        return light

    def gen_chunk_buffer(self, chunk):
        """Mesh the chunk and send the mesh to the GPU. A generator; the mesh
        is dropped if the chunk changed or was unloaded meanwhile."""
        version = chunk.version
        light = self.light_map(chunk) if self.has_lights(chunk) else None
        data, faces, miny, maxy = yield from compute_chunk(chunk, light)
        if chunk.version != version or self.chunks.get((chunk.p, chunk.q)) is not chunk:
            return
        if chunk.mesh is not None:
            rl.unload_mesh(chunk.mesh)
        chunk.mesh = rl.load_mesh(data, 10) if data else None
        chunk.faces, chunk.miny, chunk.maxy = faces, miny, maxy
        chunk.dirty = False

    def load_chunk(self, p, q):
        chunk = self.find_chunk(p, q) or (yield from self.create_chunk(p, q))
        yield from self.gen_chunk_buffer(chunk)

    def force_chunks(self):
        """Build the chunks around the player at once, so they are never
        missing beneath the player's feet."""
        p, q = chunked(self.x), chunked(self.z)
        for a in (p - 1, p, p + 1):
            for b in (q - 1, q, q + 1):
                chunk = self.find_chunk(a, b)
                if not chunk or chunk.dirty:
                    finish(self.load_chunk(a, b))

    def ensure_chunks(self, planes, deadline):
        """Create or rebuild the chunks within create_radius until the
        deadline, one at a time, resuming next frame where this one stopped."""
        self.force_chunks()
        while rl.get_time() < deadline:
            if self.job is None:
                self.job = self.next_job(planes)
                if self.job is None:
                    return
            try:
                next(self.job)
            except StopIteration:
                self.job = None

    def next_job(self, planes):
        """Load the missing or stale chunk that matters most: first those in
        view, then those already drawn, nearest first."""
        p, q = chunked(self.x), chunked(self.z)
        r = self.create_radius
        best = None
        for a in range(p - r, p + r + 1):
            for b in range(q - r, q + r + 1):
                chunk = self.find_chunk(a, b)
                if chunk and not chunk.dirty:
                    continue
                invisible = not chunk_visible(planes, a, b, 0, 256, self.ortho)
                priority = bool(chunk and chunk.mesh is not None)
                score = invisible << 24 | priority << 16 | max(abs(a - p), abs(b - q))
                if best is None or score < best[0]:
                    best = score, a, b
        return None if best is None else self.load_chunk(best[1], best[2])

    def delete_chunks(self):
        p, q = chunked(self.x), chunked(self.z)
        for key in [k for k in self.chunks if max(abs(k[0] - p), abs(k[1] - q)) >= self.delete_radius]:
            chunk = self.chunks.pop(key)
            if chunk.mesh is not None:
                rl.unload_mesh(chunk.mesh)

    # -- blocks --

    def get_block(self, x, y, z):
        chunk = self.find_chunk(chunked(x), chunked(z))
        return chunk.get(x, y, z) if chunk else 0

    def highest_block(self, x, z):
        nx, nz = roundf(x), roundf(z)
        chunk = self.find_chunk(chunked(x), chunked(z))
        if chunk:
            for y in range(255, -1, -1):
                if is_obstacle(chunk.get(nx, y, nz)):
                    return y
        return -1

    def set_block(self, x, y, z, w):
        """Set a block in its chunk and in the borders of the neighbours that
        hold it, and save it. Removing a block puts out its light."""
        p, q = chunked(x), chunked(z)
        self.store.blocks.setdefault((p, q), {})[x, y, z] = w
        for dp in (-1, 0, 1):
            for dq in (-1, 0, 1):
                chunk = self.find_chunk(p + dp, q + dq)
                if chunk and chunk.set(x, y, z, w):
                    self.dirty_chunk(chunk)
        if w == 0:
            self.set_light(x, y, z, 0)
        self.store.changed = True

    def record_block(self, x, y, z, w):
        self.block1, self.block0 = self.block0, (x, y, z, w)

    def builder_block(self, x, y, z, w):
        if y <= 0 or y >= 256:
            return
        if is_destructable(self.get_block(x, y, z)):
            self.set_block(x, y, z, 0)
        if w:
            self.set_block(x, y, z, w)

    def set_light(self, x, y, z, w):
        p, q = chunked(x), chunked(z)
        lights = self.store.lights.setdefault((p, q), {})
        if lights.get((x, y, z), 0) == w:
            return
        if w:
            lights[x, y, z] = w
        else:
            del lights[x, y, z]
        chunk = self.find_chunk(p, q)
        if chunk:
            # dirty_chunk reaches the neighbours only while a light is left.
            for dp in (-1, 0, 1):
                for dq in (-1, 0, 1):
                    other = self.find_chunk(p + dp, q + dq)
                    if other:
                        other.touch()
        self.store.changed = True

    def toggle_light(self, x, y, z):
        lights = self.store.lights.get((chunked(x), chunked(z)), {})
        self.set_light(x, y, z, 0 if lights.get((x, y, z)) else 15)

    # -- the player --

    def sight_vector(self):
        m = cos(self.ry)
        return cos(self.rx - radians(90)) * m, sin(self.ry), sin(self.rx - radians(90)) * m

    def motion_vector(self, sz, sx):
        if not sz and not sx:
            return 0, 0, 0
        strafe = atan2(sz, sx)
        if self.flying:
            m, y = cos(self.ry), sin(self.ry)
            if sx:
                if not sz:
                    y = 0
                m = 1
            if sz > 0:
                y = -y
            return cos(self.rx + strafe) * m, y, sin(self.rx + strafe) * m
        return cos(self.rx + strafe), 0, sin(self.rx + strafe)

    def hit_test(self, previous):
        """March along the line of sight for eight blocks; return the first
        block hit as (x, y, z, w), or the empty block before it when
        previous is set. w is 0 when nothing is hit."""
        vx, vy, vz = self.sight_vector()
        x, y, z = self.x, self.y, self.z
        px = py = pz = 0
        for _ in range(8 * 32):
            nx, ny, nz = roundf(x), roundf(y), roundf(z)
            if nx != px or ny != py or nz != pz:
                hw = self.get_block(nx, ny, nz)
                if hw > 0:
                    return (px, py, pz, hw) if previous else (nx, ny, nz, hw)
                px, py, pz = nx, ny, nz
            x, y, z = x + vx / 32, y + vy / 32, z + vz / 32
        return 0, 0, 0, 0

    def collide(self, height):
        """Push the player out of the blocks around them; return whether
        they stand on or hit their head on one."""
        chunk = self.find_chunk(chunked(self.x), chunked(self.z))
        if not chunk:
            return False
        result = False
        nx, ny, nz = roundf(self.x), roundf(self.y), roundf(self.z)
        px, py, pz = self.x - nx, self.y - ny, self.z - nz
        pad = 0.25
        for dy in range(height):
            if px < -pad and is_obstacle(chunk.get(nx - 1, ny - dy, nz)):
                self.x = nx - pad
            if px > pad and is_obstacle(chunk.get(nx + 1, ny - dy, nz)):
                self.x = nx + pad
            if py < -pad and is_obstacle(chunk.get(nx, ny - dy - 1, nz)):
                self.y = ny - pad
                result = True
            if py > pad and is_obstacle(chunk.get(nx, ny - dy + 1, nz)):
                self.y = ny + pad
                result = True
            if pz < -pad and is_obstacle(chunk.get(nx, ny - dy, nz - 1)):
                self.z = nz - pad
            if pz > pad and is_obstacle(chunk.get(nx, ny - dy, nz + 1)):
                self.z = nz + pad
        return result

    def intersects_block(self, height, hx, hy, hz):
        nx, ny, nz = roundf(self.x), roundf(self.y), roundf(self.z)
        return any(nx == hx and ny - i == hy and nz == hz for i in range(height))

    def look(self, dx, dy):
        self.rx = (self.rx + dx) % radians(360)
        self.ry = max(-radians(90), min(radians(90), self.ry + dy))

    def move(self, dt, sz, sx, jump):
        """Walk or fly, fall, and collide, in steps
        small enough that the player cannot pass through a block."""
        vx, vy, vz = self.motion_vector(sz, sx)
        if jump:
            if self.flying:
                vy = 1
            elif self.dy == 0:
                self.dy = 8
        speed = 20 if self.flying else 5
        estimate = roundf(((vx * speed) ** 2 + (vy * speed + abs(self.dy) * 2) ** 2 + (vz * speed) ** 2) ** 0.5 * dt * 8)
        step = max(8, estimate)
        ut = dt / step
        vx, vy, vz = vx * ut * speed, vy * ut * speed, vz * ut * speed
        for _ in range(step):
            if self.flying:
                self.dy = 0
            else:
                self.dy = max(self.dy - ut * 25, -250)
            self.x += vx
            self.y += vy + self.dy * ut
            self.z += vz
            if self.collide(2):
                self.dy = 0
        if self.y < 0:
            self.y = self.highest_block(self.x, self.z) + 2

    # -- clicks --

    def on_left_click(self):
        hx, hy, hz, hw = self.hit_test(False)
        if 0 < hy < 256 and is_destructable(hw):
            self.set_block(hx, hy, hz, 0)
            self.record_block(hx, hy, hz, 0)
            if is_plant(self.get_block(hx, hy + 1, hz)):
                self.set_block(hx, hy + 1, hz, 0)

    def on_right_click(self):
        hx, hy, hz, hw = self.hit_test(True)
        if 0 < hy < 256 and is_obstacle(hw) and not self.intersects_block(2, hx, hy, hz):
            self.set_block(hx, hy, hz, ITEMS[self.item_index])
            self.record_block(hx, hy, hz, ITEMS[self.item_index])

    def on_middle_click(self):
        hw = self.hit_test(False)[3]
        if hw in ITEMS:
            self.item_index = ITEMS.index(hw)

    def on_light(self):
        hx, hy, hz, hw = self.hit_test(False)
        if 0 < hy < 256 and is_destructable(hw):
            self.toggle_light(hx, hy, hz)


def chunk_visible(planes, p, q, miny, maxy, ortho):
    """Whether any corner of the chunk's box is inside every plane of the
    view frustum (the near and far planes do not apply to ortho views)."""
    x, z, d = p * CHUNK_SIZE - 1, q * CHUNK_SIZE - 1, CHUNK_SIZE + 1
    points = [(x + dx, y, z + dz) for y in (miny, maxy) for dz in (0, d) for dx in (0, d)]
    for a, b, c, e in planes[:4] if ortho else planes:
        if all(a * px + b * py + c * pz + e < 0 for px, py, pz in points):
            return False
    return True
