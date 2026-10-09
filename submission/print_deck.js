// node submission/print_deck.js  -> submission/Level-Forge_pitch_deck.pdf (+ PNG previews)
const { chromium } = require(process.env.PW || 'playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
  const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  await p.goto('file://' + path.join(__dirname, 'deck.html')); await p.waitForTimeout(800);
  const over = await p.evaluate(() => [...document.querySelectorAll('.s')].map((s, i) => [i + 1, s.scrollHeight - s.clientHeight]).filter(x => x[1] > 0));
  console.log('overflowing slides [slide, px]:', JSON.stringify(over));
  await p.pdf({ path: path.join(__dirname, 'Level-Forge_pitch_deck.pdf'), width: '1280px', height: '720px', printBackground: true, preferCSSPageSize: true });
  const n = await p.evaluate(() => document.querySelectorAll('.s').length);
  for (let i = 0; i < n; i++) await p.locator('.s').nth(i).screenshot({ path: path.join(__dirname, 'preview', `slide_${String(i + 1).padStart(2, '0')}.png`) });
  await b.close();
})();
