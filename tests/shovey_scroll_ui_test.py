"""Check the real level selector's wheel, content drag and scrollbar privately."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, action='append', required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver

    def wait(predicate, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.05)
        raise AssertionError(message)

    with tempfile.TemporaryDirectory(prefix='shovey-scroll-') as temporary:
        output = Path(temporary)
        for binary in args.binary:
            driver = UiDriver(output / binary.name / 'driver')
            log_path = output / (binary.name + '.log')
            with log_path.open('w') as log:
                child = subprocess.Popen([str(binary.resolve())], cwd=binary.resolve().parent,
                                         env=os.environ | driver.environment() |
                                         {'ARCADE_DATA': str(output / binary.name / 'profile'),
                                          'LANG': 'en_US.UTF-8'}, stdout=log, stderr=subprocess.STDOUT)
                driver.attach(child, log_path)
                try:
                    driver.press(label='Play', role='button')
                    driver.press(label='Levels', role='button')
                    driver.wait(label='Continue', role='button')
                    numbers = [int(n['label']) for n in driver.find(role='button') if n['label'].isdigit()]
                    last = str(max(numbers))

                    def first_y():
                        return driver.find(label='1', role='button')[0]['y']

                    for width, height in ((480, 820), (960, 600)):
                        windows = subprocess.check_output(
                            ['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
                        assert len(windows) == 1
                        window = windows[0]
                        assert int(subprocess.check_output(['xdotool', 'getwindowpid', window], text=True)) == child.pid
                        subprocess.run(['xdotool', 'windowsize', '--sync', window, str(width), str(height)], check=True)
                        wait(lambda: (driver.tree()[0]['width'], driver.tree()[0]['height']) == (width, height),
                             'The app did not adopt the test size')
                        driver.wait_idle(frames=5)
                        scroll = driver.wait(role='scroll')
                        x, y = UiDriver.center(scroll)
                        driver.pointer(x, y, wheel=200)
                        driver.wait_idle(frames=90)
                        before = first_y()
                        header = driver.find(label='Continue', role='button', visible=True)[0]
                        driver.pointer(x, y, wheel=-200)
                        wait(lambda: first_y() < before - 20, f'{binary.name}: wheel did not scroll levels')
                        driver.wait_idle(frames=90)
                        end = driver.find(label=last, role='button', visible=True)
                        assert end and end[0]['visible_height'] >= end[0]['height'] - 1, 'Last level is unreachable'
                        assert driver.find(label='Continue', role='button', visible=True)[0]['y'] == header['y']

                        for label in ('2', '1'):
                            # Both locked and playable cards must yield a swipe
                            # to their scroll, without opening a puzzle.
                            driver.pointer(x, y, wheel=200)
                            driver.wait_idle(frames=90)
                            before = first_y()
                            card = driver.find(label=label, role='button', visible=True)[0]
                            start = UiDriver.center(card)
                            driver.drag(start, (start[0], start[1] - 140))
                            wait(lambda: first_y() < before - 20, 'Dragging a level card did not scroll')
                            assert driver.find(label='Continue', role='button', visible=True), 'Scrolling opened a level'

                        driver.pointer(x, y, wheel=200)
                        driver.wait_idle(frames=90)
                        track_x = scroll['x'] + scroll['width'] - 5
                        driver.drag((track_x, scroll['y'] + 12),
                                    (track_x, scroll['y'] + scroll['height'] - 12))
                        driver.wait_idle(frames=5)
                        assert driver.find(label=last, role='button', visible=True), 'Scrollbar cannot reach the last row'
                        driver.release_pointer()
                        print(f'PASS: {binary.name} {width}x{height}: wheel, card drag, scrollbar, final row, fixed header')
                finally:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=10)


if __name__ == '__main__':
    main()
