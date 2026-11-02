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

run: smallcraft
	./smallcraft

# The game without a window, on the spy command line, with stand-ins for
# the host's modules (tests/raylib.py, noise.py, libm.py).
test: $(OBJ)/spy
	rm -rf $(OBJ)/test && mkdir -p $(OBJ)/test
	cp tests/*.py $(OBJ)/test/ && ln -s ../../craft $(OBJ)/test/craft
	cd $(OBJ)/test && ../spy test_game.py

clean:
	rm -rf smallcraft $(OBJ) assets

.PHONY: run test clean
