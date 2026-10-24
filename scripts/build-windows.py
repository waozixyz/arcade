#!/usr/bin/env python3
"""Cross-build standalone Shovey for 64-bit Windows with MinGW: the Ziran
runtime, raylib, curl and liboqs from their locked sources, then the host in
src/windows.zi."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')
BUILD = ROOT / 'build/windows'
DEFINES = ['--define', '_WIN32', '--define', 'PLATFORM_DESKTOP', '--define', 'SHOVEY_STANDALONE',
           '--define', '__x86_64__']
# Kryon's parallel image decoding runs on Ziran's threads, so the static
# link takes MinGW's winpthreads too.
LIBRARIES = ['-lgdi32', '-lwinmm', '-lopengl32', '-luser32', '-lshell32', '-lole32', '-lcomdlg32', '-lcomctl32',
             '-luuid', '-lws2_32', '-liphlpapi', '-lcrypt32', '-lsecur32', '-lbcrypt', '-ladvapi32', '-lz', '-lm',
             '-lpthread']


def package(name):
    lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *lock], cwd=ROOT, text=True).strip())


def source_key(path):
    """A locked package's path names its commit; a local checkout's path does
    not, so its commit is added and a new commit rebuilds what it made."""
    head = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    return str(path) + ('@' + head.stdout.strip() if head.returncode == 0 else '')


def built(output, source):
    """A dependency is rebuilt only when its locked source changes."""
    stamp = output.parent / (output.name + '.source')
    return output.exists() and stamp.exists() and stamp.read_text() == str(source)


def record(output, source):
    (output.parent / (output.name + '.source')).write_text(str(source))


def cmake(source, folder, tools, *options):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    toolchain = folder / 'mingw.cmake'
    toolchain.write_text(f'''set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER {tools}gcc)
set(CMAKE_RC_COMPILER {tools}windres)
set(CMAKE_AR {tools}ar)
set(CMAKE_RANLIB {tools}ranlib)
set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
''')
    subprocess.run(['cmake', '-S', str(source), '-B', str(folder), '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain),
                    '-DBUILD_SHARED_LIBS=OFF', *options], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/shovey.exe')
    parser.add_argument('--tools', default='x86_64-w64-mingw32-', help='The MinGW tool prefix')
    args = parser.parse_args()
    tools = args.tools
    toolchain = package('ziran')
    # The host's Zi graph, generated fresh for Windows from the project.
    ir, generated = BUILD / 'ir', BUILD / 'c'
    for folder in (ir, generated):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    subprocess.run([ZIRAN, 'ir', '--project', *lock, *DEFINES, '-o', str(ir), 'src/windows.zi'], cwd=ROOT, check=True)
    subprocess.run([ZIRAN, 'build', '--target=c', *DEFINES, '--entry', 'windows:main', '--root', str(ir),
                    '-o', str(generated), str(ir / 'windows.zir')], cwd=ROOT, check=True)

    runtime = BUILD / 'runtime/libziran.a'
    if not built(runtime, source_key(toolchain)):
        subprocess.run(['make', '-B', '-j4', '-C', str(toolchain), 'BOOTSTRAP=1', 'BUILD_DIR=' + str(runtime.parent),
                        'CC=' + tools + 'gcc', 'AR=' + tools + 'ar', 'OBJCOPY=' + tools + 'objcopy', 'CFLAGS=-O2',
                        str(runtime)], check=True)
        record(runtime, source_key(toolchain))

    # Windows raylib as Inner Breeze ships it: RGFW and OpenGL 1.1.
    raylib_source = package('raylib') / 'src'
    raylib = BUILD / 'raylib/libraylib.a'
    if not built(raylib, raylib_source):
        copy = BUILD / 'raylib/source'
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(raylib_source, copy, ignore=shutil.ignore_patterns('*.o', '*.a'))
        subprocess.run(['make', '-j4', '-C', str(copy), 'OS=Windows_NT', 'RAYLIB_SRC_PATH=.', 'RAYLIB_RELEASE_PATH=..',
                        'PLATFORM=PLATFORM_DESKTOP_RGFW', 'GRAPHICS=GRAPHICS_API_OPENGL_11', 'RAYLIB_LIBTYPE=STATIC',
                        'RAYLIB_MODULE_AUDIO=TRUE', 'RAYLIB_MODULE_MODELS=TRUE', 'CC=' + tools + 'gcc',
                        'AR=' + tools + 'ar', 'RANLIB=' + tools + 'ranlib',
                        'CUSTOM_CFLAGS=-DSUPPORT_FILEFORMAT_JPG=1 -DSUPPORT_FILEFORMAT_TTF=1 -O2 -ffunction-sections -fdata-sections'],
                       check=True)
        record(raylib, raylib_source)

    # Entity's account network and signatures: curl over Windows TLS, liboqs.
    curl_source = package('curl')
    curl = BUILD / 'curl/install/lib/libcurl.a'
    if not built(curl, curl_source):
        cmake(curl_source, BUILD / 'curl', tools, '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(BUILD / 'curl/install'),
              '-DBUILD_STATIC_LIBS=ON', '-DBUILD_CURL_EXE=OFF', '-DCURL_STATICLIB=ON', '-DCURL_USE_SCHANNEL=ON',
              '-DCURL_USE_OPENSSL=OFF', '-DCURL_USE_LIBPSL=OFF', '-DCURL_USE_LIBSSH2=OFF', '-DCURL_USE_GSSAPI=OFF',
              '-DUSE_NGHTTP2=OFF', '-DUSE_LIBIDN2=OFF', '-DCURL_ZSTD=OFF', '-DCURL_BROTLI=OFF', '-DCURL_DISABLE_LDAP=ON',
              '-DCURL_DISABLE_LDAPS=ON', '-DCURL_DISABLE_SMB=ON', '-DENABLE_CURL_MANUAL=OFF', '-DBUILD_EXAMPLES=OFF',
              '-DBUILD_LIBCURL_DOCS=OFF', '-DBUILD_MISC_DOCS=OFF', '-DBUILD_TESTING=OFF')
        subprocess.run(['cmake', '--build', str(BUILD / 'curl'), '--target', 'install', '-j4'], check=True)
        record(curl, curl_source)
    oqs_source = package('liboqs')
    oqs = BUILD / 'oqs/lib/liboqs.a'
    if not built(oqs, oqs_source):
        cmake(oqs_source, BUILD / 'oqs', tools, '-DCMAKE_BUILD_TYPE=MinSizeRel', '-DOQS_BUILD_ONLY_LIB=ON',
              '-DOQS_USE_OPENSSL=OFF', '-DOQS_DIST_BUILD=OFF', '-DOQS_OPT_TARGET=generic', '-DOQS_MINIMAL_BUILD=SIG_ml_dsa_44')
        subprocess.run(['cmake', '--build', str(BUILD / 'oqs'), '--target', 'oqs', '-j4'], check=True)
        record(oqs, oqs_source)

    # The program's icon in Explorer and the taskbar.
    from PIL import Image
    icon = BUILD / 'shovey.ico'
    Image.open(package('shovey') / 'assets/branding/shovey-icon.png').convert('RGBA').save(
        icon, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    (BUILD / 'shovey.rc').write_text('1 ICON "shovey.ico"\n')
    resource = BUILD / 'shovey-resource.o'
    subprocess.run([tools + 'windres', '-O', 'coff', '-o', str(resource), 'shovey.rc'], cwd=BUILD, check=True)

    output = args.output.resolve()
    temporary = output.with_suffix('.new.exe')
    output.parent.mkdir(parents=True, exist_ok=True)
    includes = ['-I' + str(toolchain / 'include'), '-I' + str(package('monocypher') / 'src')]
    for folder in sorted({generated, *(path for path in generated.rglob('*') if path.is_dir())}):
        includes += ['-iquote', str(folder)]
    subprocess.run([tools + 'gcc', '-std=c11', '-O2', '-ffunction-sections', '-fdata-sections', *includes,
                    *map(str, sorted(generated.rglob('*.c'))), str(package('monocypher') / 'src/monocypher.c'),
                    str(package('monocypher') / 'src/optional/monocypher-ed25519.c'),
                    str(runtime), str(oqs), str(curl), str(raylib), str(resource),
                    '-Wl,--gc-sections', '-static', '-static-libgcc', '-mwindows', *LIBRARIES, '-o', str(temporary)],
                   check=True)
    subprocess.run([tools + 'strip', str(temporary)], check=True)
    temporary.replace(output)
    font = package('kryon') / 'assets/fonts/LiberationSans-Regular.ttf'
    shutil.copyfile(font, output.parent / 'kryon-font.ttf')
    print('Shovey Windows build passed: ' + str(output))


if __name__ == '__main__':
    main()
