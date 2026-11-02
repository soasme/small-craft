"""Touch controls, for phones and tablets: a stick at the bottom left to
walk, buttons at the bottom right, and any other finger drags to look.
They appear once the screen is first touched."""
import raylib as rl

LOOK_SPEED = 0.006  # radians per pixel dragged
LABELS = {"jump": "Jump", "break": "Break", "place": "Place", "item": "Block", "fly": "Fly"}


def layout(width, height):
    """The stick's centre and radius, and each button's centre and radius."""
    u = min(width, height) / 8
    stick = (1.8 * u, height - 1.8 * u, 1.3 * u)
    spots = {"jump": (1.2, 1.2), "break": (2.7, 1.2), "place": (1.2, 2.7), "item": (2.7, 2.7), "fly": (1.2, 4.2)}
    buttons = {name: (width - dx * u, height - dy * u, 0.65 * u) for name, (dx, dy) in spots.items()}
    return stick, buttons


def inside(x, y, circle):
    cx, cy, r = circle
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


class Touch:
    def __init__(self):
        self.active = False  # the screen has been touched
        self.fingers = {}  # touch id: (what it holds, last x, last y)
        self.stick = (0, 0)  # the stick's (sz, sx), for drawing

    def update(self, width, height):
        """Read the fingers. Return walking (sz, sx), looking (dx, dy) in
        radians, whether jump is held, and the buttons pressed this frame."""
        stick, buttons = layout(width, height)
        sz = sx = 0
        look_x = look_y = 0
        jump = False
        pressed = set()
        held = {}
        for finger, x, y in rl.get_touches():
            self.active = True
            role, last_x, last_y = self.fingers.get(finger, (None, x, y))
            if role is None:  # a new finger: what did it land on?
                role = next((name for name, circle in buttons.items() if inside(x, y, circle)), None)
                if role:
                    pressed.add(role)
                else:
                    role = "stick" if inside(x, y, (stick[0], stick[1], stick[2] * 1.4)) else "look"
            if role == "stick":
                dx, dy = x - stick[0], y - stick[1]
                dead = stick[2] / 3
                sx, sz = (dx > dead) - (dx < -dead), (dy > dead) - (dy < -dead)
            elif role == "look":
                look_x += (x - last_x) * LOOK_SPEED
                look_y -= (y - last_y) * LOOK_SPEED
            elif role == "jump":
                jump = True
            held[finger] = role, x, y
        self.fingers = held
        self.stick = sz, sx
        return (sz, sx), (look_x, look_y), jump, pressed

    def draw(self, width, height):
        if not self.active:
            return
        (cx, cy, r), buttons = layout(width, height)
        rl.draw_circle(cx, cy, r, (255, 255, 255, 50))
        sz, sx = self.stick
        rl.draw_circle(cx + sx * r / 2, cy + sz * r / 2, r / 3, (255, 255, 255, 120))
        held = {role for role, _, _ in self.fingers.values()}
        size = max(10, int(r / 3))
        for name, (bx, by, br) in buttons.items():
            rl.draw_circle(bx, by, br, (255, 255, 255, 140 if name in held else 70))
            label = LABELS[name]
            rl.draw_text(label, bx - rl.measure_text(label, size) / 2, by - size / 2, size, (0, 0, 0, 200))
