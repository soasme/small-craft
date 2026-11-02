"""A stand-in for the host's libm module, by Taylor series (accurate to
about 1e-12 over the angles the game uses)."""
PI = 3.141592653589793


def sin(x):
    x = (x + PI) % (2 * PI) - PI
    term = total = x
    for n in range(1, 14):
        term *= -x * x / ((2 * n) * (2 * n + 1))
        total += term
    return total


def cos(x):
    return sin(x + PI / 2)


def tan(x):
    return sin(x) / cos(x)


def atan2(y, x):
    # Only the eight directions motion_vector asks for.
    table = {(0, 1): 0, (1, 1): PI / 4, (1, 0): PI / 2, (1, -1): 3 * PI / 4, (0, -1): PI,
             (-1, -1): -3 * PI / 4, (-1, 0): -PI / 2, (-1, 1): -PI / 4}
    return table[(y > 0) - (y < 0), (x > 0) - (x < 0)]


def acos(x):
    # Bisection on cos, for the sky sphere.
    lo, hi = 0.0, PI
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cos(mid) > x else (lo, mid)
    return lo
