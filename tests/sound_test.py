"""Play compressed and plain WAV game sounds through Arcade's SDL2 channel.

SDL's dummy driver accepts audio without a device, so this never sounds on
the desktop. The fixture tones are generated here, not taken from a game.
"""
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
    ziran = str(ROOT / 'scripts/ziran.sh')
    lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    toolchain = subprocess.check_output([ziran, 'pkg', 'path', 'ziran', *lock], cwd=ROOT, text=True).strip()
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
    generated = WORK / 'c'
    if generated.exists():
        shutil.rmtree(generated)
    subprocess.run([ziran, 'build', '--project', *lock, '--target=c', '--no-main',
                    '--entry', 'sound_behavior:Check', '-o', str(generated), 'tests/sound_behavior.zi'],
                   cwd=ROOT, check=True)
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
