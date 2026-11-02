"""4x4 matrices as lists of 16 numbers, column by
column, as OpenGL takes them."""
from libm import cos, sin, tan

PI = 3.14159265359


def normalize(x, y, z):
    d = (x * x + y * y + z * z) ** 0.5
    return x / d, y / d, z / d


def identity():
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def translate(dx, dy, dz):
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, dx, dy, dz, 1]


def rotate(x, y, z, angle):
    x, y, z = normalize(x, y, z)
    s, c = sin(angle), cos(angle)
    m = 1 - c
    return [m * x * x + c, m * x * y - z * s, m * z * x + y * s, 0,
            m * x * y + z * s, m * y * y + c, m * y * z - x * s, 0,
            m * z * x - y * s, m * y * z + x * s, m * z * z + c, 0,
            0, 0, 0, 1]


def multiply(a, b):
    """a times b: b's transformation first, then a's."""
    return [sum(a[i * 4 + r] * b[col * 4 + i] for i in range(4))
            for col in range(4) for r in range(4)]


def apply(data, matrix, count, offset, stride):
    """Transform count 3-vectors of data in place, as positions."""
    for i in range(count):
        d = offset + stride * i
        x, y, z = data[d:d + 3]
        data[d:d + 3] = [matrix[r] * x + matrix[4 + r] * y + matrix[8 + r] * z + matrix[12 + r] for r in range(3)]


def frustum_planes(radius, m):
    znear, zfar = 0.125, radius * 32 + 64
    return [
        (m[3] + m[0], m[7] + m[4], m[11] + m[8], m[15] + m[12]),
        (m[3] - m[0], m[7] - m[4], m[11] - m[8], m[15] - m[12]),
        (m[3] + m[1], m[7] + m[5], m[11] + m[9], m[15] + m[13]),
        (m[3] - m[1], m[7] - m[5], m[11] - m[9], m[15] - m[13]),
        (znear * m[3] + m[2], znear * m[7] + m[6], znear * m[11] + m[10], znear * m[15] + m[14]),
        (zfar * m[3] - m[2], zfar * m[7] - m[6], zfar * m[11] - m[10], zfar * m[15] - m[14]),
    ]


def frustum(left, right, bottom, top, znear, zfar):
    a, w, h, d = 2 * znear, right - left, top - bottom, zfar - znear
    return [a / w, 0, 0, 0, 0, a / h, 0, 0,
            (right + left) / w, (top + bottom) / h, (-zfar - znear) / d, -1,
            0, 0, -a * zfar / d, 0]


def perspective(fov, aspect, znear, zfar):
    ymax = znear * tan(fov * PI / 360)
    xmax = ymax * aspect
    return frustum(-xmax, xmax, -ymax, ymax, znear, zfar)


def ortho(left, right, bottom, top, near, far):
    return [2 / (right - left), 0, 0, 0, 0, 2 / (top - bottom), 0, 0,
            0, 0, -2 / (far - near), 0,
            -(right + left) / (right - left), -(top + bottom) / (top - bottom), -(far + near) / (far - near), 1]


def matrix_2d(width, height):
    return ortho(0, width, 0, height, -1, 1)


def matrix_3d(width, height, x, y, z, rx, ry, fov, ortho_size, radius):
    aspect = width / height
    zfar = radius * 32 + 64
    a = translate(-x, -y, -z)
    a = multiply(rotate(cos(rx), 0, sin(rx), ry), a)
    a = multiply(rotate(0, 1, 0, -rx), a)
    if ortho_size:
        size = ortho_size
        b = ortho(-size * aspect, size * aspect, -size, size, -zfar, zfar)
    else:
        b = perspective(fov, aspect, 0.125, zfar)
    return multiply(b, a)


def matrix_item(width, height, scale):
    aspect = width / height
    size = 64 * scale
    box = height / size / 2
    xoffset = 1 - size / width * 2
    yoffset = 1 - size / height * 2
    a = rotate(0, 1, 0, -PI / 4)
    a = multiply(rotate(1, 0, 0, -PI / 10), a)
    a = multiply(ortho(-box * aspect, box * aspect, -box, box, -1, 1), a)
    return multiply(translate(-xoffset, -yoffset, 0), a)
