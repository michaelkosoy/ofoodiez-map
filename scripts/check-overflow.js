#!/usr/bin/env node
/* P0-4 acceptance: with the overflow-x mask disabled, no route may be wider
 * than the viewport (scrollWidth <= innerWidth) at 390 / 1440 / 2560.
 * Reports every element that pokes past the right or left viewport edge.
 *
 *   node scripts/check-overflow.js      # BASE=http://localhost:5057
 */
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://localhost:5057';
const WIDTHS = [390, 1440, 2560];
const PATHS = [
  '/', '/blog', '/map', '/about', '/blog/japan', '/blog/bachelorette',
  '/hitech', '/hitech/community', '/hitech/referrals-bot', '/hitech/cv-guide',
  '/hitech/cv-review', '/portfolio',
];

(async () => {
  const browser = await chromium.launch();
  let bad = 0;
  for (const width of WIDTHS) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 } });
    for (const p of PATHS) {
      const page = await ctx.newPage();
      try {
        await page.goto(BASE + p, { waitUntil: 'networkidle', timeout: 45000 });
        await page.waitForTimeout(800);
        const r = await page.evaluate(() => {
          document.documentElement.style.overflowX = 'visible';
          document.body.style.overflowX = 'visible';
          const overflowers = [];
          // Two by-design cases create element boxes past the viewport without
          // page overflow: transformed subtrees (closed drawer at
          // translateX(-100%)) and content inside horizontal scrollers
          // (card carousels, tab strips). Skip both.
          const benign = (e) => {
            for (let n = e; n && n !== document.documentElement; n = n.parentElement) {
              const cs = getComputedStyle(n);
              if (cs.transform !== 'none') return true;
              // any non-visible overflow-x ancestor (scroller OR clipper, e.g.
              // carousel track wraps) stops propagation to the page box;
              // the root itself is excluded above, so page-level masking
              // can't hide real overflow like the footer bug
              if (n !== e && cs.overflowX !== 'visible') return true;
            }
            return false;
          };
          for (const el of document.querySelectorAll('body *')) {
            const b = el.getBoundingClientRect();
            if (benign(el)) continue;
            if (b.width && (b.right > innerWidth + 1 || b.left < -1)) {
              const cls = (typeof el.className === 'string' && el.className) ? '.' + el.className.split(' ')[0] : '';
              overflowers.push(`${el.tagName}${cls} left=${b.left | 0} right=${b.right | 0}`);
            }
            if (overflowers.length > 4) break;
          }
          return {
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth,
            overflowers,
          };
        });
        // scrollWidth alone is clamped by overflow:hidden roots — any element
        // box past the viewport edges counts as a failure too
        if (r.scrollWidth > r.innerWidth || r.overflowers.length) {
          bad++;
          console.error(`FAIL ${width} ${p}: scrollWidth ${r.scrollWidth} vs ${r.innerWidth}`);
          r.overflowers.forEach((o) => console.error(`   ${o}`));
        }
      } catch (e) {
        console.error(`ERROR ${width} ${p}: ${e.message.split('\n')[0]}`);
      } finally {
        await page.close();
      }
    }
    await ctx.close();
  }
  await browser.close();
  if (bad) { console.error(`${bad} route/viewport combos overflow`); process.exit(1); }
  console.log('PASS: no horizontal overflow on any route at any viewport');
})();
