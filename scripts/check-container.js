#!/usr/bin/env node
/* P1-1 acceptance at 2560px on /blog and /hitech:
 *  - no visible heading sits closer to the viewport edge than the container
 *    allows (left >= (2560 - 1280)/2, within a tolerance for text-indent)
 *  - no section content block is wider than --container (1280px)
 *
 *   node scripts/check-container.js     # BASE=http://localhost:5057
 */
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://localhost:5057';
const CONTENT_BLOCKS = [
  '.map-overlay-content', '.community-card', '.world-maps-header',
  '.world-carousel', '.calendar-layout', '.site-footer .container',
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 2560, height: 1440 } });
  let bad = 0;
  for (const p of ['/blog', '/hitech']) {
    await page.goto(BASE + p, { waitUntil: 'networkidle', timeout: 45000 });
    await page.waitForTimeout(1000);
    const r = await page.evaluate((blocks) => {
      const minLeft = (innerWidth - 1280) / 2 - 1; // container edge
      const out = { headings: [], wide: [] };
      for (const h of document.querySelectorAll('h1,h2,h3')) {
        const b = h.getBoundingClientRect();
        if (!b.width || !b.height) continue;
        // centred headings pass trivially; left-aligned ones must respect the container
        if (b.left < minLeft) out.headings.push(`${h.tagName} "${h.innerText.slice(0, 30)}" left=${b.left | 0} (< ${minLeft | 0})`);
      }
      for (const sel of blocks) {
        for (const el of document.querySelectorAll(sel)) {
          const b = el.getBoundingClientRect();
          if (b.width > 1281) out.wide.push(`${sel} width=${b.width | 0}`);
        }
      }
      return out;
    }, CONTENT_BLOCKS);
    for (const m of [...r.headings, ...r.wide]) { console.error(`FAIL ${p}: ${m}`); bad++; }
  }
  await browser.close();
  if (bad) process.exit(1);
  console.log('PASS: all headings and content blocks respect the 1280px container at 2560px');
})();
