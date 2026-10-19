"""Play compressed and plain WAV game sounds through Arcade's SDL2 channel.

SDL's dummy driver accepts audio without a device, so this never sounds on
the desktop. The fixture tones are generated here, not taken from a game.
"""
from importlib.machinery import SourceFileLoader
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/sound-test'


def main():
    toolchain = os.environ.get('TOOLCHAIN_SOURCE')
    apps = os.environ.get('APPS_SOURCE')
    if not toolchain or not apps:
        raise SystemExit('Set TOOLCHAIN_SOURCE and APPS_SOURCE as for the Arcade build')
    WORK.mkdir(parents=True, exist_ok=True)
    pcm = WORK / 'tone.wav'
    with wave.open(str(pcm), 'wb') as tone:
        tone.setnchannels(1)
        tone.setsampwidth(2)
        tone.setframerate(22050)
        tone.writeframes(b''.join(struct.pack('<h', int(9000 * math.sin(index * 0.1))) for index in range(4410)))
    adpcm = WORK / 'tone-adpcm.wav'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(pcm), '-ar', '44100', '-ac', '1',
                    '-c:a', 'adpcm_ima_wav', str(adpcm)], check=True)
    module_map = WORK / 'module-map.tsv'
    helper = SourceFileLoader('apps_map', str(ROOT / 'scripts/local-apps-map.py')).load_module()
    helper.build(ROOT, Path(apps).resolve(), module_map)
    with module_map.open('a') as stream:
        stream.write('M\troot\tsound_behavior\t' + str(ROOT / 'tests/sound_behavior.zi') + '\n')
    generated = WORK / 'c'
    if generated.exists():
        shutil.rmtree(generated)
    subprocess.run([str(Path(toolchain) / 'build/bin/zi2c'), '--no-main', '--root', str(ROOT),
                    '--entry', 'sound_behavior:Check', '-o', str(generated), 'tests/sound_behavior.zi'],
                   cwd=ROOT, env=os.environ | {'ZIRAN_PACKAGE_MAP': str(module_map)}, check=True)
    (generated / 'main.c').write_text('#include "sound_behavior.h"\nint main(void) { return Check(); }\n')
    libraries = subprocess.check_output(['pkg-config', '--libs', 'sdl2'], text=True).split()
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-I' + str(Path(toolchain) / 'include'),
                    *[item for path in [generated, *generated.rglob('*')] if path.is_dir() for item in ('-iquote', str(path))],
                    *map(str, generated.rglob('*.c')), str(ROOT / 'build/ziran/libziran.a'),
                    *libraries, '-lm', '-lpthread', '-o', str(WORK / 'test')], check=True)
    environment = {key: value for key, value in os.environ.items()
                   if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
    result = subprocess.run([str(WORK / 'test')], env=environment | {'SDL_AUDIODRIVER': 'dummy',
                            'SOUND_TEST_ADPCM': str(adpcm), 'SOUND_TEST_PCM': str(pcm)})
    if result.returncode:
        raise SystemExit(f'Arcade sound check {result.returncode} failed')
    print('Arcade sound: ADPCM and PCM WAV decode, replace the playing sound, and reject damaged data')


if __name__ == '__main__':
    main()
