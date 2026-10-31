"""Every native registered on ArcadeActivity must exist with its JNI signature.

Android rejects the entire library in JNI_OnLoad when even one method is
missing. Check the resolved host, so a package update cannot silently ship
an activity that crashes before onCreate.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def verify():
    kryon = Path(subprocess.check_output(
        [str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'kryon'],
        cwd=ROOT, text=True).strip())
    host = (kryon / 'src/backend/android_device.zi').read_text()
    glue = (ROOT / 'src/android_glue.zi').read_text()
    java = (ROOT / 'droid/app/src/main/java/xyz/waozi/arcade/ArcadeActivity.java').read_text()
    types = {'void': 'V', 'int': 'I', 'long': 'J', 'boolean': 'Z',
             'float': 'F', 'byte[]': '[B', 'String': 'Ljava/lang/String;'}
    declared = {}
    for result, name, arguments in re.findall(
            r'native\s+(\w+)\s+(\w+)\(([^)]*)\)', java):
        parameters = [argument.strip().split()[0] for argument in arguments.split(',') if argument.strip()]
        declared[name] = '(' + ''.join(types[t] for t in parameters) + ')' + types[result]
    registered = 0
    for source in (host, glue):
        names = dict((index, name) for name, index in re.findall(
            r'CopyCString\("(native\w+)", names\[(\d+)\]', source))
        signatures = dict((index, signature) for signature, index in re.findall(
            r'CopyCString\("([^"]+)", signatures\[(\d+)\]', source))
        for index, name in names.items():
            expected = signatures[index]
            assert declared.get(name) == expected, (
                f'{name}{expected} registered by native host, Java declares {declared.get(name)}')
            registered += 1
    assert registered >= 12, 'No Android JNI registration contract found'
    print(f'Android JNI contract: {registered} registered methods match ArcadeActivity')


if __name__ == '__main__':
    verify()
