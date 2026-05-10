// Galaxy Quantitative 真实控制台抓取
// 凭证从 /tmp/galaxy_creds.env 读，绝不进 shell history。
// 用法: node _design/galaxy_live/capture.mjs [--page=dashboard|copy|history|leaders|all]
//      node _design/galaxy_live/capture.mjs --headed     // 可视化调试
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';
import fs from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const HEADED = argv.includes('--headed');
const PAGE_FILTER = (argv.find(a => a.startsWith('--page=')) || '--page=all').split('=')[1];

// --- creds ---
const credsRaw = fs.readFileSync('/tmp/galaxy_creds.env', 'utf8');
const creds = Object.fromEntries(credsRaw.trim().split('\n').map(l => {
  const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)];
}));
const EMAIL = creds.GALAXY_EMAIL;
const PASSWORD = creds.GALAXY_PASSWORD;
if (!EMAIL || !PASSWORD) { console.error('missing creds'); process.exit(1); }

const ORIGIN = 'https://galaxyquantitative.com';
const OUT = __dirname;

// --- launch ---
const browser = await chromium.launch({ headless: !HEADED });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
});
const page = await ctx.newPage();

const networkLog = [];
page.on('request', r => { if (r.url().includes('/api') || r.url().includes('/user')) networkLog.push(r.method() + ' ' + r.url()); });
page.on('pageerror', e => console.error('[pageerror]', e.message));

// --- nav helpers ---
async function shot(name) {
  const p = resolve(OUT, name + '.png');
  await page.screenshot({ path: p, fullPage: false });
  console.log('  shot', name, '→', p);
}
async function shotFull(name) {
  const p = resolve(OUT, name + '-full.png');
  await page.screenshot({ path: p, fullPage: true });
  console.log('  shotFull', name, '→', p);
}
async function dumpDom(name) {
  const html = await page.content();
  fs.writeFileSync(resolve(OUT, name + '.html'), html);
  // accessibility tree (already used by recon)
  const tree = await page.accessibility.snapshot();
  fs.writeFileSync(resolve(OUT, name + '.a11y.json'), JSON.stringify(tree, null, 2));
}

// --- 1. login (direct /login route, element-ui span buttons) ---
console.log('→ goto /login');
await page.goto(ORIGIN + '/login', { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForSelector('input[placeholder*="邮箱"]', { timeout: 10000 });
await page.fill('input[placeholder*="邮箱"]', EMAIL);
await page.fill('input[type="password"]', PASSWORD);
console.log('→ filled creds, clicking 立即登录');
await page.locator('text=立即登录').first().click();
console.log('→ submit, waiting for nav');
await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
await page.waitForTimeout(1500);
// after login, force-navigate to /home — sourceHome in localStorage confirms this is the real dashboard route
if (!page.url().endsWith('/home')) {
  console.log('→ nav to /home');
  await page.goto(ORIGIN + '/home', { waitUntil: 'networkidle', timeout: 30000 });
}
console.log('  url after login:', page.url());
// wait for actual dashboard content
await page.waitForSelector('text=Hello', { timeout: 20000 });
await page.waitForLoadState('networkidle').catch(() => {});
await page.waitForTimeout(2500); // belts-and-braces for chart/widget render
console.log('✓ dashboard rendered');

// --- extract auth artifacts ---
const auth = await page.evaluate(() => {
  const ls = {};
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i); ls[k] = localStorage.getItem(k);
  }
  return { localStorage: ls, cookies: document.cookie };
});
fs.writeFileSync(resolve(OUT, 'auth.json'), JSON.stringify(auth, null, 2));
console.log('✓ auth.json saved (localStorage keys:', Object.keys(auth.localStorage).join(','), ')');

