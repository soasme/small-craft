"""The parameters a player may want to change."""

WINDOW_WIDTH, WINDOW_HEIGHT = 1024, 768
SCROLL_THRESHOLD = 0.1
MAX_MESSAGES = 4
SAVE_PATH = "craft.txt"
DAY_LENGTH = 600  # seconds
INVERT_MOUSE = False

SHOW_LIGHTS = SHOW_PLANTS = SHOW_CLOUDS = SHOW_TREES = True
SHOW_ITEM = SHOW_CROSSHAIRS = SHOW_WIREFRAME = SHOW_INFO_TEXT = True

# Chunks are built on the one game thread, so the view starts at six chunks
# around the player (change it with /view).
CREATE_CHUNK_RADIUS = RENDER_CHUNK_RADIUS = 6
DELETE_CHUNK_RADIUS = CREATE_CHUNK_RADIUS + 4
CHUNK_SIZE = 32
COMMIT_INTERVAL = 5  # seconds between saves
