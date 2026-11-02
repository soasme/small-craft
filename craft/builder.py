"""The builder commands, typed after a slash. They work on the last two
blocks the player placed or removed (block0 is the latest)."""


def sign(x):
    return (x > 0) - (x < 0)


def copy(m):
    m.copy0, m.copy1 = m.block0, m.block1


def paste(m):
    c1, c2, p1, p2 = m.copy1, m.copy0, m.block1, m.block0
    scx, scz = sign(c2[0] - c1[0]), sign(c2[2] - c1[2])
    spx, spz = sign(p2[0] - p1[0]), sign(p2[2] - p1[2])
    oy = p1[1] - c1[1]
    dx, dz = abs(c2[0] - c1[0]), abs(c2[2] - c1[2])
    for y in range(256):
        for x in range(dx + 1):
            for z in range(dz + 1):
                w = m.get_block(c1[0] + x * scx, y, c1[2] + z * scz)
                m.builder_block(p1[0] + x * spx, y + oy, p1[2] + z * spz, w)


def array(m, b1, b2, xc, yc, zc):
    if b1[3] != b2[3]:
        return
    dx, dy, dz = b2[0] - b1[0], b2[1] - b1[1], b2[2] - b1[2]
    for i in range(xc if dx else 1):
        for j in range(yc if dy else 1):
            for k in range(zc if dz else 1):
                m.builder_block(b1[0] + dx * i, b1[1] + dy * j, b1[2] + dz * k, b1[3])


def cube(m, b1, b2, fill):
    if b1[3] != b2[3]:
        return
    lo = [min(b1[i], b2[i]) for i in range(3)]
    hi = [max(b1[i], b2[i]) for i in range(3)]
    a = sum(lo[i] == hi[i] for i in range(3))
    for x in range(lo[0], hi[0] + 1):
        for y in range(lo[1], hi[1] + 1):
            for z in range(lo[2], hi[2] + 1):
                if not fill:
                    n = sum(v == lo[i] or v == hi[i] for i, v in enumerate((x, y, z)))
                    if n <= a:
                        continue
                m.builder_block(x, y, z, b1[3])


def sphere(m, center, radius, fill, fx, fy, fz):
    cx, cy, cz, w = center
    for x in range(cx - radius, cx + radius + 1):
        if fx and x != cx:
            continue
        for y in range(cy - radius, cy + radius + 1):
            if fy and y != cy:
                continue
            for z in range(cz - radius, cz + radius + 1):
                if fz and z != cz:
                    continue
                # Keep the blocks the sphere's surface passes through (or,
                # filled, every block it touches).
                inside, outside = False, fill
                for ox in (-0.5, 0.5):
                    for oy in (-0.5, 0.5):
                        for oz in (-0.5, 0.5):
                            d = ((x + ox - cx) ** 2 + (y + oy - cy) ** 2 + (z + oz - cz) ** 2) ** 0.5
                            if d < radius:
                                inside = True
                            else:
                                outside = True
                if inside and outside:
                    m.builder_block(x, y, z, w)


def cylinder(m, b1, b2, radius, fill):
    if b1[3] != b2[3]:
        return
    lo = [min(b1[i], b2[i]) for i in range(3)]
    hi = [max(b1[i], b2[i]) for i in range(3)]
    axes = [lo[i] != hi[i] for i in range(3)]
    if sum(axes) != 1:
        return
    axis = axes.index(True)
    for v in range(lo[axis], hi[axis] + 1):
        center = [*lo, b1[3]]
        center[axis] = v
        sphere(m, tuple(center), radius, fill, *axes)


def tree(m, block):
    bx, by, bz, _ = block
    for y in range(by + 3, by + 8):
        for dx in range(-3, 4):
            for dz in range(-3, 4):
                if dx * dx + (y - (by + 4)) ** 2 + dz * dz < 11:
                    m.builder_block(bx + dx, y, bz + dz, 15)
    for y in range(by, by + 7):
        m.builder_block(bx, y, bz, 5)


def parse_command(m, text):
    """Run a command such as "/sphere 5"; report one that is unknown."""
    name, *numbers = text.split()
    try:
        numbers = [int(n) for n in numbers]
    except ValueError:
        numbers = None
    match name, numbers:
        case "/view", [radius]:
            if 1 <= radius <= 24:
                m.create_radius = m.render_radius = radius
                m.delete_radius = radius + 4
            else:
                m.add_message("Viewing distance must be between 1 and 24.")
        case "/copy", []:
            copy(m)
        case "/paste", []:
            paste(m)
        case "/tree", []:
            tree(m, m.block0)
        case "/array", [xc, yc, zc]:
            array(m, m.block1, m.block0, xc, yc, zc)
        case "/array", [count]:
            array(m, m.block1, m.block0, count, count, count)
        case "/fcube" | "/cube", []:
            cube(m, m.block0, m.block1, name == "/fcube")
        case "/fsphere" | "/sphere", [radius]:
            sphere(m, m.block0, radius, name == "/fsphere", False, False, False)
        case "/fcirclex" | "/circlex", [radius]:
            sphere(m, m.block0, radius, name[1] == "f", True, False, False)
        case "/fcircley" | "/circley", [radius]:
            sphere(m, m.block0, radius, name[1] == "f", False, True, False)
        case "/fcirclez" | "/circlez", [radius]:
            sphere(m, m.block0, radius, name[1] == "f", False, False, True)
        case "/fcylinder" | "/cylinder", [radius]:
            cylinder(m, m.block0, m.block1, radius, name == "/fcylinder")
        case _:
            m.add_message(f"Unknown command: {text}")
