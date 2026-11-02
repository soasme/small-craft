# Small Craft: one executable holding the Small Python engine (spy/, the
# v0.5.0 sources), raylib's static library, the noise library, and the
# bundle spyc writes from smallcraft.py, the craft package and the textures.
# Needs raylib and pkg-config (brew install raylib pkg-config; Debian/Ubuntu:
# apt install libraylib-dev pkg-config).
CC = cc
CFLAGS = -O2 -std=c11 -Wall -Wextra -Wpedantic
GAME_CFLAGS = $(CFLAGS) -Ispy $(shell pkg-config --cflags raylib)
RAYLIB = $(shell pkg-config --variable=libdir raylib)/libraylib.a
ifeq ($(shell uname),Darwin)
SYSTEM = -framework Cocoa -framework IOKit -framework CoreVideo -framework OpenGL -framework QuartzCore
else
SYSTEM = -lGL -lpthread -ldl -lrt -lX11
endif
OBJ = .obj

# Where the site is served, for the X card's links, and the X account it
# belongs to (for example @soasme; empty leaves twitter:site out).
SITE_URL = https://www.soasme.com/small-craft/
X_SITE =

# The web build: emcc (Emscripten), and raylib's sources, fetched once.
EMCC = emcc
RAYLIB_VERSION = 5.5
RAYLIB_WEB = $(OBJ)/raylib-$(RAYLIB_VERSION)/src
RAYLIB_MODULES = rcore rshapes rtextures rtext rmodels utils
WEB_CFLAGS = -O2 -std=c11 -DPLATFORM_WEB -DGRAPHICS_API_OPENGL_ES3
# raylib's web code uses EM_ASM, which needs GNU C.
RAYLIB_WEB_CFLAGS = -O2 -std=gnu99 -DPLATFORM_WEB -DGRAPHICS_API_OPENGL_ES3
WEB_LDFLAGS = -sUSE_GLFW=3 -sMIN_WEBGL_VERSION=2 -sMAX_WEBGL_VERSION=2 \
	-sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8388608 -sENVIRONMENT=web

build-binary: smallcraft
build: build-binary build-web

smallcraft: smallcraft.c noise.c noise.h $(OBJ)/smallcraft_py.c $(OBJ)/spy.o
	$(CC) $(GAME_CFLAGS) smallcraft.c noise.c $(OBJ)/smallcraft_py.c $(OBJ)/spy.o $(RAYLIB) $(SYSTEM) -lm -o $@

# -c -N smallcraft: the sources and smallcraft_load, for smallcraft.c's own
# main. -x: the C modules smallcraft.c registers. --deps rebuilds when any
# bundled file changes.
$(OBJ)/smallcraft_py.c: smallcraft.py $(OBJ)/assets/textures.py $(OBJ)/spyc
	$(OBJ)/spyc -c -N smallcraft -x raylib -x noise -x libm --minify \
		--deps $(OBJ)/smallcraft_py.d -o $@ smallcraft.py
-include $(OBJ)/smallcraft_py.d

# The textures become a module, written by pack.py running on the engine
# itself. assets is a namespace package (no __init__.py) that spyc finds
# through the symbolic link beside smallcraft.py.
$(OBJ)/assets/textures.py: textures/texture.png textures/sky.png pack.py $(OBJ)/spy
	mkdir -p $(OBJ)/assets
	$(OBJ)/spy pack.py > $@
	ln -sfn $(OBJ)/assets assets

# The engine, its bundler, and its command line (for pack.py).
$(OBJ)/spy.o: spy/spy.c spy/spy.h spy/spy-intrinsics.h spy/spy-unicode.h
	mkdir -p $(OBJ)
	$(CC) $(CFLAGS) -c spy/spy.c -o $@
$(OBJ)/spyc: spy/spyc.c spy/spy.c spy/host.h
	mkdir -p $(OBJ)
	$(CC) $(CFLAGS) spy/spyc.c -lm -o $@
$(OBJ)/spy: spy/cli.c spy/spy-std.c spy/spy-std.h spy/spy-std-modules.h $(OBJ)/spy.o
	$(CC) $(CFLAGS) spy/cli.c spy/spy-std.c $(OBJ)/spy.o -lm -o $@

# web/: index.html, smallcraft.js and smallcraft.wasm, for any static web
# server. The bundle spyc wrote for the desktop is plain C, so the same
# smallcraft_py.c compiles to WebAssembly.
build-web: web/index.html
web/index.html: index.html card.png web/smallcraft.js
	sed -e 's|@URL@|$(SITE_URL)|g' $(if $(X_SITE),-e 's|@X_SITE@|$(X_SITE)|g',-e '/@X_SITE@/d') index.html > $@
	cp card.png web/
	touch web/.nojekyll
web/smallcraft.js: smallcraft.c noise.c noise.h $(OBJ)/smallcraft_py.c spy/spy.c $(OBJ)/web/libraylib.a
	mkdir -p web
	$(EMCC) $(WEB_CFLAGS) -Ispy -I$(RAYLIB_WEB) smallcraft.c noise.c $(OBJ)/smallcraft_py.c spy/spy.c \
		$(OBJ)/web/libraylib.a $(WEB_LDFLAGS) -o $@

$(OBJ)/web/libraylib.a: $(RAYLIB_WEB)/raylib.h
	mkdir -p $(OBJ)/web
	for m in $(RAYLIB_MODULES); do \
		$(EMCC) $(RAYLIB_WEB_CFLAGS) -c $(RAYLIB_WEB)/$$m.c -o $(OBJ)/web/$$m.o || exit 1; done
	emar rcs $@ $(RAYLIB_MODULES:%=$(OBJ)/web/%.o)
$(RAYLIB_WEB)/raylib.h:
	mkdir -p $(OBJ)
	curl -sSfL https://github.com/raysan5/raylib/archive/refs/tags/$(RAYLIB_VERSION).tar.gz | tar xz -C $(OBJ)
	touch $@

# Publish web/ as the gh-pages branch of origin.
deploy-pages: build-web
	tools/deploy-pages.sh web

run: smallcraft
	./smallcraft

# The game without a window, on the spy command line, with stand-ins for
# the host's modules (tests/raylib.py, noise.py, libm.py).
test: $(OBJ)/spy
	rm -rf $(OBJ)/test && mkdir -p $(OBJ)/test
	cp tests/*.py $(OBJ)/test/ && ln -s ../../craft $(OBJ)/test/craft
	cd $(OBJ)/test && ../spy test_game.py

clean:
	rm -rf smallcraft web $(OBJ) assets

.PHONY: build build-binary build-web deploy-pages run test clean
