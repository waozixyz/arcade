// Open Arcade's browser edition in a private headless browser and require
// its library to draw without a failed frame. Usage: node tests/web_site_test.mjs SITE_DIR
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { access, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const site = process.argv[2];
if (!site) throw new Error('Usage: node tests/web_site_test.mjs SITE_DIR');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.wasm': 'application/wasm', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (request, response) => {
  const path = normalize(decodeURIComponent(new URL(request.url, 'http://x').pathname)).replace(/^\/+/, '') || 'index.html';
  try {
    const body = await readFile(join(site, path));
    response.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream' });
    response.end(body);
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = await mkdtemp(join(process.env.TMPDIR || tmpdir(), 'arcade-web-'));
const env = { ...process.env };
for (const key of ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS']) delete env[key];
const browser = spawn(process.env.CHROMIUM || 'chromium', ['--headless=new', '--no-sandbox', '--use-gl=swiftshader',
  '--enable-unsafe-swiftshader', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { env, detached: true, stdio: 'ignore' });
let socket, sequence = 0;
const pending = new Map(), console_lines = [];
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params }));
});
let failure = '';
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
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result);
  };
  await command('Runtime.enable'); await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await command('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  let ready = false;
  const deadline = Date.now() + 60000;
  while (!ready && Date.now() < deadline) {
    const state = await command('Runtime.evaluate', {
      expression: 'JSON.stringify({ready: !!(window.Module && Module.profileReady), error: document.getElementById("loading").classList.contains("error")})',
      returnByValue: true });
    const value = JSON.parse(state.result.value);
    if (value.error) { failure = 'the page reported that Arcade could not start'; break; }
    ready = value.ready;
    if (!ready) await delay(250);
  }
  if (!ready && !failure) failure = 'the library never became ready';
  // Let the library draw several frames before judging them.
  await delay(3000);
  const failed = console_lines.find(line => /frame failed|portable execution failed/.test(line));
  if (!failure && failed) failure = failed;
} finally {
  try { process.kill(-browser.pid, 'SIGTERM'); } catch {}
  server.close();
  await rm(profile, { recursive: true, force: true }).catch(() => {});
}
if (failure) {
  console.error(console_lines.slice(-20).join('\n'));
  throw new Error(failure);
}
console.log('Arcade opened its library in the browser');
