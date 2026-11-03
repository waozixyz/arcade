"""Run the actual WASM console in a disposable Chromium with no Node dependency."""
import argparse
import base64
import contextlib
import http.server
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import threading
import time
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


class Cdp:
    def __init__(self, profile, log):
        incoming, self.write = os.pipe()
        self.read, outgoing = os.pipe()
        # Chromium's documented debugging pipe is fd3 (input), fd4 (output).
        def child_pipes():
            os.dup2(incoming, 3)
            os.dup2(outgoing, 4)
        env = {k: v for k, v in os.environ.items() if k not in
               ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER', 'GDK_DISPLAY')}
        env['YUE_DESKTOP_RECOVERY'] = '0'
        scratch = ROOT / 'work/webtmp'
        scratch.mkdir(parents=True,exist_ok=True)
        env['TMPDIR'] = str(scratch)
        self.child = subprocess.Popen(['chromium', '--headless=new', '--no-sandbox',
            '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
            '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--remote-debugging-pipe',
            '--user-data-dir=' + str(profile), 'about:blank'], env=env,
            pass_fds=tuple(set((incoming, outgoing, 3, 4))), preexec_fn=child_pipes,
            stdout=log, stderr=log)
        os.close(incoming)
        os.close(outgoing)
        self.buffer = b''
        self.sequence = 0
        self.session = None
        self.errors = []
        target = self.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        self.session = self.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
        self.call('Runtime.enable')
        self.call('Page.enable')

    def call(self, method, params=None):
        self.sequence += 1
        request = dict(id=self.sequence, method=method, params=params or {})
        if self.session:
            request['sessionId'] = self.session
        os.write(self.write, json.dumps(request).encode() + b'\0')
        deadline = time.monotonic() + 45
        while True:
            while b'\0' not in self.buffer:
                if not select.select([self.read], [], [], max(0, deadline-time.monotonic()))[0]:
                    raise TimeoutError(method)
                data = os.read(self.read, 65536)
                if not data:
                    raise RuntimeError('Chromium debugging pipe closed')
                self.buffer += data
                assert len(self.buffer) <= 16 * 1024 * 1024
            line, self.buffer = self.buffer.split(b'\0', 1)
            if not line:
                continue
            reply = json.loads(line)
            if reply.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(reply['params']['exceptionDetails'].get('text', '')[:300])
            if reply.get('id') == self.sequence:
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', dict(expression=expression, returnByValue=True, awaitPromise=True))
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def close(self):
        if self.child.poll() is None:
            self.child.terminate()
        self.child.wait(timeout=15)
        os.close(self.read)
        os.close(self.write)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', type=Path)
    args = parser.parse_args()
    site = args.site.resolve()
    work = ROOT / 'work/web-console-ui'
    work.mkdir(parents=True, exist_ok=True)
    requests = []
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=site, **kw)
        def log_message(self, *a):
            pass
        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            requests.append(path)
            if path in ('/', '/index.html'):
                html = (site / 'index.html').read_text().replace(
                    'document.body.appendChild(script);',
                    "Module.preRun = (Module.preRun || []).concat(function () { FS.mkdirTree('/arcade-test'); ENV.KRYON_TEST_DRIVER='/arcade-test'; }); document.body.appendChild(script);")
                # No personal account/provider is part of this disposable UI test.
                html = html.replace('https://account.waozi.xyz/share.js', '/test-account.js')
                data = html.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path == '/test-account.js':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'window.WaoziAccount={attach:function(){return Promise.resolve();}};')
            else:
                super().do_GET()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(dir=work) as profile, (work / 'chromium.log').open('w') as log:
            cdp = Cdp(Path(profile), log)
            try:
                cdp.call('Emulation.setDeviceMetricsOverride', dict(width=1200, height=720, deviceScaleFactor=1, mobile=False))
                cdp.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/'})
                deadline = time.monotonic() + 90
                while not cdp.evaluate("typeof FS !== 'undefined' && FS.analyzePath('/arcade-test').exists"):
                    assert time.monotonic() < deadline, 'WASM did not start'
                    time.sleep(.1)
                serial = 0
                def driver(verb, **fields):
                    nonlocal serial
                    serial += 1
                    command = '\t'.join([str(serial), verb, *[f'{k}={v}' for k,v in fields.items()]]) + '\n'
                    cdp.evaluate("if(FS.analyzePath('/arcade-test/reply').exists)FS.unlink('/arcade-test/reply');FS.writeFile('/arcade-test/command'," + json.dumps(command) + ");")
                    stop = time.monotonic() + 15
                    while True:
                        reply = cdp.evaluate("FS.analyzePath('/arcade-test/reply').exists ? FS.readFile('/arcade-test/reply',{encoding:'utf8'}) : ''")
                        if reply:
                            value = json.loads(reply)
                            if value.get('serial') == serial:
                                assert value.get('ok', True), value
                                return value
                        assert time.monotonic() < stop, 'WASM test driver did not reply'
                        time.sleep(.03)
                def nodes():
                    return driver('tree')['nodes']
                def wait_label(label):
                    stop = time.monotonic() + 30
                    while True:
                        found = [n for n in nodes() if n['label'] == label and n['visible']]
                        if found:
                            return found[0]
                        assert time.monotonic() < stop, (label, cdp.errors)
                        time.sleep(.05)
                offline = wait_label('Stay offline')
                position = dict(x=offline['visible_x']+offline['visible_width']/2, y=offline['visible_y']+offline['visible_height']/2)
                cdp.call('Input.dispatchMouseEvent', dict(type='mouseMoved', **position))
                cdp.call('Input.dispatchMouseEvent', dict(type='mousePressed',button='left',buttons=1,clickCount=1, **position))
                time.sleep(.08)
                cdp.call('Input.dispatchMouseEvent', dict(type='mouseReleased',button='left',buttons=0,clickCount=1, **position))
                wait_label('Shovey')
                for width,height,name in [(1200,720,'landscape'),(480,820,'portrait')]:
                    cdp.call('Emulation.setDeviceMetricsOverride', dict(width=width,height=height,deviceScaleFactor=1,mobile=False))
                    time.sleep(.5)
                    tree = nodes()
                    assert not any(n['label'] == 'Arcade' and n['kind'] == 'text' for n in tree)
                    assert not any('Editor' in n['label'] for n in tree)
                    selected = [n for n in tree if n['kind']=='button' and n['selected'] and n['height']>100]
                    assert len(selected)==1
                    assert abs(selected[0]['width']/selected[0]['height']-(16/9 if width>height else 2/3))<.02
                    backdrop = next(n for n in tree if n['key']==50021)
                    assert (backdrop['x'],backdrop['y'],backdrop['width'],backdrop['height'])==(0,0,width,height)
                    assert all(any(n['kind']=='image' and n['detail'].endswith('/assets/hud/'+icon+'.webp') for n in tree) for icon in ('profile','dew'))
                    assert all(any(n['kind']=='image' and n['label']==title for n in tree) for title in ('Shovey','Apfelwurm'))
                    (work/(name+'-tree.json')).write_text(json.dumps(tree,indent=2))
                    shot=cdp.call('Page.captureScreenshot',{'format':'png'})
                    (work/(name+'.png')).write_bytes(base64.b64decode(shot['data']))
                # Exercise the production browser Gamepad adapter in real WASM.
                cdp.call('Emulation.setFocusEmulationEnabled', {'enabled': True})
                cdp.evaluate("""window.arcadePad = {connected:true,index:0,id:'Arcade local test',mapping:'standard',
                    axes:[0,0],buttons:Array.from({length:17},()=>({pressed:false,touched:false,value:0}))};
                    Object.defineProperty(navigator,'getGamepads',{configurable:true,value:()=>[window.arcadePad]});
                    document.querySelector('canvas').focus(); window.dispatchEvent(new Event('focus'));""")
                time.sleep(.2)
                def pad(button, down):
                    cdp.evaluate('window.arcadePad.buttons[' + str(button) + ']=' +
                        json.dumps(dict(pressed=down,touched=down,value=1 if down else 0)) + ';')
                def selected_label():
                    return next(n['label'] for n in nodes() if n['kind']=='button' and n['selected'] and n['height']>100)
                def wait_selected(label):
                    stop=time.monotonic()+5
                    while selected_label()!=label:
                        assert time.monotonic()<stop, ('Gamepad did not select',label)
                        time.sleep(.05)
                pad(15, True)
                wait_selected('Apfelwurm')
                time.sleep(.2)
                assert selected_label()=='Apfelwurm', 'A held button must not skip games'
                pad(15, False)
                time.sleep(.1)
                pad(14, True)
                wait_selected('Shovey')
                pad(14, False)
                time.sleep(.1)
                pad(0, True)
                wait_label('Cancel')
                assert not any(n['kind']=='modal' for n in nodes()), 'Launch progress must be a normal full-art page'
                assert any(n['kind']=='text' and n['label']=='Shovey' for n in nodes())
                pad(0, False)
                time.sleep(.1)
                pad(8, True)
                stop=time.monotonic()+5
                while any(n['kind']=='text' and n['label']=='Shovey' for n in nodes()):
                    assert time.monotonic()<stop, 'Gamepad View must return from the launch page'
                    time.sleep(.05)
                pad(8, False)
                assert '/assets/hud/profile.webp' in requests and '/assets/hud/dew.webp' in requests
                print('PASS browser WASM console: landscape/portrait geometry, full background, games only, no title/captions, canonical HUD assets, real browser Gamepad selection/activate/Back')
            finally:
                cdp.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
