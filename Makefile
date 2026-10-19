.DEFAULT_GOAL := all
ZIRAN ?= ./scripts/ziran.sh
CC ?= cc
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
ZIRAN_ROOT = $(if $(TOOLCHAIN_SOURCE),$(TOOLCHAIN_SOURCE),$(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS)))
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
APPS_BUNDLE ?= $(APPS_SOURCE)/build/ui/apps.zib
HANDOFF_MAP := $(abspath build/collection-source-check/module-map.tsv)
HANDOFF_FLAGS = --module-map $(HANDOFF_MAP) --compiler-dir $(ZIRAN_ROOT)/build/bin
INBE_SOURCE ?= $(shell $(ZIRAN) pkg path inbe $(LOCK_FLAGS))
RUNTIME_SOURCES = $(wildcard $(ZIRAN_ROOT)/cmd/zir/*.[ch] $(ZIRAN_ROOT)/include/*.h $(ZIRAN_ROOT)/cmd/compiler*.zi)
PROJECT := --project $(LOCK_FLAGS)
BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/arcade
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

.PHONY: all build/arcade build/pushy source-map standalone-ui-test collection-ui-test games collection collection-test run test chess-engine-test chess-app-test pushy-engine-test pushy-ui-test ui-test inbe-ui-test compatibility-test install
all: collection build/arcade build/pushy

games: source-map
	python3 scripts/check-games.py
	python3 scripts/build-games.py --ziran '$(ZIRAN)' $(LOCK_FLAGS) $(HANDOFF_FLAGS)

# Apps currently has no public source pin. This explicit handoff mode never
# edits production locks or treats a locally mapped graph as a release graph.
source-map:
	@test -n "$(APPS_SOURCE)" -a -n "$(APPS_SHA256)" || { echo 'Set APPS_SOURCE and the reviewed APPS_SHA256'; exit 2; }
	python3 scripts/local-apps-map.py --consumer '$(CURDIR)' --apps '$(APPS_SOURCE)' --output '$(HANDOFF_MAP)'

collection: games
	python3 scripts/build-collection.py --ziran '$(ZIRAN)' $(LOCK_FLAGS) $(HANDOFF_FLAGS) \
		--apps-bundle '$(APPS_BUNDLE)' --apps-sha256 '$(APPS_SHA256)'

collection-test:
	python3 tests/collection_test.py

src/catalog.zi: games

build/ziran/libziran.a: ziran.lock $(RUNTIME_SOURCES)
	$(MAKE) -C '$(ZIRAN_ROOT)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

build/arcade: $(wildcard src/*.zi) src/catalog.zi ziran.toml ziran.lock Makefile scripts/build-desktop.py scripts/local-apps-map.py build/ziran/libziran.a
	python3 scripts/build-desktop.py --apps-source '$(APPS_SOURCE)' --toolchain '$(ZIRAN_ROOT)' --output '$@'

build/pushy: $(wildcard src/*.zi) src/catalog.zi ziran.toml ziran.lock Makefile scripts/build-desktop.py scripts/local-apps-map.py build/ziran/libziran.a
	python3 scripts/build-desktop.py --apps-source '$(APPS_SOURCE)' --toolchain '$(ZIRAN_ROOT)' --standalone-pushy --output '$@'

run: all
	./build/arcade

test: all
	$(ZIRAN) fmt --check src/*.zi apps/chess/*.zi tests/chess_engine_behavior.zi tests/chess_app_behavior.zi
	python3 tests/chess_locale_test.py
	INBE_SOURCE='$(INBE_SOURCE)' python3 tests/catalog_test.py
	python3 tests/publisher_test.py
	./build/arcade --list
	sh tests/chess_engine_zi_test.sh '$(ZIRAN)'
	sh tests/chess_app_test.sh '$(ZIRAN)'
	$(ZIRAN) fmt --check apps/pushy/*.zi tests/pushy_engine_behavior.zi
	python3 tests/pushy_levels_test.py
	sh tests/pushy_engine_test.sh '$(ZIRAN)'
	python3 tests/pushy_island_levels_test.py
	python3 tests/pushy_island_assets_test.py
	sh tests/pushy_island_engine_test.sh '$(ZIRAN)'
	TOOLCHAIN_SOURCE='$(ZIRAN_ROOT)' APPS_SOURCE='$(APPS_SOURCE)' python3 tests/sound_test.py

chess-engine-test:
	sh tests/chess_engine_zi_test.sh '$(ZIRAN)'

chess-app-test: all
	sh tests/chess_app_test.sh '$(ZIRAN)'

pushy-engine-test:
	sh tests/pushy_engine_test.sh '$(ZIRAN)'

pushy-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy INBE_SOURCE='$(INBE_SOURCE)' \
		timeout 180s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/pushy_ui_test.py

ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy INBE_SOURCE='$(INBE_SOURCE)' \
		timeout 180s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/arcade_ui_test.py

inbe-ui-test:
	@test -n "$(INBE_BINARY)" || { echo 'Set INBE_BINARY to the intended compatible host'; exit 2; }
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy APP_NO_TRAY=1 \
		timeout 240s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/chess_inbe_ui_test.py '$(INBE_BINARY)'

compatibility-test:
	@test -n "$(INBE_BINARY)" || { echo 'Set INBE_BINARY to the intended compatible host'; exit 2; }
	python3 scripts/verify-compatibility.py --inbe-binary '$(INBE_BINARY)' $(if $(OLDEST_INBE_BINARY),--oldest-inbe-binary '$(OLDEST_INBE_BINARY)',)

standalone-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy \
		timeout 240s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/pushy_standalone_ui_test.py --inbe-source '$(INBE_SOURCE)' --toolchain '$(ZIRAN_ROOT)'

collection-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy \
		timeout 240s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/collection_ui_test.py --binary '$(CURDIR)/build/arcade' --inbe-source '$(INBE_SOURCE)'

install: all
	mkdir -p '$(BIN_DIR)' '$(LIB_DIR)/games' '$(DATA_DIR)/applications'
	install -m 0755 build/arcade '$(LIB_DIR)/arcade.new'
	mv -f '$(LIB_DIR)/arcade.new' '$(LIB_DIR)/arcade'
	install -m 0755 build/pushy '$(LIB_DIR)/pushy.new'
	mv -f '$(LIB_DIR)/pushy.new' '$(LIB_DIR)/pushy'
	install -m 0644 build/arcade.zib build/arcade.json build/pushy.zib build/pushy.json '$(LIB_DIR)/'
	install -m 0644 build/games/*.zib '$(LIB_DIR)/games/'
	install -m 0644 build/games/*-preview.png '$(LIB_DIR)/games/'
	ln -sfn '$(LIB_DIR)/arcade' '$(BIN_DIR)/arcade'
	ln -sfn '$(LIB_DIR)/pushy' '$(BIN_DIR)/pushy'
	install -m 0644 packaging/xyz.waozi.arcade.desktop packaging/xyz.waozi.pushy.desktop '$(DATA_DIR)/applications/'
