"""The saved world, as a text file: the blocks the player changed, the lights,
and where the player stood, so the next game starts where this one left.
A line is "B p q x y z w" for a block of chunk (p, q), "L p q x y z w" for
a light, or "S x y z rx ry" for the player."""


class Store:
    def __init__(self, path):
        self.path = path
        self.blocks, self.lights = {}, {}
        self.state = None
        self.changed = False
        try:
            with open(path) as file:
                lines = file.read().splitlines()
        except OSError:
            return
        for line in lines:
            match line.split():
                case ["B" | "L" as kind, *numbers] if len(numbers) == 6:
                    p, q, x, y, z, w = map(int, numbers)
                    table = self.blocks if kind == "B" else self.lights
                    table.setdefault((p, q), {})[x, y, z] = w
                case ["S", *numbers] if len(numbers) == 5:
                    self.state = tuple(map(float, numbers))

    def save(self, state):
        lines = [f"{kind} {p} {q} {x} {y} {z} {w}"
                 for kind, table in (("B", self.blocks), ("L", self.lights))
                 for (p, q), cells in table.items() for (x, y, z), w in cells.items()]
        lines.append("S " + " ".join(f"{v:.3f}" for v in state))
        try:
            with open(self.path, "w") as file:
                file.write("\n".join(lines) + "\n")
        except OSError:
            pass  # a host without a writable directory plays without saving
        self.changed = False
