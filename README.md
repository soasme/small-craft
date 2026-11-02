# Small Craft

A block-building sandbox whose game is Python, running on the
[Small Python](https://github.com/soasme/small-python) engine and drawn with
[raylib](https://www.raylib.com/). Endless generated terrain with hills,
sand, trees, flowers and clouds; build and break blocks, light the night,
fly, and shape the world with builder commands. The world is saved as you
play.

Everything links into one executable: the engine, raylib's static library,
the noise library, and the game's Python and textures, bundled by `spyc`.
Copy `smallcraft` anywhere and it runs, with no Python file, image, or
raylib library beside it.

## Build and run

Install raylib and pkg-config, then:

```sh
brew install raylib pkg-config    # Debian/Ubuntu: apt install libraylib-dev pkg-config
make run
```

`make` builds the engine from `spy/` (Small Python v0.5.0, vendored), its
bundler `spyc` and command line `spy`, then the game. `make test` runs the
game's tests without a window.

`make build-web` builds the same game for the browser with Emscripten
(`emcc` on the path, or `docker run --rm -v "$PWD":/src -w /src
emscripten/emsdk:4.0.10 make build-web`): it fetches raylib 5.5's sources,
builds them for WebGL 2, and writes a static site to `web/` (`index.html`,
`smallcraft.js`, `smallcraft.wasm`, `card.png`). Serve that directory from
any static web server. `make build` makes both. In the browser the world is
not saved.

`make deploy-pages` force-pushes `web/` to the repository's `gh-pages`
branch; turn on GitHub Pages for that branch to publish it.

On macOS arm64 with `-O2` the executable is 2.9 MB (2.7 MB stripped) and
links only system frameworks (`otool -L smallcraft`).

## Play

| Input | Action |
| --- | --- |
| W A S D | Move |
| Space | Jump; rise while flying |
| Mouse, or arrow keys | Look |
| Left click | Break the block in sight |
| Right click, or Ctrl/Cmd + left click | Place the selected block |
| Ctrl/Cmd + right click | Turn a light on or off in the block in sight |
| Middle click | Select the block in sight |
| 1-9, 0, E, R, scroll wheel | Choose the block to place |
| Tab | Fly or walk |
| Left Shift (held) | Zoom |
| F (held) | Overhead orthographic view |
| T | Type a message; Enter shows it |
| / | Type a command; Enter runs it |
| Esc | Release the mouse (click to capture it again) |

Where the mouse cannot be captured, as inside an embedded frame, drag with
the left button to look and click without dragging to break. On a touch
screen a stick at the bottom left walks, buttons at the bottom right jump,
break, place, choose the block and fly, and dragging anywhere else looks.

### Playing in a post on X

`index.html` carries an X player card: a post linking the published page
shows the game in a frame that plays it. `make build-web` points the card
at `SITE_URL` (default `https://www.soasme.com/small-craft/`, where this repository's Pages are served) and names
the X account in `X_SITE`, if set, for example
`make build-web X_SITE=@handle`. The page must be served over HTTPS, and
X decides whether to show a player card for a site; the card's image is
`card.png`, a 1200x675 screenshot of the game.

A day lasts ten minutes. The world, its lights and where you stand are saved
to `craft.txt` in the working directory every five seconds and on quit.

### Commands

Builder commands work on the last two blocks you placed or broke: `block0`
the latest, `block1` the one before.

| Command | Does |
| --- | --- |
| `/view N` | Draw N chunks around you (1-24; 6 at start) |
| `/copy`, `/paste` | Copy the box between the last two blocks; paste it at the next two |
| `/tree` | Grow a tree at the last block |
| `/cube`, `/fcube` | A hollow or filled box between the last two blocks (same type) |
| `/sphere N`, `/fsphere N` | A hollow or filled sphere of radius N at the last block |
| `/circlex N`, `/circley N`, `/circlez N` | A circle across that axis (`/fcircle...` filled) |
| `/cylinder N`, `/fcylinder N` | A cylinder along the line between the last two blocks |
| `/array N` or `/array X Y Z` | Repeat the last block at the step between the last two |

## How it is built

| File | Holds |
| --- | --- |
| `smallcraft.py` | The main loop and the keyboard, mouse and touch handlers |
| `craft/touch.py` | The on-screen stick and buttons for touch screens |
| `craft/config.py` | Window, view distance, day length, and what to show |
| `craft/item.py` | Block types, the items you can place, and their texture tiles |
| `craft/world.py` | Terrain generation from simplex noise |
| `craft/chunk.py` | A chunk's blocks (one bytearray) and its mesh, with ambient occlusion and lights |
| `craft/cube.py` | Vertices of blocks, plants, the sky sphere and the block outline |
| `craft/matrix.py` | 4x4 matrices: view, projection, frustum planes |
| `craft/model.py` | Loaded chunks, the player's physics, ray casting, editing blocks and lights |
| `craft/builder.py` | The builder commands |
| `craft/store.py` | The save file |
| `craft/render.py`, `craft/shaders.py` | Drawing, and the GLSL block and sky shaders |
| `smallcraft.c` | The host: registers the C modules `raylib`, `noise` and `libm`, runs the bundle |
| `noise.c` | Fractal simplex noise |
| `index.html` | The web page, with its X card; `tools/deploy-pages.sh` publishes the site |
| `pack.py` | Turns `textures/*.png` into a module for the bundle, running on `spy` |
| `spy/` | The Small Python engine, v0.5.0 (see `spy/VERSION`) |

The Python builds every vertex and matrix itself; the host only uploads
vertices to the GPU and draws them with the game's shaders. Chunks are built
on the game's one thread: terrain generation and meshing are generators, and
each frame advances them for up to 8 ms, so loading keeps the frame rate up.
The mesher finds the blocks with a visible face, and how much the blocks
above shade each one, for a whole chunk at once with `bytes.translate` and
big-integer bitwise operations.

### The host's modules

| Module | Functions |
| --- | --- |
| `raylib` | `init_window`, `close_window`, `run(frame)`, `get_time`, `get_fps`, `get_screen_size`; `is_key_down`, `is_key_pressed`, `get_char_pressed`, `is_mouse_button_pressed`, `is_mouse_button_down`, `is_mouse_button_released`, `get_mouse_delta`, `get_touches`, `get_mouse_wheel_move`, `disable_cursor`, `enable_cursor`, `is_cursor_hidden`; `begin_drawing`, `end_drawing`, `clear_background`, `draw_rectangle`, `draw_circle`, `draw_text`, `measure_text`; `load_texture(png, smooth)`, `load_shader(vertex, fragment)`, `set_uniform(shader, name, value)`, `load_mesh(data, stride)`, `unload_mesh`, `draw_mesh(mesh, shader, texture0, texture1)`, `set_depth(test, write)`, `set_culling(on)`, `draw_lines(matrix, points, color)`, `begin_invert`, `end_invert`; `KEY_*` and `MOUSE_BUTTON_*` constants |
| `noise` | `simplex2(x, y, octaves, persistence, lacunarity)`, `simplex3(x, y, z, ...)` |
| `libm` | `sin`, `cos`, `tan`, `acos`, `atan2` |

## Licenses

`spy/LICENSE` covers the engine. The textures, `noise.c` and `noise.h`, and
code derived from the same source are used under the MIT License; see
`NOTICE`.
