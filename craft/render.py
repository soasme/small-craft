"""Drawing: the sky, the chunks, the outline of the block
in sight, the crosshairs, the item in hand, and the text."""
import raylib as rl
from assets.textures import SKY_PNG, TEXTURE_PNG
from .config import SHOW_CROSSHAIRS, SHOW_INFO_TEXT, SHOW_ITEM, SHOW_WIREFRAME, CHUNK_SIZE
from .cube import make_cube, make_cube_wireframe, make_plant, make_sphere
from .item import ITEMS, is_obstacle, is_plant
from .matrix import frustum_planes, matrix_3d, matrix_item
from .model import chunk_visible, chunked
from .shaders import BLOCK_FRAGMENT, BLOCK_VERTEX, SKY_FRAGMENT, SKY_VERTEX

TEXT_SIZE = 20
# Text is black on a translucent white band.
TEXT_COLOR, TEXT_BACKGROUND = (0, 0, 0), (255, 255, 255, 102)
# How long a frame may spend building chunks, in seconds.
CHUNK_BUDGET = 0.008


class Renderer:
    def __init__(self):
        self.atlas = rl.load_texture(TEXTURE_PNG, False)
        self.sky = rl.load_texture(SKY_PNG, True)
        glsl = rl.GLSL_HEADER
        self.block_shader = rl.load_shader(glsl + BLOCK_VERTEX, glsl + BLOCK_FRAGMENT)
        self.sky_shader = rl.load_shader(glsl + SKY_VERTEX, glsl + SKY_FRAGMENT)
        self.sky_mesh = rl.load_mesh(make_sphere(1, 3), 8)
        self.item_meshes = {}

    def item_mesh(self, w):
        """The mesh of the item in hand, at the origin."""
        if w not in self.item_meshes:
            data = []
            if is_plant(w):
                make_plant(data, 0, 1, 0, 0, 0, 0.5, w, 45)
            else:
                make_cube(data, [(0,) * 4] * 6, [(0.5,) * 4] * 6, (True,) * 6, 0, 0, 0, 0.5, w)
            self.item_meshes[w] = rl.load_mesh(data, 10)
        return self.item_meshes[w]

    def draw(self, m, typing, touch):
        width, height = rl.get_screen_size()
        timer = m.time_of_day()
        rl.begin_drawing()
        rl.clear_background((0, 0, 0))
        self.render_sky(m, width, height, timer)
        matrix = matrix_3d(width, height, m.x, m.y, m.z, m.rx, m.ry, m.fov, m.ortho, m.render_radius)
        faces = self.render_chunks(m, matrix, timer)
        if SHOW_WIREFRAME:
            self.render_wireframe(m, matrix)
        # Depth writes stay on: with them off, the next frame's clear would
        # leave this frame's depth behind.
        rl.set_depth(False, True)
        if SHOW_CROSSHAIRS:
            render_crosshairs(width, height)
        if SHOW_ITEM:
            self.render_item(m, width, height)
        render_text(m, faces, typing)
        touch.draw(width, height)
        rl.end_drawing()

    def render_sky(self, m, width, height, timer):
        # The sky is a sphere around the eye, drawn behind everything.
        rl.set_depth(False, False)
        rl.set_culling(False)
        shader = self.sky_shader
        rl.set_uniform(shader, "matrix", matrix_3d(width, height, 0, 0, 0, m.rx, m.ry, m.fov, 0, m.render_radius))
        rl.set_uniform(shader, "timer", timer)
        rl.draw_mesh(self.sky_mesh, shader, self.sky, -1)

    def render_chunks(self, m, matrix, timer):
        """Build what chunks there is time for, then draw those in view;
        return how many faces were drawn."""
        planes = frustum_planes(m.render_radius, matrix)
        m.ensure_chunks(planes, rl.get_time() + CHUNK_BUDGET)
        rl.set_depth(True, True)
        rl.set_culling(True)
        shader = self.block_shader
        rl.set_uniform(shader, "matrix", matrix)
        rl.set_uniform(shader, "camera", (m.x, m.y, m.z))
        rl.set_uniform(shader, "daylight", m.daylight())
        rl.set_uniform(shader, "fog_distance", float(m.render_radius * CHUNK_SIZE))
        rl.set_uniform(shader, "ortho", m.ortho)
        rl.set_uniform(shader, "timer", timer)
        p, q = chunked(m.x), chunked(m.z)
        faces = 0
        for chunk in m.chunks.values():
            if (chunk.mesh is None or max(abs(chunk.p - p), abs(chunk.q - q)) > m.render_radius
                    or not chunk_visible(planes, chunk.p, chunk.q, chunk.miny, chunk.maxy, m.ortho)):
                continue
            rl.draw_mesh(chunk.mesh, shader, self.atlas, self.sky)
            faces += chunk.faces
        return faces

    def render_wireframe(self, m, matrix):
        hx, hy, hz, hw = m.hit_test(False)
        if is_obstacle(hw):
            rl.begin_invert()
            rl.draw_lines(matrix, make_cube_wireframe(hx, hy, hz, 0.53), (255, 255, 255))
            rl.end_invert()

    def render_item(self, m, width, height):
        rl.set_culling(True)
        shader = self.block_shader
        rl.set_uniform(shader, "matrix", matrix_item(width, height, 1))
        rl.set_uniform(shader, "camera", (0.0, 0.0, 5.0))
        rl.draw_mesh(self.item_mesh(ITEMS[m.item_index]), shader, self.atlas, self.sky)


def render_crosshairs(width, height):
    x, y, p = width // 2, height // 2, 10
    rl.begin_invert()
    rl.draw_rectangle(x - 2, y - p, 4, 2 * p, (255, 255, 255))
    rl.draw_rectangle(x - p, y - 2, 2 * p, 4, (255, 255, 255))
    rl.end_invert()


def text_line(text, y):
    rl.draw_rectangle(TEXT_SIZE // 4, y, rl.measure_text(text, TEXT_SIZE) + TEXT_SIZE // 2, TEXT_SIZE + 4, TEXT_BACKGROUND)
    rl.draw_text(text, TEXT_SIZE // 2, y + 2, TEXT_SIZE, TEXT_COLOR)


def render_text(m, faces, typing):
    y = TEXT_SIZE // 2
    if SHOW_INFO_TEXT:
        hour = int(m.time_of_day() * 24)
        am_pm = "a" if hour < 12 else "p"
        hour = hour % 12 or 12
        text_line(f"({chunked(m.x)}, {chunked(m.z)}) ({m.x:.2f}, {m.y:.2f}, {m.z:.2f}) "
                  f"[1, {len(m.chunks)}, {faces * 2}] {hour}{am_pm}m {rl.get_fps()}fps", y)
        y += TEXT_SIZE * 3 // 2
    for message in m.messages:
        text_line(message, y)
        y += TEXT_SIZE * 3 // 2
    if typing is not None:
        text_line(f"> {typing}", y)
