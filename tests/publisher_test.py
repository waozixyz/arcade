"""Exercise the Apps package's signed publisher with Arcade-owned inputs, offline."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
apps = Path(subprocess.check_output([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'apps'],
                                   cwd=ROOT, text=True).strip())
spec = importlib.util.spec_from_file_location('publisher', apps / 'scripts/node_release.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

with tempfile.TemporaryDirectory(prefix='arcade-publisher-') as directory:
    work = Path(directory)
    key = Ed25519PrivateKey.generate()
    private = work / 'key.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    private.chmod(0o600)
    public = key.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw).hex()
    pins = work / 'publishers.json'
    pins.write_text(json.dumps([{'key_id': 'test-key', 'public_key': public,
                                'app_ids': [], 'app_prefixes': ['inbe.']}]))
    ledger = work / 'versions.json'
    owned = json.loads((ROOT / 'apps/versions.json').read_text())
    ledger.write_text(json.dumps(owned))
    store = work / 'store'

    def stage():
        return publisher.stage_node_app(store, 'chess', private, 'test-key', pins,
                                        ledger_path=ledger, bundle_directory=ROOT / 'build/games')

    value = stage()
    assert stage() == value
    assert value['app_id'] == 'inbe.chess'
    assert value['artifacts'][0]['sha256'] == sha256((ROOT / 'build/games/chess.zx').read_bytes()).hexdigest()
    key.public_key().verify(bytes.fromhex(value['signature']), publisher.signing_message(value))
    # The upload carries the release files; the node writes its own history.
    entries = {str(path.relative_to(store)): path.read_bytes() for path in store.rglob('*')
               if path.is_file() and path.name not in ('.publish.lock', 'history-v2.json')}
    remote = work / 'receiver'
    publisher.import_node_app(entries, remote, json.loads(pins.read_text()), 'inbe.chess')
    assert json.loads((remote / 'inbe.chess/latest-v2.json').read_bytes()) == value
    component = owned['node_apps']['chess']
    component['version'] = '1.0.1'
    component['sequence'] = 2
    ledger.write_text(json.dumps(owned))
    try:
        stage()
    except ValueError:
        pass
    else:
        raise AssertionError('Publisher accepted an older game release')
    assert json.loads((store / 'inbe.chess/latest-v2.json').read_bytes()) == value
    component['id'] = 'arcade.chess'
    ledger.write_text(json.dumps(owned))
    try:
        stage()
    except ValueError:
        pass
    else:
        raise AssertionError('Publisher accepted a renamed signed game identity')

    # Arcade's catalog and exact separately downloaded games use the same
    # signed release and existing node importer.
    node_bundles = work / 'node-apps'
    shutil.copytree(ROOT / 'build/node-apps', node_bundles)
    ledger.write_text(json.dumps(json.loads((ROOT / 'apps/versions.json').read_text())))
    arcade = publisher.stage_node_app(store, 'arcade', private, 'test-key', pins,
                                     ledger_path=ledger, bundle_directory=node_bundles)
    lookups = publisher.game_lookups(store / 'inbe.arcade', arcade)
    expected = {path.stem for path in (node_bundles / 'arcade.games').glob('*.zx')}
    assert {value['artifacts'][0]['sha256'] for value in lookups} == expected
    for lookup in lookups:
        key.public_key().verify(bytes.fromhex(lookup['signature']), publisher.signing_message(lookup))
    entries = {str(path.relative_to(store)): path.read_bytes()
               for path in (store / 'inbe.arcade').rglob('*')
               if path.is_file() and path.name not in ('.publish.lock', 'history-v2.json')}
    publisher.import_node_app(entries, remote, json.loads(pins.read_text()), 'inbe.arcade')
    for digest in expected:
        assert (remote / 'inbe.arcade' / (digest + '.zx')).read_bytes() == \
            (node_bundles / 'arcade.games' / (digest + '.zx')).read_bytes()
    changed = next((node_bundles / 'arcade.games').glob('*.zx'))
    changed.write_bytes(b'ZX\0\0changed bytes')
    try:
        publisher.stage_node_app(store, 'arcade', private, 'test-key', pins,
                                 ledger_path=ledger, bundle_directory=node_bundles)
    except ValueError:
        pass
    else:
        raise AssertionError('Publisher accepted game bytes that differ from their digest')
    assert json.loads((store / 'inbe.arcade/latest-v2.json').read_bytes()) == arcade

print('Arcade ledger: signatures, separate game downloads, node receiver, immutable bytes, rollback and stable identity passed')
