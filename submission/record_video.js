// Records submission/Level-Forge_demo.webm: a scripted, real-time screen capture of the running prototype.
// Needs: ./run_demo.sh on :8765 and `python3 -m http.server 8811` inside docs/.
const { chromium } = require(process.env.PW || 'playwright');
const path = require('path'), fs = require('fs');
const APP = 'http://localhost:8765/', SITE = 'http://localhost:8811/index.html';
(async () => {
  const dir = path.join(__dirname, 'video_tmp'); fs.rmSync(dir, { recursive: true, force: true });
  const b = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir, size: { width: 1280, height: 720 } } });
  const p = await ctx.newPage(); const t0 = Date.now();
  const cap = async (text) => p.evaluate(t => { let d = document.getElementById('__cap'); if (!d) { d = document.createElement('div'); d.id = '__cap';
      d.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:99999;background:rgba(10,11,16,.94);color:#fff;border:1px solid #f2c14e;border-radius:10px;padding:10px 18px;font:600 19px Inter,system-ui,sans-serif;max-width:1100px;text-align:center;box-shadow:0 6px 30px rgba(0,0,0,.6)';
      document.body.appendChild(d); } d.textContent = t; }, text);
  const wait = ms => p.waitForTimeout(ms);
  const type = async (sel, text) => { await p.fill(sel, ''); await p.type(sel, text, { delay: 14 }); };

  // 1. what it is
  await p.goto(SITE); await cap('Level-Forge: type a sentence, get a puzzle level the game engine has already beaten.'); await wait(5500);

  // 2. live generation in the local app
  await p.goto(APP); await wait(600);
  await cap('The prototype, running live. A designer asks for a hard level in plain language…');
  await type('#req', 'Create a difficult level that tests rule manipulation, strategic object pushing and a changing win condition.');
  await p.fill('#seed', '1001'); await wait(900); await p.click('#go');
  await cap('…it builds dozens of candidates, solves each one, and replays the best in the original game engine.');
  await p.waitForSelector('#board', { timeout: 120000 }); await wait(700);
  await cap('Result: a native level file, fully validated. The shortest solution replays in the real engine.');
  await p.click('#bp'); await wait(9000);
  await p.evaluate(() => document.querySelector('.ladder').scrollIntoView({ block: 'start' })); await wait(300);
  await cap('Every requested skill is proven necessary, and difficulty is computed from the whole state space, not from length.'); await wait(6500);

  // 3. it refuses impossible requests
  await p.evaluate(() => window.scrollTo(0, 0));
  await type('#req', 'Create a hard level where the only rocks are behind the water and the water can only be crossed by sinking a rock in it.');
  await p.click('#go'); await p.waitForSelector('.contra', { timeout: 60000 });
  await cap('Impossible requests are refused: here a dependency cycle, with the literal layout proven unsolvable.'); await wait(6500);

  // 4. second game, same loop
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.selectOption('#game', 'sokoban_sg'); await wait(500);
  await cap('Same loop, second game: an open-source Sokoban. No change to the generation pipeline.');
  await p.fill('#seed', '3'); await p.click('#go'); await p.waitForSelector('#board', { timeout: 120000 }); await wait(500);
  await p.click('#bp'); await wait(8000);

  // 5. the public demo: play and verify in the browser
  await p.goto(SITE + '#demo'); await wait(800);
  await cap('The public demo link: replay any recorded run, or play the level yourself with the arrow keys.');
  await p.click('#b-live'); await wait(600);
  for (const k of ['ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowRight']) { await p.keyboard.press(k); await wait(330); }
  await wait(1200);
  await p.evaluate(() => document.querySelector('#verify').scrollIntoView({ block: 'start' })); await wait(500);
  await cap('Type any level: the solver runs live in the browser tab and finds the shortest solution…'); await p.click('#v-play'); await wait(4200);
  await p.click('#v-break'); await cap('…or proves that a level cannot be won.'); await wait(4000);

  // 6. evidence
  await p.evaluate(() => document.querySelector('#evidence').scrollIntoView({ block: 'start' })); await wait(400);
  await cap('Measured: 200-request benchmark, zero false acceptances, model checked against the real engine, failures listed.'); await wait(6000);
  await p.evaluate(() => window.scrollTo(0, 0)); await cap('Level-Forge · Team Azərçay · NeuroBridge.SI Baku · AI Gaming'); await wait(3000);
  console.log('video seconds:', ((Date.now() - t0) / 1000).toFixed(1));
  await ctx.close(); await b.close();
  const f = fs.readdirSync(dir).find(x => x.endsWith('.webm'));
  fs.renameSync(path.join(dir, f), path.join(__dirname, 'Level-Forge_demo.webm')); fs.rmSync(dir, { recursive: true, force: true });
})();
