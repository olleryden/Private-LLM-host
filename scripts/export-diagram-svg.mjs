// Export an Archify diagram through its viewer Export menu (headless Edge/Chrome via CDP).
// Usage: node scripts/export-diagram-svg.mjs <diagram.html> <out> [svg|svg-light|svg-dark|png]
// Browser: $ARCHIFY_CHROME, default /usr/bin/microsoft-edge (the browser Archify checks used).
import { spawn } from 'node:child_process';
import { copyFileSync, mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [, , htmlArg, outArg, format = 'svg'] = process.argv;
if (!htmlArg || !outArg) { console.error('usage: export-diagram-svg.mjs <diagram.html> <out> [format]'); process.exit(2); }
const browserPath = process.env.ARCHIFY_CHROME || '/usr/bin/microsoft-edge';
const profile = mkdtempSync(join(tmpdir(), 'archify-export-profile-'));
const downloads = mkdtempSync(join(tmpdir(), 'archify-export-dl-'));

const browser = spawn(browserPath, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

const wsUrl = await new Promise((res, rej) => {
  const timer = setTimeout(() => rej(new Error('browser did not start')), 30000);
  let buf = '';
  browser.stderr.on('data', (d) => {
    buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(timer); res(m[1]); }
  });
  browser.on('exit', (c) => rej(new Error(`browser exited ${c}`)));
});

const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let nextId = 0; const pending = new Map(); const listeners = [];
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { res, rej } = pending.get(msg.id); pending.delete(msg.id);
    msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
  } else listeners.forEach((fn) => fn(msg));
});
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++nextId; pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads, eventsEnabled: true });
  const { targetId } = await send('Target.createTarget', { url: pathToFileURL(resolve(htmlArg)).href });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId)).result.value;

  for (let i = 0; i < 100 && !(await evaluate(`document.readyState === 'complete' && !!document.querySelector('[data-format="${format}"]')`)); i++) await sleep(100);
  await sleep(800);
  const clicked = await evaluate(`(() => { const b = document.querySelector('[data-format="${format}"]'); if (!b) return false; b.click(); return true; })()`);
  if (!clicked) throw new Error(`no export control for format ${format}`);

  let file;
  for (let i = 0; i < 150 && !file; i++) {
    await sleep(200);
    file = readdirSync(downloads).find((f) => !f.endsWith('.crdownload') && statSync(join(downloads, f)).size > 0);
  }
  if (!file) throw new Error('export did not produce a download');
  copyFileSync(join(downloads, file), resolve(outArg));
  console.log(`exported ${format}: ${resolve(outArg)} (from ${file})`);
} finally {
  ws.close(); browser.kill('SIGTERM');
  await sleep(300);
  rmSync(profile, { recursive: true, force: true }); rmSync(downloads, { recursive: true, force: true });
}
