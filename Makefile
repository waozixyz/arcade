.DEFAULT_GOAL := all
ZIRAN ?= ./scripts/ziran.sh
CC ?= cc
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
ZIRAN_ROOT = $(if $(TOOLCHAIN_SOURCE),$(TOOLCHAIN_SOURCE),$(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS)))
KRYON_DIR = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
# The shared Apps controller is built from the locked Apps package. Arcade
# trusts only the reviewed digest committed in apps-controller.sha256.
ENTITY_DIR = $(shell $(ZIRAN) pkg path entity $(LOCK_FLAGS))
APPS_DIR = $(shell $(ZIRAN) pkg path apps $(LOCK_FLAGS))
APPS_BUNDLE := build/apps-ui/apps.zib
APPS_SHA256 := $(shell cat apps-controller.sha256)
INBE_SOURCE ?= $(shell $(ZIRAN) pkg path inbe $(LOCK_FLAGS))
RUNTIME_SOURCES = $(wildcard $(ZIRAN_ROOT)/cmd/zir/*.[ch] $(ZIRAN_ROOT)/include/*.h $(ZIRAN_ROOT)/cmd/compiler*.zi)
PROJECT := --project $(LOCK_FLAGS)
BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/arcade
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

.PHONY: all build/arcade build/shovey standalone-ui-test collection-ui-test scroll-ui-test navigation-ui-test games collection collection-test run test chess-engine-test chess-app-test ui-test inbe-ui-test compatibility-test install
all: collection build/entity.zib build/arcade build/shovey

games:
	python3 scripts/check-games.py
	python3 scripts/build-games.py --ziran '$(ZIRAN)' $(LOCK_FLAGS)

$(APPS_BUNDLE): ziran.lock apps-controller.sha256
	$(ZIRAN) version > /dev/null
	env -u DISPLAY -u WAYLAND_DISPLAY \
		PATH="$(if $(wildcard $(ZIRAN_ROOT)/build/bin/ziran),$(ZIRAN_ROOT)/build/bin,$(CURDIR)/build/toolchain/bin):$$PATH" \
		python3 '$(APPS_DIR)/scripts/build-ui.py' --output '$(abspath $(dir $@))'

collection: games $(APPS_BUNDLE)
	python3 scripts/build-collection.py --ziran '$(ZIRAN)' $(LOCK_FLAGS) \
		--apps-bundle '$(APPS_BUNDLE)' --apps-sha256 '$(APPS_SHA256)'

collection-test:
	python3 tests/collection_test.py

src/catalog.zi: games

build/entity.zib: ziran.lock $(wildcard $(ENTITY_DIR)/src/*.zi)
	python3 scripts/build-entity.py

build/ziran/libziran.a: ziran.lock $(RUNTIME_SOURCES)
	$(MAKE) -C '$(ZIRAN_ROOT)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

build/arcade: build/entity.zib $(wildcard src/*.zi) src/catalog.zi ziran.toml ziran.lock Makefile scripts/build-desktop.py build/ziran/libziran.a
	python3 scripts/build-desktop.py --output '$@'

build/shovey: build/entity.zib $(wildcard src/*.zi) src/catalog.zi ziran.toml ziran.lock Makefile scripts/build-desktop.py build/ziran/libziran.a
	python3 scripts/build-desktop.py --standalone-shovey --output '$@'

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
	python3 tests/sound_test.py

chess-engine-test:
	sh tests/chess_engine_zi_test.sh '$(ZIRAN)'

chess-app-test: all
	sh tests/chess_app_test.sh '$(ZIRAN)'

ui-test: collection-ui-test

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
		timeout 240s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/shovey_standalone_ui_test.py --binary '$(CURDIR)/build/shovey' --inbe-source '$(INBE_SOURCE)'

collection-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_AUDIODRIVER=dummy \
		timeout 240s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/collection_ui_test.py --binary '$(CURDIR)/build/arcade' --inbe-source '$(INBE_SOURCE)'

scroll-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy \
		timeout 120s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/shovey_scroll_ui_test.py \
		--binary '$(CURDIR)/build/arcade' --binary '$(CURDIR)/build/shovey' --inbe-source '$(INBE_SOURCE)'

navigation-ui-test: all
	env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
		-u SESSION_MANAGER -u GDK_DISPLAY YUE_DESKTOP_RECOVERY=0 SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy \
		timeout 150s xvfb-run -a -n 400 -s '-screen 0 1280x1000x24' python3 tests/standalone_navigation_ui_test.py \
		--binary '$(CURDIR)/build/arcade' --binary '$(CURDIR)/build/shovey' --inbe-source '$(INBE_SOURCE)'

install: all
	mkdir -p '$(BIN_DIR)' '$(LIB_DIR)/games' '$(DATA_DIR)/applications'
	mkdir -p '$(LIB_DIR)/startup/shovey'
	install -m 0644 build/startup/shovey/*.png '$(LIB_DIR)/startup/shovey/'
	install -m 0755 build/arcade '$(LIB_DIR)/arcade.new'
	mv -f '$(LIB_DIR)/arcade.new' '$(LIB_DIR)/arcade'
	install -m 0755 build/shovey '$(LIB_DIR)/shovey.new'
	mv -f '$(LIB_DIR)/shovey.new' '$(LIB_DIR)/shovey'
	install -m 0644 build/entity.zib build/arcade.zib build/arcade.json build/shovey.zib build/shovey.json '$(LIB_DIR)/'
	install -m 0644 build/games/*.zib '$(LIB_DIR)/games/'
	install -m 0644 build/games/*-preview.png '$(LIB_DIR)/games/'
	ln -sfn '$(LIB_DIR)/arcade' '$(BIN_DIR)/arcade'
	ln -sfn '$(LIB_DIR)/shovey' '$(BIN_DIR)/shovey'
	mkdir -p '$(DATA_DIR)/icons/hicolor/256x256/apps'
	install -m 0644 build/shovey-icon.png '$(DATA_DIR)/icons/hicolor/256x256/apps/xyz.waozi.shovey.png'
	install -m 0644 packaging/xyz.waozi.arcade.desktop packaging/xyz.waozi.shovey.desktop '$(DATA_DIR)/applications/'

.PHONY: android-shovey android-shovey-release
android-shovey: collection
	python3 scripts/build-android.py

android-shovey-release: collection
	python3 scripts/build-android.py --release

.PHONY: shovey-linux-download
shovey-linux-download: collection build/entity.zib build/shovey
	python3 scripts/package-shovey.py linux