// --- 2. capture computed CSS tokens (one-shot) ---
const tokens = await page.evaluate(() => {
  const root = document.documentElement;
  const body = document.body;
  const rootStyle = getComputedStyle(root);
  const bodyStyle = getComputedStyle(body);
  // pick representative elements
  const find = (sel) => document.querySelector(sel);
  const sb = find('aside, .sidebar, nav, [class*="sidebar" i], [class*="menu" i]');
  const tb = find('header, .topbar, [class*="header" i], [class*="topbar" i]');
  const card = document.querySelectorAll('div').length ?
    Array.from(document.querySelectorAll('div')).find(d => {
      const s = getComputedStyle(d);
      return s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.borderRadius !== '0px' && d.children.length >= 1 && d.offsetWidth > 100 && d.offsetWidth < 400;
    }) : null;
  const button = find('button');
  function dump(el, label) {
    if (!el) return { label, missing: true };
    const s = getComputedStyle(el);
    return {
      label,
      tag: el.tagName.toLowerCase(),
      classes: el.className,
      bg: s.backgroundColor,
      color: s.color,
      font: s.fontFamily,
      fontSize: s.fontSize,
      fontWeight: s.fontWeight,
      borderRadius: s.borderRadius,
      border: s.border,
      padding: s.padding,
      boxShadow: s.boxShadow,
    };
  }
  return {
    root: dump(root, 'root'),
    body: dump(body, 'body'),
    sidebar: dump(sb, 'sidebar'),
    topbar: dump(tb, 'topbar'),
    card: dump(card, 'card-sample'),
    button: dump(button, 'button'),
    cssVars: Array.from(rootStyle).filter(p => p.startsWith('--')).reduce((m, p) => (m[p] = rootStyle.getPropertyValue(p), m), {}),
  };
});
fs.writeFileSync(resolve(OUT, 'tokens.json'), JSON.stringify(tokens, null, 2));
console.log('✓ tokens.json saved');

// --- 3. extract logo + asset URLs ---
const assets = await page.evaluate(() => {
  const imgs = Array.from(document.querySelectorAll('img')).map(i => ({
    alt: i.alt, src: i.src, w: i.naturalWidth, h: i.naturalHeight,
  }));
  const svgs = Array.from(document.querySelectorAll('svg')).slice(0, 10).map(s => s.outerHTML.slice(0, 800));
  const sheets = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => l.href);
  return { imgs, svgs, sheets };
});
fs.writeFileSync(resolve(OUT, 'assets.json'), JSON.stringify(assets, null, 2));
console.log('✓ assets.json saved (imgs:', assets.imgs.length, ', svgs:', assets.svgs.length, ')');

// --- 4. capture pages ---
async function captureCurrentPage(label) {
  console.log('--- capturing:', label);
  await page.waitForTimeout(1500);
  await shot('page-' + label);
  await shotFull('page-' + label);
  await dumpDom('page-' + label);
}

if (PAGE_FILTER === 'all' || PAGE_FILTER === 'dashboard') {
  await captureCurrentPage('dashboard');
}

// --- 5. navigate to other sections ---
// menu structure (from recon): <li role=menuitem><div><img></div><span>首页</span></li>
async function clickMenu(text) {
  console.log('  click menu:', text);
  // Find the <li role=menuitem> that contains a span with exact text
  const item = page.locator('li[role="menuitem"]', { has: page.locator(`span:text-is("${text}")`) }).first();
  await item.waitFor({ state: 'visible', timeout: 8000 });
  await item.scrollIntoViewIfNeeded().catch(() => {});
  await item.click();
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1800);
}

if (PAGE_FILTER === 'all' || PAGE_FILTER === 'accounts') {
  try {
    await clickMenu('账户管理');
    await captureCurrentPage('accounts');
  } catch (e) { console.error('账户管理:', e.message); }
}

if (PAGE_FILTER === 'all' || PAGE_FILTER === 'copy' || PAGE_FILTER === 'leaders' || PAGE_FILTER === 'history') {
  try {
    await clickMenu('智能跟单');
    await page.waitForTimeout(800);
    await shot('after-expand-copy');
    await dumpDom('after-expand-copy');
    // try to find sub-items
    const subitems = await page.evaluate(() => {
      const all = document.querySelectorAll('li, [role="menuitem"], a');
      return Array.from(all).map(el => el.textContent.trim()).filter(t => t && t.length < 20 && t.length > 1);
    });
    fs.writeFileSync(resolve(OUT, 'menu-items-after-copy-expand.json'), JSON.stringify(subitems, null, 2));
    console.log('  menu items:', subitems.slice(0, 30));
  } catch (e) { console.error('智能跟单:', e.message); }
}

if (PAGE_FILTER === 'all' || PAGE_FILTER === 'system') {
  try {
    await clickMenu('系统控制');
    await captureCurrentPage('system');
  } catch (e) { console.error('系统控制:', e.message); }
}

fs.writeFileSync(resolve(OUT, 'network.log'), networkLog.join('\n'));
console.log('✓ network.log saved (', networkLog.length, 'API calls)');

await browser.close();
console.log('DONE');
