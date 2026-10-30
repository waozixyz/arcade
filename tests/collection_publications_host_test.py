"""Check that Arcade routes writable publications through Entity's account gate."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build/collection-publications-host-test"
ENVIRONMENT = {
    key: value for key, value in os.environ.items()
    if key not in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"}
}


def run(program, *arguments):
    return subprocess.run([program, *arguments], cwd=ROOT, check=True,
                          env=ENVIRONMENT, text=True)


def main():
    generated = WORK / "c"
    binary = WORK / "test"
    for path in (binary, binary.with_suffix(".new")):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    if generated.exists():
        shutil.rmtree(generated)
    generated.mkdir(parents=True)
    ziran = str(ROOT / "scripts/ziran.sh")
    lock = [] if (ROOT / "ziran.local.toml").exists() else ["--locked"]
    run(ziran, "build", "--project", *lock, "--target=c", "--no-main",
        "--define", "PLATFORM_DESKTOP", "--entry",
        "collection_publications_host_behavior:Check", "-o", str(generated),
        "tests/collection_publications_host_behavior.zi")
    main_c = generated / "main.c"
    main_c.write_text('#include "collection_publications_host_behavior.h"\n'
                      'int main(void) { return Check(); }\n')
    toolchain = Path(subprocess.check_output(
        [ziran, "pkg", "path", "ziran", *lock], cwd=ROOT, text=True,
        env=ENVIRONMENT).strip())
    runtime = ROOT / "build/ziran/libziran.a"
    if not runtime.exists():
        run("make", "-j1", str(runtime))

    def package(name):
        return Path(subprocess.check_output(
            [ziran, "pkg", "path", name, *lock], cwd=ROOT, text=True,
            env=ENVIRONMENT).strip())

    oqs_source = package("liboqs")
    oqs = WORK / ("oqs-" + oqs_source.name)
    oqs.parent.mkdir(parents=True, exist_ok=True)
    with open(oqs.with_name(oqs.name + ".lock"), "w") as exclusive:
        fcntl.flock(exclusive, fcntl.LOCK_EX)
        run("cmake", "-S", str(oqs_source), "-B", str(oqs),
            "-DCMAKE_BUILD_TYPE=MinSizeRel", "-DBUILD_SHARED_LIBS=OFF",
            "-DOQS_BUILD_ONLY_LIB=ON", "-DOQS_USE_OPENSSL=OFF",
            "-DOQS_DIST_BUILD=OFF", "-DOQS_OPT_TARGET=generic",
            "-DOQS_MINIMAL_BUILD=SIG_ml_dsa_44")
        run("cmake", "--build", str(oqs), "--target", "oqs", "--", "-j1")
    libraries = subprocess.check_output(
        ["pkg-config", "--libs", "sdl2", "cairo", "freetype2", "fontconfig",
         "pangocairo", "gtk+-3.0"], text=True, env=ENVIRONMENT).split()
    monocypher = package("monocypher")
    includes = [item for path in generated.rglob("*") if path.is_dir()
                for item in ("-iquote", str(path))]
    temporary = binary.with_suffix(".new")
    run(os.environ.get("CC", "cc"), "-std=c11", "-O2", "-ffunction-sections",
        "-fdata-sections", "-I" + str(toolchain / "include"), "-iquote",
        str(generated), *includes, *map(str, generated.rglob("*.c")),
        str(ROOT / "build/ziran/libziran.a"), "-I" + str(monocypher / "src"),
        str(monocypher / "src/monocypher.c"),
        str(monocypher / "src/optional/monocypher-ed25519.c"),
        str(oqs / "lib/liboqs.a"), "-Wl,--gc-sections", *libraries,
        "-lX11", "-l:libcurl.so.4", "-lz", "-lm", "-lpthread", "-o", str(temporary))
    temporary.replace(binary)
    result = subprocess.run([binary], cwd=ROOT, env=ENVIRONMENT |
                            {"SDL_AUDIODRIVER": "dummy"})
    if result.returncode != 42:
        raise SystemExit(
            f"collection publications host check returned {result.returncode}")
    print("Arcade publications host: writable service dispatches through Entity's account gate")


if __name__ == "__main__":
    main()
