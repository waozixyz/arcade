"""Exercise the existing signed publisher with Arcade-owned inputs, offline."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
inbe = Path(subprocess.check_output([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'inbe'],
                                   cwd=ROOT, text=True).strip())
spec = importlib.util.spec_from_file_location('publisher', inbe / 'scripts/package-release.py')
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
    assert value['artifacts'][0]['sha256'] == sha256((ROOT / 'build/games/chess.zib').read_bytes()).hexdigest()
    key.public_key().verify(bytes.fromhex(value['signature']), publisher.signing_message(value))
    entries = {str(path.relative_to(store)): path.read_bytes()
               for path in store.rglob('*') if path.is_file() and path.name != '.publish.lock'}
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

print('Arcade ledger: existing signature, node receiver, idempotence, rollback and stable identity passed')
