.DEFAULT_GOAL := all
ZIRAN ?= ./scripts/ziran.sh
CC ?= cc
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
ZIRAN_ROOT = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
RUNTIME_SOURCES = $(wildcard $(ZIRAN_ROOT)/cmd/zir/*.[ch] $(ZIRAN_ROOT)/include/*.h $(ZIRAN_ROOT)/cmd/compiler*.zi)
PROJECT := --project $(LOCK_FLAGS)
BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/arcade
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

.PHONY: all games run test chess-engine-test chess-app-test ui-test compatibility-test install
all: build/arcade games

games:
	python3 scripts/check-games.py
	python3 scripts/build-games.py --ziran '$(ZIRAN)' $(LOCK_FLAGS)

src/catalog.zi: games

build/ziran/libziran.a: ziran.lock $(RUNTIME_SOURCES)
	$(MAKE) -C '$(ZIRAN_ROOT)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

build/arcade: $(wildcard src/*.zi) src/catalog.zi ziran.toml ziran.lock Makefile scripts/ziran.sh build/ziran/libziran.a
	mkdir -p build/generated
	$(ZIRAN) build $(PROJECT) --define PLATFORM_DESKTOP --target=c --entry desktop:main -o build/generated src/desktop.zi
	$(CC) -std=c11 -O2 -ffunction-sections -fdata-sections -I'$(ZIRAN_ROOT)/include' \
		$$(find build/generated -type d -printf ' -iquote %p') $$(find build/generated -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections \
		$$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo) -lm -lpthread -o $@

run: all
	./build/arcade

test: all
	$(ZIRAN) fmt --check src/*.zi
	python3 tests/catalog_test.py
	python3 tests/publisher_test.py
	./build/arcade --list
	sh tests/chess_engine_zi_test.sh '$(ZIRAN)'
	sh tests/chess_app_test.sh '$(ZIRAN)'

chess-engine-test:
	sh tests/chess_engine_zi_test.sh '$(ZIRAN)'

chess-app-test: all
	sh tests/chess_app_test.sh '$(ZIRAN)'

ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy \
		timeout 180s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/arcade_ui_test.py

compatibility-test:
	@test -n "$(INBE_BINARY)" || { echo 'Set INBE_BINARY to the intended compatible host'; exit 2; }
	python3 scripts/verify-compatibility.py --inbe-binary '$(INBE_BINARY)' $(if $(OLDEST_INBE_BINARY),--oldest-inbe-binary '$(OLDEST_INBE_BINARY)',)

install: all
	mkdir -p '$(BIN_DIR)' '$(LIB_DIR)/games' '$(DATA_DIR)/applications'
	install -m 0755 build/arcade '$(LIB_DIR)/arcade'
	install -m 0644 build/games/*.zib '$(LIB_DIR)/games/'
	install -m 0644 build/games/*-preview.png '$(LIB_DIR)/games/'
	ln -sfn '$(LIB_DIR)/arcade' '$(BIN_DIR)/arcade'
	install -m 0644 packaging/xyz.waozi.arcade.desktop '$(DATA_DIR)/applications/'
