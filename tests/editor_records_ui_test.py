"""Standalone Shovey's editor keeps custom levels as the account's entity
records: levels in the editor's old records are copied over once and stay
in place, new levels are saved as records, and a restart lists each one
once. Runs privately with a throwaway profile and no account."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys


def board():
    cells = []
    for y in range(20):
        for x in range(12):
            cells.append(12 if x in (0, 11) or y in (0, 19) else 0)
    cells[4 * 12 + 6], cells[15 * 12 + 6] = 10, 7
    return ''.join(f'{value:02x}' for value in cells)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    root = Path(__file__).resolve().parents[1]
    output = root / 'build/editor-records-ui-test'
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver
    driver = UiDriver(output / 'driver')
    profile = output / 'profile'
    subprocess.run(['rm', '-rf', str(profile)], check=True)
    old = profile / 'games/arcade.shovey-editor/records'
    old.mkdir(parents=True, mode=0o700)
    index = 'I1\nnext 2\nlevel 1 0 - 0 - Kept garden\n'
    level = f'E1\nboard {board()}\nroute \n'
    (old / 'classic-levels').write_text(index)
    (old / 'classic-1').write_text(level)
    records = profile / 'entity/records/local/levels'

    def documents():
        return {path.stem: json.loads(path.read_text()) for path in records.glob('*.json')}

    @contextlib.contextmanager
    def editor(name):
        log_path = output / (name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                     env=os.environ | driver.environment() |
                                     {'ARCADE_DATA': str(profile), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Play', role='button')
                driver.press(label='Next', role='button')
                driver.press(label='Open', role='button')
                driver.wait(label='Explore', role='button')
                driver.press(label='Classic', role='button')
                driver.wait(label='Story levels', role='text')
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    with editor('first'):
        driver.wait(label='Kept garden', role='button')
        saved = documents()
        assert len(saved) == 1, saved
        document = next(iter(saved.values()))
        assert document['format'] == 'shovey-levels-1' and document['edition'] == 'classic', document
        assert document['title'] == 'Kept garden' and document['proof'] == '-', document
        assert ''.join(document['levels'][0]['cells']) == board(), 'The copied board changed'
        assert isinstance(document['updated_at'], int) and document['updated_at'] > 1700000000
        assert (old / 'entity-moved').read_text() == 'M1\nclassic 1\n'
        assert (old / 'classic-levels').read_text() == index and (old / 'classic-1').read_text() == level, \
            'The old records must stay for older editors'
        driver.press(label='New level', role='button')
        driver.wait(label='Play', role='button')
        driver.key('escape')
        driver.wait(label='Kept garden', role='button')
        assert len(documents()) == 2, documents()
    for path in [profile / 'entity', *(profile / 'entity').rglob('*')]:
        assert path.stat().st_mode & 0o077 == 0, f'Non-private record path: {path}'
    with editor('again'):
        driver.wait(label='Kept garden', role='button')
        assert len(driver.find(label='Kept garden', role='button')) == 1, 'The old level was copied twice'
        assert len(documents()) == 2, documents()
    print("Standalone Shovey's editor: old custom levels copied once into private entity records, kept in place, "
          'new levels saved as records and listed once after a restart passed')


if __name__ == '__main__':
    main()
