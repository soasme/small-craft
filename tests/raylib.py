"""A stand-in for the host's raylib module: a clock the tests set, and
meshes that are only counted."""
now = 0.0
meshes = {}  # vertex counts of the meshes loaded and not unloaded
loaded = 0


def get_time():
    return now


def load_mesh(data, stride):
    global loaded
    assert len(data) % (stride * 3) == 0 and data
    handle = loaded
    loaded += 1
    meshes[handle] = len(data) // stride
    return handle


def unload_mesh(handle):
    del meshes[handle]
