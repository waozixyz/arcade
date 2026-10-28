// Open Arcade's browser edition in a private headless browser and require
// install, play, reopen and recover from a failed saved-record read.
// Usage: node tests/web_site_test.mjs SITE_DIR
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { access, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const site = process.argv[2];
const game = process.env.ARCADE_TEST_GAME || 'Apfelwurm';
if (!site) throw new Error('Usage: node tests/web_site_test.mjs SITE_DIR');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.wasm': 'application/wasm', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://x');
  const path = normalize(decodeURIComponent(url.pathname)).replace(/^\/+/, '') || 'index.html';
  try {
    // Model the previous runtime still cached under its unversioned URL.
    // A new deployment must request its coherent runtime revision instead.
    if (path === 'runtime.js' && !url.searchParams.has('v')) {
      response.writeHead(200, { 'Content-Type': 'text/javascript', 'Cache-Control': 'public, max-age=14400' });
      response.end('console.error("Stale cached Arcade runtime"); Module.onAbort();');
      return;
    }
    let body = await readFile(join(site, path));
    if (path === 'index.html') {
      // Enable only the existing widget-tree reader in this disposable page.
      // Input still travels through the browser's real pointer and key events.
      body = Buffer.from(body.toString().replace('document.body.appendChild(script);', `
        Module.preRun = (Module.preRun || []).concat(function () {
          FS.mkdir('/arcade-test');
          ENV.KRYON_TEST_DRIVER = '/arcade-test';
        });
        document.body.appendChild(script);`));
    }
    response.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream' });
    response.end(body);
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = await mkdtemp(join(process.env.TMPDIR || tmpdir(), 'arcade-web-'));
const env = { ...process.env };
for (const key of ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS']) delete env[key];
env.YUE_DESKTOP_RECOVERY = '0';
const browser = spawn(process.env.CHROMIUM || 'chromium', ['--headless=new', '--no-sandbox', '--use-gl=swiftshader',
  '--enable-unsafe-swiftshader', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { env, detached: true, stdio: 'ignore' });
let socket, sequence = 0;
const pending = new Map(), console_lines = [];
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  const timeout = setTimeout(() => { pending.delete(id); reject(new Error(method + ' timed out')); }, 15000);
  pending.set(id, { resolve, reject, timeout }); socket.send(JSON.stringify({ id, method, params }));
});
let failure = '';
let expectedDiagnostics = 0;
try {
  const started = Date.now();
  while (true) {
    try { await access(join(profile, 'DevToolsActivePort')); break; } catch {}
    if (Date.now() - started > 15000) throw new Error('the browser did not start');
    await delay(50);
  }
  const port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0];
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.consoleAPICalled')
      console_lines.push(message.params.args.map(arg => arg.value ?? arg.description ?? '').join(' '));
    if (message.method === 'Runtime.exceptionThrown')
      console_lines.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    clearTimeout(request.timeout);
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result);
  };
  await command('Runtime.enable'); await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await command('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  let ready = false;
  const deadline = Date.now() + 60000;
  while (!ready && Date.now() < deadline) {
    // The page may still be loading; it answers once its status element exists.
    const state = await command('Runtime.evaluate', {
      expression: 'JSON.stringify({ready: !!(window.Module && Module.profileReady), error: !!document.getElementById("loading")?.classList.contains("error")})',
      returnByValue: true });
    if (typeof state.result?.value !== 'string') { await delay(250); continue; }
    const value = JSON.parse(state.result.value);
    if (value.error) { failure = 'the page reported that Arcade could not start'; break; }
    ready = value.ready;
    if (!ready) await delay(250);
  }
  if (!ready && !failure) failure = 'the library never became ready';
  if (ready) {
    const resources = await command('Runtime.evaluate', {
      expression: 'performance.getEntriesByType("resource").map(entry=>entry.name)', returnByValue: true });
    const runtime = resources.result.value.map(name=>new URL(name)).filter(url=>
      /\/(runtime\.(js|wasm|data)(\.gz)?|arcade\.json|apps\.zx(\.gz)?)$/.test(url.pathname));
    const revisions = new Set(runtime.map(url=>url.searchParams.get('v')));
    if (!runtime.some(url=>url.pathname.endsWith('/runtime.js')) ||
        !runtime.some(url=>url.pathname.endsWith('/runtime.wasm')) ||
        revisions.size !== 1 || !/^[a-f0-9]{64}$/.test([...revisions][0]))
      failure = 'the runtime and collection files did not use one coherent cache revision';
  }
  // Let the library draw several frames before judging them.
  await delay(3000);
  if (ready && !failure) {
    const evaluate = async expression => {
      const value = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (value.exceptionDetails) throw new Error(value.exceptionDetails.exception?.description || value.exceptionDetails.text);
      return value.result?.value;
    };
    let serial = 0;
    const tree = async () => {
      await evaluate(`FS.writeFile('/arcade-test/command', ${JSON.stringify(++serial + '\ttree\n')})`);
      const end = Date.now() + 10000;
      while (Date.now() < end) {
        const failed = console_lines.slice(expectedDiagnostics).find(line => /frame failed|portable execution failed|RuntimeError/.test(line));
        if (failed) throw new Error(failed);
        const reply = await evaluate(`FS.analyzePath('/arcade-test/reply').exists ? FS.readFile('/arcade-test/reply', {encoding:'utf8'}) : ''`);
        if (reply) {
          await evaluate(`FS.unlink('/arcade-test/reply')`);
          return JSON.parse(reply).nodes;
        }
        await delay(100);
      }
      throw new Error('Arcade stopped drawing frames');
    };
    const click = async node => {
      const position = { x: node.visible_x + node.visible_width / 2, y: node.visible_y + node.visible_height / 2 };
      await command('Input.dispatchMouseEvent', { type: 'mouseMoved', ...position });
      await command('Input.dispatchMouseEvent', { type: 'mousePressed', ...position, button: 'left', buttons: 1, clickCount: 1 });
      await delay(80);
      await command('Input.dispatchMouseEvent', { type: 'mouseReleased', ...position, button: 'left', buttons: 0, clickCount: 1 });
      await delay(250);
    };
    const button = (nodes, label) => nodes.find(node => node.kind === 'button' && node.label === label && node.visible);
    const waitButton = async label => {
      let nodes;
      for (const end = Date.now() + 60000; Date.now() < end;) {
        nodes = await tree();
        const found = button(nodes, label);
        if (found) return found;
        await delay(150);
      }
      throw new Error('Game did not show ' + label + ': ' + nodes.filter(node => node.kind === 'button').map(node => node.label).join(', '));
    };
    const pageReady = async () => {
      for (const end = Date.now() + 60000; Date.now() < end;) {
        if (await evaluate('!!(window.Module && Module.profileReady)')) return;
        await delay(150);
      }
      throw new Error('The library did not reopen');
    };
    const cover = button(await tree(), game);
    if (!cover) throw new Error('Game cover missing');
    await click(cover);
    const download = (await tree()).findLast(node => node.kind === 'button' && node.label === 'Download');
    if (!download) throw new Error('The cover did not offer its download');
    await click(download);
    await waitButton(game === 'Apfelwurm' ? 'Play' : 'Back');
    const play = button(await tree(), 'Play');
    if (play) await click(play);
    const swipe = button(await tree(), 'Swipe');
    if (swipe) await click(swipe);
    if (game === 'Apfelwurm') await waitButton('Pause');
    // Flush the actual control record before a cold restart.
    await evaluate(`new Promise((resolve,reject) => FS.syncfs(false,error => error ? reject(error) : resolve(true)))`);
    await command('Page.reload');
    await pageReady();
    const reloaded = await tree();
    const installed = button(reloaded, game);
    if (!installed) throw new Error('Installed cover missing after reload');
    await click(installed);
    await waitButton(game === 'Apfelwurm' ? 'Play' : 'Back');
    console.log(game + ' downloaded, opened its game and reopened from its installed cover');
    if (game === 'Apfelwurm') {
      await command('Page.reload');
      await pageReady();
      const installed = button(await tree(), game);
      const saved = await evaluate(`(() => {
        const root='/kryon-apps/arcade/games';
        for (const name of FS.readdir(root)) {
          const path=root+'/'+name+'/records/controls.dat';
          if (FS.analyzePath(path).exists) return {path,text:FS.readFile(path,{encoding:'utf8'})};
        }
        return null;
      })()`);
      if (!saved) throw new Error('Playing did not retain the control choice');
      await evaluate(`(() => {
        const original=FS.open;
        FS.open=function(path,...args) {
          if (String(path).includes('/games/') && String(path).includes('/records/') && !String(path).endsWith('/.lock')) {
            FS.open=original;
            throw new FS.ErrnoError(29);
          }
          return original.call(this,path,...args);
        };
      })()`);
      await click(installed);
      // Depending on the game version it first reads records on its title
      // or on Play. Either path must expose a usable recovery control.
      if (!await evaluate('!!Module.arcadeFailed')) {
        try {
          const play=button(await tree(),'Play');
          if (play) await click(play);
        } catch (error) {
          // The first game frame can fail between sampling the flag and
          // asking for its tree. Require the runtime's failure signal.
          let failed=false;
          for (const end=Date.now()+1000; Date.now()<end;) {
            failed=await evaluate('!!Module.arcadeFailed');
            if (failed) break;
            await delay(50);
          }
          if (!failed) throw error;
        }
      }
      let recovered=false;
      for (const end=Date.now()+15000; Date.now()<end;) {
        recovered=await evaluate(`!!Module.arcadeFailed && document.getElementById('loading').classList.contains('error') && getComputedStyle(document.getElementById('loading')).opacity==='1'`);
        if (recovered) break;
        await delay(100);
      }
      if (!recovered) throw new Error('A failed game left the library frozen without recovery');
      if (!console_lines.some(line=>/portable execution failed in ReadLevel/.test(line)))
        throw new Error('The fixture did not reproduce the reported saved-record failure');
      expectedDiagnostics=console_lines.length;
      const retry=await evaluate(`(() => {const r=document.getElementById('retry').getBoundingClientRect();return {visible_x:r.x,visible_y:r.y,visible_width:r.width,visible_height:r.height};})()`);
      await click(retry);
      await pageReady();
      if (await evaluate(`FS.readFile(${JSON.stringify(saved.path)},{encoding:'utf8'})`) !== saved.text)
        throw new Error('Recovering from a failed game changed its saved record');
      await click(button(await tree(),game));
      await waitButton('Play');
      console.log('The reported ReadLevel failure showed recovery; returning reopened the installed game and retained its saved record');
    }
  }
  const failed = console_lines.slice(expectedDiagnostics).find(line => /frame failed|portable execution failed/.test(line));
  if (!failure && failed) failure = failed;
} catch (error) {
  console.error(console_lines.slice(-20).join('\n'));
  throw error;
} finally {
  socket?.close();
  try { process.kill(-browser.pid, 'SIGTERM'); } catch {}
  server.close();
  await rm(profile, { recursive: true, force: true }).catch(() => {});
}
if (failure) {
  console.error(console_lines.slice(-20).join('\n'));
  throw new Error(failure);
}
console.log('Arcade opened its library in the browser');
