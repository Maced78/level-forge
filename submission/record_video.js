// Records submission/Level-Forge_demo.webm: a real-time screen capture of the running app and the demo site.
// Needs: the app on :8765 (bash run_demo.sh) and `python3 -m http.server 8811` inside docs/.
// FONTS=<node_modules dir with @fontsource packages> serves the site's fonts locally when Google Fonts is unreachable.
const { chromium } = require(process.env.PW || 'playwright');
const path = require('path'), fs = require('fs');
const APP = 'http://localhost:8765/', SITE = 'http://localhost:8811/index.html';
const FONTS = process.env.FONTS || '';
const FACES = [['Pixelify Sans', 'pixelify-sans', [500, 700]], ['IBM Plex Sans', 'ibm-plex-sans', [400, 500, 600, 700]], ['IBM Plex Mono', 'ibm-plex-mono', [400, 600]]];
const FONT_CSS = FACES.map(([fam, pkg, ws]) => ws.map(w => `@font-face{font-family:"${fam}";font-weight:${w};src:url(http://fonts.local/${pkg}/${pkg}-latin-${w}-normal.woff2) format("woff2")}`).join('')).join('');

(async () => {
  const dir = path.join(__dirname, 'video_tmp'); fs.rmSync(dir, { recursive: true, force: true });
  const b = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, colorScheme: 'light', recordVideo: { dir, size: { width: 1280, height: 720 } } });
  if (FONTS) {
    await ctx.route('**/fonts.googleapis.com/**', r => r.fulfill({ contentType: 'text/css', body: FONT_CSS }));
    await ctx.route('http://fonts.local/**', r => { const [pkg, file] = new URL(r.request().url()).pathname.slice(1).split('/');
      r.fulfill({ contentType: 'font/woff2', headers: { 'access-control-allow-origin': '*' }, body: fs.readFileSync(path.join(FONTS, '@fontsource', pkg, 'files', file)) }); });
  }
  const p = await ctx.newPage(); const t0 = Date.now();
  const wait = ms => p.waitForTimeout(ms);
  const cap = async (text) => p.evaluate(([t, css]) => {
    if (!document.getElementById('__capcss')) { const s = document.createElement('style'); s.id = '__capcss';
      s.textContent = css + '#__cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:99999;background:#12244a;color:#fff;border-radius:8px;padding:12px 22px;font:500 21px/1.35 "IBM Plex Sans",system-ui,sans-serif;max-width:1040px;text-align:center;box-shadow:0 10px 30px rgba(10,17,36,.45);transition:opacity .25s}#__cap::after{content:"";position:absolute;left:0;top:0;width:2px;height:2px;opacity:.02;background:#fff;animation:__k 1s linear infinite}@keyframes __k{to{transform:translateX(3px)}}';
      document.head.appendChild(s); }
    let d = document.getElementById('__cap'); if (!d) { d = document.createElement('div'); d.id = '__cap'; document.body.appendChild(d); }
    d.style.opacity = t ? 1 : 0; if (t) d.textContent = t; }, [text, FONT_CSS]);
  const type = async (sel, text) => { await p.fill(sel, ''); await p.type(sel, text, { delay: 12 }); };
  // eased scroll that finishes before the next step starts (keeps captions in step with the picture)
  const go = (sel, off = 64) => p.evaluate(([s, off]) => new Promise(done => { const y0 = window.scrollY, el = s ? document.querySelector(s) : null;
    const y1 = Math.max(0, el ? el.getBoundingClientRect().top + y0 - off : 0), t0 = performance.now(), D = 650;
    document.documentElement.style.scrollBehavior = 'auto';
    const step = t => { const k = Math.min(1, (t - t0) / D), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; window.scrollTo(0, y0 + (y1 - y0) * e); k < 1 ? requestAnimationFrame(step) : done(); };
    requestAnimationFrame(step); }), [sel, off]);
  const card = async (big, small, lines) => p.setContent(`<style>${FONT_CSS}
    body{margin:0;height:100vh;display:grid;place-items:center;background:#eef2f8;background-image:linear-gradient(rgba(47,91,234,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(47,91,234,.07) 1px,transparent 1px);background-size:28px 28px;color:#12244a;font-family:"IBM Plex Sans",system-ui,sans-serif;text-align:center}
    h1{font:700 104px/1 "Pixelify Sans",monospace;margin:0 0 22px}h1 b{color:#d6337f}p{font-size:30px;margin:0 0 30px;color:#56678a}div.l{font:400 21px/1.7 "IBM Plex Mono",monospace;color:#2f5bea}</style>
    <div><h1>${big}</h1><p>${small}</p><div class="l">${lines || ''}</div></div>`);

  // 1. title
  await card('<b>Level</b>-Forge', 'Type a sentence. Get a puzzle level that can be won.', ''); await wait(3200);

  // 2. the live app: one hard request
  await p.goto(APP); await wait(700);
  await cap('A level designer asks for a hard level, in plain words.');
  await type('#req', 'Create a difficult level that tests rule manipulation, strategic object pushing and a changing win condition.');
  await p.fill('#seed', '1001'); await wait(900); await p.click('#go');
  await cap('The program builds many levels and plays every one of them.'); await wait(7500);
  await cap('It keeps the hardest level that passes every check.');
  await p.waitForSelector('#board', { timeout: 120000 }); await wait(600);
  await cap('Here is the level. Now the computer wins it, move by move, in the real game.');
  await p.getByRole('button', { name: /Play solution/ }).first().click(); await wait(11600);
  await cap('The report shows it can be won, how hard it is, and that it needs each skill that was asked for.'); await go('.ladder', 20); await wait(4600);

  // 3. an impossible request
  await go(null);
  await cap('Some requests cannot be built at all.');
  await type('#req', 'Create a hard level where the only rocks are behind the water and the water can only be crossed by sinking a rock in it.');
  await p.click('#go'); await p.waitForSelector('.contra', { timeout: 60000 });
  await cap('Refused: you need a rock to cross the water, and the rocks are on the other side.'); await wait(5200);

  // 4. second game
  await go(null);
  await p.selectOption('#game', 'sokoban_sg'); await type('#req', 'A medium level with two boxes.'); await p.fill('#seed', '2');
  await cap('The same program also works on a second game, Sokoban.'); await wait(600);
  await p.click('#go'); await p.waitForFunction(() => /Sokoban level/.test(document.querySelector('#result')?.textContent || '') && document.querySelector('#board'), null, { timeout: 120000 }); await wait(300); await go('#board', 60);
  await cap('Every box must end on a target. The computer solves this one too.');
  await p.getByRole('button', { name: /Play solution/ }).first().click(); await wait(6500);

  // 5. the public demo site
  await p.goto(SITE); await wait(500); await cap('On the demo site, anyone can play a generated level with the arrow keys.'); await go('#demo');
  await p.click('#b-live'); await wait(700);
  const first = await p.evaluate(() => window.FORGE_DATA.gallery[0].solution.slice(0, 11));   // the opening moves of the real solution
  for (const m of first) { await p.keyboard.press({ U: 'ArrowUp', D: 'ArrowDown', L: 'ArrowLeft', R: 'ArrowRight' }[m]); await wait(300); }
  await wait(900);
  await cap('You can also write your own level. The solver checks it right in the browser.'); await go('#verify'); await p.click('#v-play'); await wait(3600);
  await p.click('#v-break'); await cap('And it tells you when a level cannot be won.'); await wait(3000);
  await cap('Baba Is You is only our example. These are generated levels, drawn in each game\'s own graphics.'); await go('#games'); await wait(4600);
  await cap('How it works: learn the game\'s rules once, then use that rule book for every request.'); await go('#how'); await wait(5000);
  await cap('Tested on 200 requests. Every level could be won, and none was wrongly marked as winnable.'); await go('#evidence'); await wait(4600);

  // 6. end card
  await card('<b>Level</b>-Forge', 'Team Azərçay · NeuroBridge.SI Baku · AI Gaming', 'maced78.github.io/level-forge<br>github.com/Maced78/level-forge'); await wait(3400);
  console.log('video seconds:', ((Date.now() - t0) / 1000).toFixed(1));
  await ctx.close(); await b.close();
  const f = fs.readdirSync(dir).find(x => x.endsWith('.webm'));
  fs.renameSync(path.join(dir, f), path.join(__dirname, 'Level-Forge_demo.webm')); fs.rmSync(dir, { recursive: true, force: true });
})();
