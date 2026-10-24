"""Run the standalone Shovey app privately: its covers, Classic and Editor
opening directly from them, Island staying unavailable, and independent saves."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    root = Path(__file__).resolve().parents[1]
    output = root / 'build/shovey-standalone-ui-test'
    # Classic's heading counts its levels, which Shovey's level file lists.
    shovey = Path(subprocess.check_output([str(root / 'scripts/ziran.sh'), 'pkg', 'path', 'shovey'], text=True).strip())
    classic_levels = len(json.loads((shovey / 'levels/approved.json').read_text())['levels'])
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver
    driver = UiDriver(output / 'driver')

    @contextlib.contextmanager
    def application(profile, name):
        log_path = output / (name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                     env=os.environ | driver.environment() |
                                     {'ARCADE_DATA': str(profile), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Play', role='button')
                assert not driver.find(label='Shovey Island', role='button'), 'Island must stay unavailable'
                driver.wait(label='Next', role='button')
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def move_until_saved(record):
        before = record.read_bytes() if record.exists() else b''
        for key in ('left', 'up', 'right', 'down'):
            driver.key(key)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if record.exists() and record.read_bytes() != before:
                    return record.read_bytes()
                time.sleep(.05)
        raise AssertionError(f'No move was saved to {record}')

    def campaign_progress(data):
        # Animals keep wandering while the window rotates. Campaign unlocks,
        # completion marks, player state and board identity must stay intact.
        assert data[:2] in (b'C2', b'C3', b'C4')
        assert data[179:181] in (b'P1', b'P2', b'P3')
        return data[:179 + 32], data[-8:]

    def swipe_beside_board_until_saved(record):
        """A swipe on the game screen moves Shovey even where the board is not."""
        nodes = driver.tree()
        screen = nodes[0]
        # The board is the box Shovey stands in, not the slate behind the screen.
        shovey_image = next(node for node in nodes if node['kind'] == 'image' and node['label'] == 'Shovey')
        sx, sy = shovey_image['x'] + shovey_image['width'] / 2, shovey_image['y'] + shovey_image['height'] / 2
        board = max((node for node in nodes if node['kind'] == 'box' and node['visible'] and node['key'] != 19990 and
                     node['x'] <= sx <= node['x'] + node['width'] and node['y'] <= sy <= node['y'] + node['height']),
                    key=lambda node: node['width'] * node['height'])
        left_gap = board['x'] - screen['x']
        below_gap = screen['y'] + screen['height'] - (board['y'] + board['height'])
        if left_gap >= below_gap:
            x, y = screen['x'] + left_gap / 2, board['y'] + board['height'] / 2
        else:
            x, y = board['x'] + board['width'] / 2, board['y'] + board['height'] + below_gap / 2
        # The portrait layout has a 24 px margin; a vertical swipe fits there.
        assert max(left_gap, below_gap) > 8, f'no room beside the board: {board} in {screen}'
        before = record.read_bytes()
        for dx, dy in ((-80, 0), (0, -80), (80, 0), (0, 80)):
            driver.drag((x, y), (x + dx, y + dy))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if record.read_bytes() != before:
                    return
                time.sleep(.05)
        raise AssertionError(f'A swipe beside the board at {x}, {y} moved nothing')

    def board_and_player(board_key=22000):
        board = driver.find(key=board_key, visible=True)[0]
        players = driver.find(label='Shovey', role='image', visible=True)
        assert len(players) == 1, 'Only the player may be labelled Shovey; terrain must have its own name'
        player = players[0]
        return board, player

    def resize_owned_window(child, width, height):
        windows = subprocess.check_output(
            ['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
        assert len(windows) == 1
        window = windows[0]
        owner = subprocess.check_output(['xdotool', 'getwindowpid', window], text=True).strip()
        assert owner == str(child.pid)
        subprocess.run(['xdotool', 'windowsize', '--sync', window, str(width), str(height)], check=True)
        subprocess.run(['xdotool', 'windowmove', window, '0', '0'], check=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            screen = driver.tree()[0]
            if (screen['width'], screen['height']) == (width, height):
                driver.wait_idle(frames=3)
                return window
            time.sleep(.05)
        raise AssertionError('Shovey did not adopt the resized window')

    def swipe_in_visible_direction(board_key=22000):
        board, player = board_and_player(board_key)
        before = UiDriver.center(player)
        start = (board['x'] + board['width'] / 2, board['y'] + board['height'] / 2)
        for dx, dy in ((-100, 0), (0, -100), (100, 0), (0, 100)):
            driver.drag(start, (start[0] + dx, start[1] + dy))
            deadline = time.monotonic() + .8
            while time.monotonic() < deadline:
                _, player = board_and_player(board_key)
                after = UiDriver.center(player)
                moved_x, moved_y = after[0] - before[0], after[1] - before[1]
                if abs(moved_x) + abs(moved_y) > 2:
                    if dx:
                        assert moved_x * dx > 0 and abs(moved_y) < 2, 'horizontal swipe moved in another direction'
                    else:
                        assert moved_y * dy > 0 and abs(moved_x) < 2, 'vertical swipe moved in another direction'
                    return
                time.sleep(.05)
        raise AssertionError('No visible swipe direction moved Shovey')

    with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as temporary:
        profile = Path(temporary)
        classic = profile / 'games/arcade.shovey/records/campaign'
        with application(profile, 'play') as child:
            assert not driver.find(label='Arcade', role='text')
            driver.press(label='Play', role='button')
            driver.wait(label=f'Level 1 / {classic_levels}')
            # The first level asks how to move: swipe and tap, or the pad.
            driver.wait(label='How do you want to move?', role='text')
            assert driver.find(label='Swipe and tap', visible=True) and driver.find(label='Movement pad', visible=True)
            for width, height in ((412, 860), (960, 600)):
                window = resize_owned_window(child, width, height)
                driver.wait_idle(frames=5)
                orientation = 'landscape' if width > height else 'portrait'
                subprocess.run(['import', '-window', window, str(output / ('controls-choice-' + orientation + '.png'))], check=True)
            resize_owned_window(child, 480, 820)
            driver.press(label='Swipe and tap')
            driver.wait_gone(label='How do you want to move?', role='text')
            assert (profile / 'games/arcade.shovey-player/records/controls').read_text() == 'off'
            assert not driver.find(label='Continue', role='button'), 'Classic must open straight on a level'
            assert driver.find(label='Shovey', role='image', visible=True), 'Shovey must be drawn as a picture'
            assert driver.find(label='Back', role='button', visible=True), 'Classic lacks its return control'
            driver.press(label='Mute', role='button')
            driver.wait(label='Unmute', role='button')
            assert (profile / 'games/arcade.shovey-player/records/sound').read_text() == 'muted'
            driver.press(label='Unmute', role='button')
            driver.wait(label='Mute', role='button')
            assert (profile / 'games/arcade.shovey-player/records/sound').read_text() == 'on'
            driver.press(label='Levels', role='button')
            driver.wait(label='Continue', role='button')
            portrait_preview = driver.find(label='1', role='image', visible=True)[0]
            assert abs(portrait_preview['width'] / portrait_preview['height'] - 3 / 5) < .01
            window = resize_owned_window(child, 960, 600)
            landscape_preview = driver.find(label='1', role='image', visible=True)[0]
            assert abs(landscape_preview['width'] / landscape_preview['height'] - 5 / 3) < .01
            subprocess.run(['import', '-window', window, str(output / 'level-selector-landscape.png')], check=True)
            # Back from the level list returns to the level, then to the covers.
            driver.press(key=20022)
            driver.wait(label=f'Level 1 / {classic_levels}')
            assert not driver.find(label='Continue', role='button', visible=True)
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            driver.press(label='Play', role='button')
            driver.wait(label=f'Level 1 / {classic_levels}')
            move_until_saved(classic)
            swipe_beside_board_until_saved(classic)
            # Rotation changes presentation without replacing the saved game.
            for width, height, columns, rows in ((960, 600, 20, 12), (480, 820, 12, 20)):
                saved = campaign_progress(classic.read_bytes())
                window = resize_owned_window(child, width, height)
                board, player = board_and_player()
                assert abs(board['width'] / board['height'] - columns / rows) < .01
                assert board['x'] >= 0 and board['y'] >= 0
                assert board['x'] + board['width'] <= width and board['y'] + board['height'] <= height
                assert campaign_progress(classic.read_bytes()) == saved, 'rotation changed or reset the saved game'
                orientation = 'landscape' if width > height else 'portrait'
                subprocess.run(['import', '-window', window, str(output / (orientation + '.png'))], check=True)
                swipe_in_visible_direction()
            classic_saved = campaign_progress(classic.read_bytes())
            assert len(driver.find(label='Back', role='button', visible=True)) == 1, 'Shovey needs one clear Back action'
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            driver.press(label='Next', role='button')
            driver.press(label='Open', role='button')
            driver.wait(label='Explore', role='button')
            driver.press(label='Classic', role='button')
            driver.wait(label='Story levels', role='text')
            driver.press(label='1', role='button')
            driver.wait(label='Play', role='button')
            # Editing follows the device, including portrait screens whose
            # board area becomes wider after reserving the toolbar/palette.
            for width, height in ((390, 844), (844, 390), (580, 600), (480, 820)):
                resize_owned_window(child, width, height)
                board = driver.find(key=200000, visible=True)[0]
                aspect = 5 / 3 if width > height else 3 / 5
                assert abs(board['width'] / board['height'] - aspect) < .01, ('editor paint orientation', width, height, board)
            driver.press(label='Play', role='button')
            driver.wait(label='Testing', role='text')
            for width, height in ((390, 844), (844, 390), (480, 820)):
                window = resize_owned_window(child, width, height)
                board, player = board_and_player(200000)
                aspect = 5 / 3 if width > height else 3 / 5
                assert abs(board['width'] / board['height'] - aspect) < .01, ('editor play orientation', width, height, board)
                swipe_in_visible_direction(board_key=200000)
            # Island stays unavailable in the editor until it is offered for sale.
            driver.key('escape')
            driver.key('escape')
            driver.key('escape')
            driver.wait(label='Classic', role='button')
            assert not driver.find(label='Island', role='button'), 'The editor offers Island'
        with application(profile, 'restore'):
            driver.press(label='Next', role='button')
            driver.press(label='Open', role='button')
            driver.wait(label='Explore', role='button')
            # Escape returns to the editor's cover, which stays selected.
            driver.key('escape')
            driver.wait(label='Open', role='button')
            driver.press(label='Previous', role='button')
            driver.press(label='Play', role='button')
            driver.wait(label=f'Level 1 / {classic_levels}')
            assert campaign_progress(classic.read_bytes()) == classic_saved
    print('Standalone Shovey: portrait/landscape boards, swipe directions, rotation saves, covers and independent saves passed')


if __name__ == '__main__':
    main()
