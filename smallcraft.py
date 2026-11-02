"""Small Craft: a block-building sandbox on Small Python and raylib.

smallcraft.c registers raylib, noise and libm; spyc bundles this file, the
craft package and the textures into the program. This file is the main
loop and the keyboard and mouse handlers."""
import raylib as rl
from craft.builder import parse_command
from craft.config import COMMIT_INTERVAL, INVERT_MOUSE, SAVE_PATH, SCROLL_THRESHOLD, WINDOW_HEIGHT, WINDOW_WIDTH
from craft.item import ITEMS
from craft.model import Model
from craft.render import Renderer
from craft.store import Store

CONTROL_KEYS = (rl.KEY_LEFT_CONTROL, rl.KEY_RIGHT_CONTROL, rl.KEY_LEFT_SUPER, rl.KEY_RIGHT_SUPER)


class Input:
    """The input state kept between frames."""

    def __init__(self):
        self.typing = None  # the line being typed, or None
        self.scroll = 0

    def handle(self, m, dt):
        exclusive = rl.is_cursor_hidden()
        control = any(rl.is_key_down(key) for key in CONTROL_KEYS)
        self.on_keys(m, exclusive, control)
        self.on_mouse(m, exclusive, control)
        if exclusive:
            dx, dy = rl.get_mouse_delta()
            m.look(dx * 0.0025, (dy if INVERT_MOUSE else -dy) * 0.0025)
        sz = sx = 0
        jump = False
        if self.typing is None:
            m.ortho = 64 if rl.is_key_down(rl.KEY_F) else 0
            m.fov = 15 if rl.is_key_down(rl.KEY_LEFT_SHIFT) else 65
            sz = rl.is_key_down(rl.KEY_S) - rl.is_key_down(rl.KEY_W)
            sx = rl.is_key_down(rl.KEY_D) - rl.is_key_down(rl.KEY_A)
            m.look((rl.is_key_down(rl.KEY_RIGHT) - rl.is_key_down(rl.KEY_LEFT)) * dt,
                   (rl.is_key_down(rl.KEY_UP) - rl.is_key_down(rl.KEY_DOWN)) * dt)
            jump = rl.is_key_down(rl.KEY_SPACE)
        m.move(dt, sz, sx, jump)

    def on_keys(self, m, exclusive, control):
        if self.typing is not None and rl.is_key_pressed(rl.KEY_BACKSPACE):
            self.typing = self.typing[:-1]
        if rl.is_key_pressed(rl.KEY_ESCAPE):
            if self.typing is not None:
                self.typing = None
            elif exclusive:
                rl.enable_cursor()
        if rl.is_key_pressed(rl.KEY_ENTER):
            if self.typing is not None:
                text, self.typing = self.typing.strip(), None
                if text.startswith("/"):
                    parse_command(m, text)
                elif text:
                    m.add_message(text)
            elif control:
                m.on_right_click()
            else:
                m.on_left_click()
        while char := rl.get_char_pressed():
            if self.typing is not None:
                if " " <= char < "\x7f":
                    self.typing += char
            elif char == "t":
                self.typing = ""
            elif char == "/":
                self.typing = "/"
        if self.typing is None:
            if rl.is_key_pressed(rl.KEY_TAB):
                m.flying = not m.flying
            for key in range(rl.KEY_ONE, rl.KEY_NINE + 1):
                if rl.is_key_pressed(key):
                    m.item_index = key - rl.KEY_ONE
            if rl.is_key_pressed(rl.KEY_ZERO):
                m.item_index = 9
            if rl.is_key_pressed(rl.KEY_E):
                m.item_index = (m.item_index + 1) % len(ITEMS)
            if rl.is_key_pressed(rl.KEY_R):
                m.item_index = (m.item_index - 1) % len(ITEMS)

    def on_mouse(self, m, exclusive, control):
        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            if not exclusive:
                rl.disable_cursor()
            elif control:
                m.on_right_click()
            else:
                m.on_left_click()
        if exclusive and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_RIGHT):
            if control:
                m.on_light()
            else:
                m.on_right_click()
        if exclusive and rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_MIDDLE):
            m.on_middle_click()
        self.scroll += rl.get_mouse_wheel_move()
        if self.scroll < -SCROLL_THRESHOLD:
            m.item_index = (m.item_index + 1) % len(ITEMS)
            self.scroll = 0
        if self.scroll > SCROLL_THRESHOLD:
            m.item_index = (m.item_index - 1) % len(ITEMS)
            self.scroll = 0


def main():
    rl.init_window(WINDOW_WIDTH, WINDOW_HEIGHT, "Small Craft")
    rl.disable_cursor()
    store = Store(SAVE_PATH)
    view = Renderer()
    m = Model(store)
    controls = Input()
    clock = {"previous": rl.get_time(), "commit": rl.get_time()}

    def frame():
        now = rl.get_time()
        dt = min(max(now - clock["previous"], 0), 0.2)
        clock["previous"] = now
        controls.handle(m, dt)
        if now - clock["commit"] > COMMIT_INTERVAL:
            clock["commit"] = now
            store.save((m.x, m.y, m.z, m.rx, m.ry))
        m.delete_chunks()
        view.draw(m, controls.typing)

    # In a browser, run returns at once and the page calls frame from then on.
    if rl.run(frame):
        store.save((m.x, m.y, m.z, m.rx, m.ry))
        rl.close_window()


main()
