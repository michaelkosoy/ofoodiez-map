#!/usr/bin/env node
/* Screenshot a list of routes at the three audit viewports.
 *
 *   node scripts/shots.js <label> [path ...]
 *
 * Saves to artifacts/<label>/<slug>-<width>.png. Defaults to the audit's
 * nine routes when no paths are given. BASE overrides the target origin
 * (default http://localhost:5057).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE || 'http://localhost:5057';
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 2560, height: 1440 },
  { width: 390, height: 844 },
];
const DEFAULT_PATHS = [
  '/', '/blog', '/map', '/blog/japan', '/hitech', '/hitech/referrals-bot',
  '/hitech/cv-review', '/about', '/portfolio',
];

const label = process.argv[2];
if (!label) {
  console.error('usage: node scripts/shots.js <label> [path ...]');
  process.exit(1);
}
const paths = process.argv.length > 3 ? process.argv.slice(3) : DEFAULT_PATHS;
const outDir = path.join(__dirname, '..', 'artifacts', label);

const slug = (p) => (p === '/' ? 'root' : p.replace(/^\//, '').replace(/\//g, '-'));

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1 });
    for (const p of paths) {
      const page = await ctx.newPage();
      try {
        await page.goto(BASE + p, { waitUntil: 'networkidle', timeout: 45000 });
        await page.waitForTimeout(1500); // fonts, maps, lazy paint
        // fullPage capture never fires IntersectionObserver for below-fold
        // [data-reveal] blocks — force-reveal so screenshots show real content
        await page.evaluate(() => document.querySelectorAll('[data-reveal]').forEach((e) => e.classList.add('is-visible')));
        await page.waitForTimeout(300);
        // /map is a fixed-viewport app; everything else is a document.
        const fullPage = p !== '/map';
        const file = path.join(outDir, `${slug(p)}-${vp.width}.png`);
        await page.screenshot({ path: file, fullPage });
        console.log(`ok ${vp.width}x${vp.height} ${p} -> ${path.relative(process.cwd(), file)}`);
      } catch (e) {
        console.error(`FAIL ${vp.width}x${vp.height} ${p}: ${e.message.split('\n')[0]}`);
      } finally {
        await page.close();
      }
    }
    await ctx.close();
  }
  await browser.close();
})();
