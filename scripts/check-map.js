#!/usr/bin/env node
/* P0-1 regression check: cold-load /map, perform ZERO interactions, and
 * assert Google base-map tiles were actually requested (the blank-map bug
 * loaded all JS but never fetched a single tile).
 *
 *   node scripts/check-map.js            # BASE=http://localhost:5057
 */
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://localhost:5057';
const TILE_RE = /maps\.googleapis\.com\/(maps\/vt|v1\/2dmap|.*tiles)/i;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let tiles = 0;
  page.on('request', (r) => { if (TILE_RE.test(r.url())) tiles++; });
  await page.goto(BASE + '/map', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2500); // idle settle — no clicks, no scroll
  await page.screenshot({ path: 'artifacts/check-map-coldload.png' });
  await browser.close();
  if (tiles > 0) {
    console.log(`PASS: ${tiles} tile requests on cold load with no interaction`);
  } else {
    console.error('FAIL: no base-map tile requests — blank-map regression');
    process.exit(1);
  }
})();
