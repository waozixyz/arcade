"""The same native import interaction in Arcade and an Inbe consumer."""
import subprocess
import time


def check_import(driver, saved_game, capture=None):
    original = saved_game()

    def wait(predicate, message):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.05)
        raise driver._failure(message)

    def paste(text):
        # This clipboard belongs to the harness's private Xvfb display.
        subprocess.run(['xclip', '-selection', 'clipboard', '-target', 'UTF8_STRING', '-i'],
                       input=text, text=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, check=True)
        driver.press(label='Paste', role='button')
        wait(lambda: driver.find(key=8973)[0]['value'] == text, 'Paste did not fill the import field')

    def square(name):
        return 8010 + (8 - int(name[1])) * 8 + ord(name[0]) - ord('a')

    def format_button(name):
        driver.press(label=name, role='button')
        wait(lambda: driver.find(label=name, role='button')[0]['selected'], 'Format was not selected')

    def notation():
        driver.press(label='Notation', role='button')
        driver.wait(key=8963)

    driver.press(label='Study', role='button')
    notation()
    driver.press(label='Import', role='button')
    format_button('PGN')
    pgn = '[Event "Imported game"] [White "Alice"] [Black "Bob"]\n1.e4 c5 {main line} (1...e5) 2.Nf3 d6 *'
    paste(pgn)
    if capture:
        capture('import-pgn')
    driver.press(label='Open study', role='button')
    driver.wait(label='2. Nf3', role='button')
    driver.wait(label='2... d6', role='button')
    assert saved_game() == original, 'PGN import changed the live game'
    notation()
    format_button('PGN')
    exported = driver.find(key=8963)[0]['value']
    assert '[White "Alice"]' in exported and '[Black "Bob"]' in exported
    assert '1. e4 c5 2. Nf3 d6 *' in exported and 'main line' not in exported, exported
    format_button('FEN')
    assert driver.find(key=8963)[0]['value'] == 'rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3'

    driver.press(label='Import', role='button')
    format_button('FEN')
    custom = '7k/8/8/8/8/8/p7/7K b - - 0 17'
    paste(custom)
    driver.press(label='Open study', role='button')
    driver.wait(label='Chessboard', role='button')
    driver.press(key=square('a2'))
    driver.press(key=square('a1'))
    driver.press(label='Queen', role='button')
    move = driver.wait(label='17... a1=Q+', role='button')
    board = driver.find(key=8000)[0]
    assert move['x'] > board['x'] + board['width'] / 2, 'Black history must stay in the Black column'
    if capture:
        capture('import-fen-promotion')
    driver.press(label='First', role='button')
    driver.press(label='Latest', role='button')
    notation()
    format_button('PGN')
    exported = driver.find(key=8963)[0]['value']
    assert '[SetUp "1"]' in exported and '[FEN "' + custom + '"]' in exported, exported
    assert '[White "?"]' in exported and '[Black "?"]' in exported, exported
    assert '17... a1=Q+ *' in exported, exported

    # A malformed position and a partially legal PGN leave the previous
    # study intact. Cancel must restore that study's engine position too.
    driver.press(label='Import', role='button')
    format_button('FEN')
    paste('8/8/8/8/8/8/8/8 w - - 0 1')
    driver.press(label='Open study', role='button')
    driver.wait(label='Invalid PGN/FEN. Check the format and starting position.')
    driver.press(label='Cancel', role='button')
    driver.wait(label='17... a1=Q+', role='button')
    notation()
    driver.press(label='Import', role='button')
    format_button('PGN')
    paste('1.e4 e5 2.Bh6 *')
    driver.press(label='Open study', role='button')
    driver.wait(label='An illegal or ambiguous move was found. Check the main line.')
    driver.press(label='Cancel', role='button')
    driver.wait(label='17... a1=Q+', role='button')
    assert saved_game() == original, 'Failed import changed the live game'
    driver.press(label='Computer', role='button')
    driver.press(label='Study', role='button')
    driver.wait(label='17... a1=Q+', role='button')
    notation()
    format_button('FEN')
    assert driver.find(key=8963)[0]['value'] == '7k/8/8/8/8/8/8/q6K w - - 0 18'
    driver.press(label='Back to board', role='button')
    driver.press(label='Computer', role='button')
    assert saved_game() == original, 'Returning from imported study changed the live game'
