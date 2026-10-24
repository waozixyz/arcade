"""Verify Chess's study tools and native clipboard inside the Inbe consumer."""
import contextlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
INBE = Path(subprocess.check_output([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'inbe'],
                                  cwd=ROOT, text=True).strip())
sys.path.insert(0, str(INBE / 'tests'))
from ui_driver import UiDriver
from chess_import_flow import check_import

assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
BINARY = Path(sys.argv[1]).resolve(strict=True)
OUTPUT = ROOT / 'build/inbe-ui-test'
OUTPUT.mkdir(parents=True, exist_ok=True)
driver = UiDriver(OUTPUT / 'driver')


def wait(predicate, message):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(.05)
    raise driver._failure(message)


@contextlib.contextmanager
def application(profile, name):
    log_path = OUTPUT / (name + '.log')
    env = os.environ | driver.environment() | {
        'APP_DATA_ROOT': str(profile), 'INBE_NODE_APP_FILE': str(ROOT / 'build/games/chess.zx')}
    with log_path.open('w') as log:
        child = subprocess.Popen([str(BINARY)], cwd=INBE, env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            driver.tree()
            def own_window():
                found = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)],
                                       text=True, capture_output=True)
                return found.stdout.splitlines()[0] if found.returncode == 0 else None
            window = wait(own_window, 'Inbe did not map its own window')
            subprocess.run(['xdotool', 'windowsize', window, '390', '844'], check=True)
            driver.wait_idle(frames=3)
            yield child, window
        finally:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def square(name):
    return 8010 + (8 - int(name[1])) * 8 + ord(name[0]) - ord('a')


with tempfile.TemporaryDirectory(prefix='profile-', dir=OUTPUT) as directory:
    profile = Path(directory)
    with application(profile, 'bootstrap'):
        wait(lambda: (profile / 'inbe.db').exists(), 'Inbe profile was not created')
    with sqlite3.connect(profile / 'inbe.db') as db:
        user = db.execute("SELECT id FROM users WHERE kind='local' LIMIT 1").fetchone()[0]
        settings = dict(language='en', language_system=0, language_setup_done=1, apps_setup_done=1,
                        tutorial_seen=1, habits_guide_seen=1, launcher_guide_seen=1, lumi_guides_seen=127,
                        package_updates_allowed=0, apps_last_update_check=1900000000,
                        node_apps_checked_at=int(time.time()))
        for key, value in settings.items():
            db.execute('INSERT INTO settings(user_id,key,value,updated_at) VALUES(?,?,?,1) '
                       'ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value', (user, key, str(value)))

    def saved_game():
        with sqlite3.connect(profile / 'inbe.db') as db:
            row = db.execute("SELECT value FROM settings WHERE user_id=? AND key='cell.chess.computer'",
                             (user,)).fetchone()
            return row[0] if row else ''

    def clipboard(expected):
        result = subprocess.run(['xclip', '-selection', 'clipboard', '-target', 'UTF8_STRING', '-o'],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip() == expected

    with application(profile, 'study') as (child, window):
        driver.press(label='Apps', role='button')
        driver.press(label='Chess', role='button')
        driver.wait(label='Expert', role='button')
        driver.press(label='Easy', role='button')
        driver.press(label='Start', role='button')
        driver.press(key=square('e2'))
        driver.press(key=square('e4'))
        wait(lambda: len(saved_game().split('moves=', 1)[-1].split()) == 2, 'Computer did not reply')
        driver.wait(label='Your move')
        saved = saved_game()
        driver.press(label='Hint', role='button')
        driver.wait(contains='Suggested move:', timeout=60)
        assert saved_game() == saved
        driver.press(label='Review', role='button')
        driver.press(label='First', role='button')
        driver.press(label='Next', role='button')
        driver.press(key=square('e7'))
        driver.press(key=square('e5'))
        driver.press(label='Analysis', role='button')
        driver.wait(contains='Depth', timeout=90)
        assert driver.find(key=8922, visible=True), 'Evaluation bar is missing'
        assert int(subprocess.check_output(['xdotool', 'getwindowpid', window])) == child.pid
        subprocess.run(['import', '-window', window, str(OUTPUT / 'study.png')], check=True)
        driver.press(label='Notation', role='button')
        pgn = driver.find(key=8963)[0]['value']
        assert '1. e4 e5' in pgn, pgn
        driver.press(label='Copy', role='button')
        wait(lambda: clipboard(pgn), 'Inbe did not copy the PGN')
        driver.press(label='FEN', role='button')
        wait(lambda: driver.find(label='FEN', role='button')[0]['selected'], 'FEN did not become selected')
        fen = driver.find(key=8963)[0]['value']
        assert fen == 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2', fen
        driver.press(label='Copy', role='button')
        wait(lambda: clipboard(fen), 'Inbe did not copy the FEN')
        driver.press(label='Back to board', role='button')
        driver.press(label='Computer', role='button')
        driver.wait(label='Your move')
        assert saved_game() == saved, 'Study changed the account game'
        driver.press(label='Flip board', role='button')
        driver.press(label='Flip board', role='button')
        driver.press(label='Take back', role='button')
        wait(lambda: saved_game().endswith('moves='), 'Takeback did not restore the previous turn')
        check_import(driver, saved_game)

print('Inbe: narrow Chess hints, study variations, analysis, PGN/FEN clipboard, flip, takeback, PGN/FEN import and recovery passed')
