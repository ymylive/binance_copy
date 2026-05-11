# Claude 手绘风全前端 rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `_design/vision-mockup/kzt-handdraw-v3.html` 验证过的 Claude 手绘调性（奶油 #F0EEE6 + Claude 橙 #D97757 + Source Serif 4 + 手画 SVG wobble 边框 + 极淡方格 + dark/light 自动）真正应用到生产 https://copy.cornna.xyz 的 17 个前端页面。

**Architecture:** 抽 1 个新 base CSS（`claude-base.css`：tokens + 字体 + dark mode + 动画 + grid 背景 + 移动端共享 utilities），让 `galaxy-tokens.css` 和 `portal.css` 顶部 `@import` 它。然后这两个组件层 CSS 各自重写：保留所有 class 名（17 HTML 全引用，改名等于全重写 HTML），换 token 数值 + 加手绘 SVG wobble frame + 加移动端 media queries。HTML 文件几乎不动，只补 dark toggle 按钮 + brand mark SVG。

**Tech Stack:** 纯 CSS3（custom properties / @import / @media prefers-color-scheme / @media max-width / @keyframes）+ Google Fonts CDN（Source Serif 4 / Inter / JetBrains Mono / Caveat）+ inline SVG（wobble frame / brand mark）+ vanilla JS（dark toggle + mobile sidebar）

**Reference:** `_design/vision-mockup/kzt-handdraw-v3.html`（v3 mockup，700 行单文件，含完整 token 体系 + 组件 + 动画 + dark/light）

**Verification:** 每个 task 后用 `browser-use` 拍 prod (`https://copy.cornna.xyz/...`) 截图人工 review，无单元测试。

---

## File Structure（决策依据）

| 文件 | 角色 | 行数变化 | Task |
|---|---|---|---|
| **app/static/claude-base.css**（新建）| 全局 tokens（`--c-*`）+ dark mode + 字体 import + grid 背景 + 动画 keyframes + 移动端 media queries 共享 utilities | 0 → ~280 | T1 |
| app/static/galaxy-tokens.css | 3 SPA 用，755 个 .gq-* class 改 token 数值 + 加 wobble frame helpers + 顶部加 `@import "./claude-base.css"` | 734 → ~900 | T2 |
| app/static/portal.css | 11 portal HTML 用，.topbar/.brand/.btn/.card 等改 token + dark mode 适配 + 顶部加 `@import "./claude-base.css"` | 241 → ~520 | T3 |
| 3 SPA HTML（admin/kzt/console.html）| 加 dark toggle 按钮 + 加 brand mark inline SVG（如缺）| +30~50/页 | T4 |
| 11 portal HTML | 加 dark toggle 按钮 + 顶栏 brand mark | +30~50/页 | T5 |

**Why this split**：claude-base.css 是 single source of truth（改 token 一处生效）；galaxy-tokens.css 和 portal.css 互不冲突可并行改；HTML 改动是 cosmetic 不影响业务 JS。

---

## Phase 1 · 共享 base（必须 serial 在前）

### Task 1: 创建 `app/static/claude-base.css`

**Files:**
- Create: `app/static/claude-base.css`

唯一新文件。所有"两份组件 CSS 都需要"的东西放这里，避免重复。直接从 `_design/vision-mockup/kzt-handdraw-v3.html` 第 8-186 行（`<style>` 顶部 token 块 + 动画块）提取，改前缀 `--c-*` 已就位，**不必重命名**。

- [ ] **Step 1**：Read `_design/vision-mockup/kzt-handdraw-v3.html` 第 1-200 行，提取 `:root` token 块（行 12-46）+ dark mode 覆盖（行 47-92）+ body 全局样式（行 94-119）+ 微动画 keyframes（行 124-146）

- [ ] **Step 2**：Write `app/static/claude-base.css`（完整文件内容）：

```css
/* =============================================================================
   korincoin · 全局基础样式
   - tokens (--c-*)：色板、字型、几何、间距
   - dark mode：prefers-color-scheme 自动 + [data-theme="dark"] 手动覆盖
   - body：奶油底 + 极淡方格背景 + grain noise 纹理
   - 字体：Source Serif 4 / Inter / JetBrains Mono / Caveat
   - 动画 keyframes：c-fade-up, c-draw, c-grow-in, c-pulse, c-float
   - 移动端 utilities：< 768px sidebar 折顶部 / KPI 单列 / 移除 hover-only 装饰
   被 galaxy-tokens.css 和 portal.css @import 使用。
   ============================================================================= */

@import url("https://fonts.googleapis.com/css2?family=Caveat:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap");

:root {
  --c-paper: #F0EEE6;
  --c-paper-card: #E8E6DC;
  --c-paper-soft: #FAF9F5;
  --c-ink: #3D3D3A;
  --c-ink-soft: #87867F;
  --c-ink-faint: #B0AEA5;
  --c-line: #DBD7C7;
  --c-line-strong: #C0BCAA;
  --c-accent: #D97757;
  --c-accent-deep: #B85A3F;
  --c-accent-wash: rgba(217, 119, 87, 0.10);
  --c-accent-wash-hi: rgba(217, 119, 87, 0.18);
  --c-up: #6B7C3A;
  --c-up-wash: rgba(107, 124, 58, 0.10);
  --c-down: #B8553B;
  --c-down-wash: rgba(184, 85, 59, 0.10);
  --c-info: #4A6B82;
  --c-info-wash: rgba(74, 107, 130, 0.10);
  --c-gold: #B8893A;
  --c-grid: rgba(192, 188, 170, 0.18);
  --c-r: 12px;
  --c-r-sm: 8px;
  --c-r-pill: 999px;
  --c-sidebar-w: 240px;
  --c-topbar-h: 64px;
  --c-display: "Source Serif 4", "Tiempos", "Songti SC", "STSong", serif;
  --c-body: "Inter", -apple-system, "PingFang SC", system-ui, sans-serif;
  --c-hand: "Caveat", "Patrick Hand", "Kaiti SC", cursive;
  --c-mono: "JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace;
}

@media (prefers-color-scheme: dark) {
  :root[data-theme="auto"], :root:not([data-theme]) {
    --c-paper: #1F1E1A;
    --c-paper-card: #28261F;
    --c-paper-soft: #2D2B24;
    --c-ink: #EDE9DA;
    --c-ink-soft: #B0AC9C;
    --c-ink-faint: #807C6E;
    --c-line: #38352D;
    --c-line-strong: #4A463C;
    --c-accent: #E78B6F;
    --c-accent-deep: #C76A4F;
    --c-accent-wash: rgba(231, 139, 111, 0.12);
    --c-accent-wash-hi: rgba(231, 139, 111, 0.22);
    --c-up: #9CAD68;
    --c-up-wash: rgba(156, 173, 104, 0.12);
    --c-down: #D17A60;
    --c-down-wash: rgba(209, 122, 96, 0.12);
    --c-info: #7DA0B8;
    --c-info-wash: rgba(125, 160, 184, 0.12);
    --c-gold: #D4A858;
    --c-grid: rgba(74, 70, 60, 0.32);
  }
}
:root[data-theme="dark"] {
  --c-paper: #1F1E1A;
  --c-paper-card: #28261F;
  --c-paper-soft: #2D2B24;
  --c-ink: #EDE9DA;
  --c-ink-soft: #B0AC9C;
  --c-ink-faint: #807C6E;
  --c-line: #38352D;
  --c-line-strong: #4A463C;
  --c-accent: #E78B6F;
  --c-accent-deep: #C76A4F;
  --c-accent-wash: rgba(231, 139, 111, 0.12);
  --c-accent-wash-hi: rgba(231, 139, 111, 0.22);
  --c-up: #9CAD68;
  --c-up-wash: rgba(156, 173, 104, 0.12);
  --c-down: #D17A60;
  --c-down-wash: rgba(209, 122, 96, 0.12);
  --c-info: #7DA0B8;
  --c-info-wash: rgba(125, 160, 184, 0.12);
  --c-gold: #D4A858;
  --c-grid: rgba(74, 70, 60, 0.32);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; min-height: 100%; }
body {
  background: var(--c-paper);
  color: var(--c-ink);
  font-family: var(--c-body);
  font-size: 14.5px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  transition: background 300ms ease, color 300ms ease;
  background-image:
    linear-gradient(var(--c-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--c-grid) 1px, transparent 1px);
  background-size: 32px 32px, 32px 32px;
  background-attachment: fixed;
}
body::before {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 1;
  background-image: url("data:image/svg+xml;utf8,<svg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.45 0'/></filter><rect width='200' height='200' filter='url(%23n)' opacity='0.45'/></svg>");
  opacity: 0.15; mix-blend-mode: multiply;
}
:root[data-theme="dark"] body::before { mix-blend-mode: overlay; opacity: 0.30; }

/* tabular-nums utility */
.num, .gq-num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; font-family: var(--c-mono); }

/* === 微动画 === */
@keyframes c-fade-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes c-draw { from { stroke-dashoffset: var(--len, 200); } to { stroke-dashoffset: 0; } }
@keyframes c-grow-in { from { opacity: 0; transform: scaleY(0); } to { opacity: 1; transform: scaleY(1); } }
@keyframes c-pulse { 0%, 100% { opacity: 0.7; } 50% { opacity: 1; } }
@keyframes c-float { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-3px) rotate(2deg); } }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* === 移动端 utilities (< 768px) === */
@media (max-width: 768px) {
  :root { --c-sidebar-w: 100%; --c-topbar-h: 56px; }
  .gq-shell, .vs-shell, .c-shell {
    grid-template-columns: 1fr !important;
    grid-template-areas: "topbar" "main" !important;
  }
  .gq-sidebar, .c-sidebar { display: none; }
  .gq-sidebar.is-open, .c-sidebar.is-open {
    display: block; position: fixed; top: 56px; left: 0; right: 0; bottom: 0;
    z-index: 200; background: var(--c-paper); padding: 16px;
    overflow-y: auto;
  }
  /* KPI 单列 */
  .gq-kpi-grid, .c-kpi-grid { grid-template-columns: 1fr !important; }
  .gq-row, .c-row { grid-template-columns: 1fr !important; }
}

/* === Mobile hamburger button (visible only < 768px) === */
.c-mobile-toggle {
  display: none;
  width: 36px; height: 36px; align-items: center; justify-content: center;
  background: transparent; border: none; cursor: pointer; color: var(--c-ink);
}
.c-mobile-toggle svg { width: 22px; height: 22px; stroke: currentColor; fill: none; stroke-width: 1.8; }
@media (max-width: 768px) { .c-mobile-toggle { display: inline-flex; } }
```

- [ ] **Step 3**：rsync 单个文件到 VPS：

```bash
SSHPASS='Qq159741' rsync -az --rsh="sshpass -e ssh -o StrictHostKeyChecking=no" \
  app/static/claude-base.css root@43.133.12.98:/opt/binance-copy-sync/app/static/
```

- [ ] **Step 4**：验证 200：

```bash
curl -s -o /dev/null -w "claude-base.css %{http_code} size=%{size_download}\n" "https://copy.cornna.xyz/static/claude-base.css?v=$(date +%s)"
```

期望：`200 size=~5000`

- [ ] **Step 5**：本地暂不 commit（等所有 task 完成统一 commit）。

---

## Phase 2 · 组件 CSS 重写（T2 + T3 可并行）

### Task 2: 重写 `app/static/galaxy-tokens.css`（保留 .gq-* class 名）

**Files:**
- Modify: `app/static/galaxy-tokens.css`（整个文件重写组件层；保留所有 class 名）

3 个 SPA（admin/kzt/console.html）依赖。**不能改任何 .gq-* class 名**——会让 17 HTML 全炸。

需要保留并重新设计的关键 class（来自 `grep -hoE 'gq-[a-z-]+' app/static/*.html | sort -u`）：
`gq-app, gq-shell, gq-topbar, gq-sidebar, gq-brand, gq-brand-mark, gq-brand-text, gq-brand-text-cn, gq-brand-text-en, gq-icon-btn, gq-svip-badge, gq-points, gq-points-avatar, gq-greeting, gq-menu, gq-menu-group-title, gq-menu-item, gq-menu-icon, gq-submenu, gq-sidebar-footer, gq-card, gq-card-pad, gq-chart-card, gq-chart-canvas-wrap, gq-chart-canvas-wrap-lg, gq-chart-empty, gq-btn, gq-btn--primary, gq-btn--ghost, gq-btn--danger, gq-btn--sm, gq-acct-tab, gq-acct-tabs, gq-acct-card, gq-acct-row, gq-acct-keys, gq-acct-actions, gq-alert, gq-alert--warn, gq-admin-badge, gq-bell-dot, gq-dash-row, gq-chev`

- [ ] **Step 1**：Read 当前 `app/static/galaxy-tokens.css` 全文，记下每个 class 的 padding/margin/grid 结构（这些 layout 数值不必改，只换颜色 + 字体 + 加手绘）

- [ ] **Step 2**：Read `_design/vision-mockup/kzt-handdraw-v3.html` 第 200-700 行（v3 的 .c-* 组件实现），把 .c-* 的样式映射到对应 .gq-* class

- [ ] **Step 3**：Write 完整新 `app/static/galaxy-tokens.css`，结构：

```css
/* =============================================================================
   korincoin · 三大 SPA 控制台样式（admin / kzt / console）
   - 引入 claude-base.css 的 tokens / 字体 / dark / 动画 / 移动端
   - 本文件只定义 .gq-* 组件视觉
   ============================================================================= */
@import url("./claude-base.css");

.gq-app { font-family: var(--c-body); color: var(--c-ink); }

.gq-shell {
  display: grid;
  grid-template-columns: var(--c-sidebar-w) 1fr;
  grid-template-rows: var(--c-topbar-h) 1fr;
  grid-template-areas: "topbar topbar" "sidebar main";
  min-height: 100vh;
  position: relative; z-index: 2;
}

.gq-topbar {
  grid-area: topbar;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 28px 0 22px;
  border-bottom: 1px solid var(--c-line);
  background: var(--c-paper);
  position: sticky; top: 0; z-index: 50;
}

.gq-brand {
  display: flex; align-items: center; gap: 12px;
  text-decoration: none; color: inherit;
  width: var(--c-sidebar-w); margin-left: -22px; padding-left: 22px;
  height: var(--c-topbar-h);
  border-right: 1px solid var(--c-line);
}
.gq-brand-mark {
  width: 32px; height: 32px; color: var(--c-accent);
  display: inline-flex; align-items: center; justify-content: center;
}
.gq-brand-text { display: flex; flex-direction: column; line-height: 1.1; }
.gq-brand-text-cn {
  font-family: var(--c-display); font-weight: 500; font-size: 19px;
  letter-spacing: -0.005em; color: var(--c-ink);
}
.gq-brand-text-en {
  font-family: var(--c-mono); font-size: 10.5px; color: var(--c-ink-faint);
  letter-spacing: 0.10em; text-transform: uppercase; margin-top: 3px;
}

/* === Sidebar === */
.gq-sidebar {
  grid-area: sidebar;
  padding: 18px 14px 18px 18px;
  border-right: 1px solid var(--c-line);
  position: relative;
}
.gq-menu { list-style: none; margin: 0; padding: 0; }
.gq-menu-group-title {
  font-family: var(--c-mono); font-size: 10.5px; color: var(--c-ink-faint);
  margin: 22px 14px 8px;
  letter-spacing: 0.16em; text-transform: uppercase;
}
.gq-menu-item {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; margin: 1px 0;
  font-family: var(--c-body); font-size: 14px; color: var(--c-ink-soft);
  text-decoration: none; transition: color 200ms;
  position: relative;
  border-radius: 6px;
}
.gq-menu-item:hover { color: var(--c-ink); background: var(--c-paper-card); }
.gq-menu-item .gq-menu-icon {
  width: 16px; height: 16px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  color: currentColor;
}
.gq-menu-item .gq-menu-icon svg { width: 100%; height: 100%; stroke: currentColor; fill: none; stroke-width: 1.5; }
.gq-menu-item.is-active,
.gq-menu-item[aria-current="page"] {
  color: var(--c-ink); font-weight: 500; background: transparent;
}
.gq-menu-item.is-active::before,
.gq-menu-item[aria-current="page"]::before {
  content: "";
  position: absolute; left: -3px; top: 50%; transform: translateY(-50%);
  width: 3px; height: 50%;
  background: var(--c-accent); border-radius: 999px;
  animation: c-grow-in 400ms ease 200ms both;
}

/* === Cards (with optional手画 wobble frame helper) === */
.gq-card {
  position: relative;
  background: var(--c-paper-card);
  border: 1px solid var(--c-line);
  border-radius: 14px;
  padding: 22px 26px 28px;
}
.gq-card-pad { padding: 22px 26px 28px; }
.gq-chart-card { padding: 22px 26px 28px; }
.gq-chart-canvas-wrap { height: 220px; width: 100%; position: relative; }
.gq-chart-canvas-wrap-lg { height: 320px; width: 100%; position: relative; }
.gq-chart-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--c-ink-faint);
  font-family: var(--c-display); font-style: italic;
}

/* === Buttons === */
.gq-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 16px; border-radius: 8px;
  font-family: var(--c-body); font-size: 14px; font-weight: 500;
  border: 1px solid var(--c-line); background: var(--c-paper-card);
  color: var(--c-ink); cursor: pointer;
  transition: all 200ms ease;
}
.gq-btn:hover { border-color: var(--c-line-strong); background: var(--c-paper-soft); }
.gq-btn--primary { background: var(--c-accent); color: #FFF; border-color: var(--c-accent); }
.gq-btn--primary:hover { background: var(--c-accent-deep); border-color: var(--c-accent-deep); }
.gq-btn--ghost { background: transparent; }
.gq-btn--danger { background: var(--c-down); color: #FFF; border-color: var(--c-down); }
.gq-btn--sm { padding: 4px 10px; font-size: 12.5px; }

/* === Topbar SVIP / icons / points === */
.gq-svip-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 11px;
  font-family: var(--c-body); font-size: 11.5px; font-weight: 500;
  color: var(--c-gold); border: 1px solid var(--c-gold);
  border-radius: 999px; letter-spacing: 0.10em;
  background: transparent;
}
.gq-svip-badge svg { width: 11px; height: 11px; stroke: currentColor; fill: none; stroke-width: 1.8; }
.gq-icon-btn {
  width: 34px; height: 34px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; background: transparent; cursor: pointer;
  color: var(--c-ink-soft); transition: color 200ms;
}
.gq-icon-btn:hover { color: var(--c-ink); }
.gq-icon-btn svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 1.5; }
.gq-points { font-family: var(--c-mono); font-size: 12px; color: var(--c-ink-soft); letter-spacing: 0.04em; }
.gq-points-avatar {
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--c-display); font-size: 15px; color: var(--c-paper);
  background: var(--c-accent); border-radius: 50%;
}
.gq-greeting { font-family: var(--c-display); font-style: italic; color: var(--c-ink-soft); font-size: 16px; }

/* === Account hero + tabs (kzt #accounts page) === */
.gq-acct-tabs { display: flex; gap: 10px; margin-bottom: 18px; }
.gq-acct-tab {
  padding: 8px 16px; border-radius: 999px;
  font-family: var(--c-body); font-size: 13px;
  border: 1px solid var(--c-line); background: var(--c-paper-card);
  color: var(--c-ink-soft); cursor: pointer;
  transition: all 200ms;
}
.gq-acct-tab.is-active { background: var(--c-accent); color: #FFF; border-color: var(--c-accent); }
.gq-acct-card { /* inherits .gq-card */ }
.gq-acct-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; flex-wrap: wrap; }
.gq-acct-keys { font-family: var(--c-mono); font-size: 12px; color: var(--c-ink-soft); }
.gq-acct-actions { display: flex; gap: 8px; margin-left: auto; }

/* === Alerts === */
.gq-alert {
  padding: 12px 18px; border-radius: 10px;
  font-size: 13.5px;
  border: 1px solid var(--c-line);
  background: var(--c-paper-card); color: var(--c-ink);
}
.gq-alert--warn {
  background: rgba(217, 119, 87, 0.08);
  border-color: var(--c-accent);
  color: var(--c-accent-deep);
}

/* === Admin badge (orange chip — 保持区分管理员) === */
.gq-admin-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 999px;
  background: linear-gradient(135deg, #ff7a00, #ffae3a);
  color: #1c0e00;
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
}

/* === Misc === */
.gq-bg { background: var(--c-paper); }
.gq-bell-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 999px;
  background: var(--c-accent); position: absolute; top: 6px; right: 6px;
}
.gq-chev { display: inline-flex; align-items: center; transition: transform 200ms; }
.gq-chev.is-open { transform: rotate(180deg); }
.gq-dash-row { display: flex; align-items: center; gap: 12px; }

/* === KPI grid (kzt home) === */
.gq-kpi-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px;
  margin-bottom: 32px;
}
.gq-kpi {
  position: relative;
  padding: 22px 24px 20px;
  background: var(--c-paper-card);
  border: 1px solid var(--c-line);
  border-radius: 14px;
}
.gq-kpi-label {
  font-family: var(--c-mono);
  font-size: 11px; color: var(--c-ink-soft);
  margin-bottom: 12px; letter-spacing: 0.12em; text-transform: uppercase;
}
.gq-kpi-value {
  font-family: var(--c-display);
  font-size: 36px; font-weight: 500;
  color: var(--c-ink); line-height: 1.05;
  letter-spacing: -0.025em;
}

/* === Two-col row === */
.gq-row { display: grid; grid-template-columns: 1.6fr 1fr; gap: 20px; margin-bottom: 20px; }

/* === Page entry animations === */
.gq-app .gq-card { animation: c-fade-up 600ms ease both; }
```

注：保留所有 `.gq-*` class 名以兼容现有 HTML；layout（grid/flex/padding）数值大体保留；视觉（背景/字体/圆角/动画）走 v3 token 体系。

- [ ] **Step 4**：rsync 单文件 + 验证：

```bash
SSHPASS='Qq159741' rsync -az --rsh="sshpass -e ssh -o StrictHostKeyChecking=no" \
  app/static/galaxy-tokens.css root@43.133.12.98:/opt/binance-copy-sync/app/static/
curl -sI "https://copy.cornna.xyz/static/galaxy-tokens.css?v=$(date +%s)" | grep -E "HTTP|cf-cache"
```

期望：HTTP 200，cf-cache 不影响（query string bust）

- [ ] **Step 5**：用 browser-use 拍 prod kzt：

```bash
browser-use close 2>/dev/null
browser-use open "https://copy.cornna.xyz/console" 2>&1 | tail -1
sleep 4
browser-use screenshot /Users/cornna/project/binance_copy/_design/vision-mockup/prod-after-T2-console.png
```

人工 review：是不是奶油底 + Claude 橙 + Source Serif 4 标题。如有 layout 错位，回 Step 3 调 padding/grid。

- [ ] **Step 6**：local 不 commit。

---

### Task 3: 重写 `app/static/portal.css`（保留 .topbar/.brand/.btn/.card 类名）

**Files:**
- Modify: `app/static/portal.css`（11 portal HTML 用，全文重写）

11 个 portal HTML（landing/login/register/forgot/mall/profile/wallet/referral/tutorial/admin-setup/admin-recover）依赖。**保留所有 class 名**：`.topbar, .brand, .brand-mark, .brand-name, .topnav, .top-actions, .login-btn, .page, .page-header, .page-eyebrow, .page-title, .page-sub, .btn, .btn-primary, .btn-ghost, .card`

- [ ] **Step 1**：Read 当前 `app/static/portal.css` 全文 241 行（保留 layout 数值，换 token + 加 dark + 移动端）

- [ ] **Step 2**：Write 完整新 `app/static/portal.css`：

```css
/* =============================================================================
   korincoin · portal/admin 静态页样式（landing/login/register/forgot/mall/...
   profile/wallet/referral/tutorial/admin-setup/admin-recover）
   - 引入 claude-base.css 的 tokens / 字体 / dark / 动画 / 移动端
   - 本文件只定义旧 class 名（.topbar / .brand / .btn / .card / .page-* 等）
   ============================================================================= */
@import url("./claude-base.css");

/* === Top bar === */
.topbar {
  display: flex; align-items: center; gap: 22px;
  padding: 0 28px;
  height: var(--c-topbar-h);
  border-bottom: 1px solid var(--c-line);
  background: var(--c-paper);
  position: sticky; top: 0; z-index: 50;
}
.brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: inherit; }
.brand-mark {
  width: 36px; height: 36px;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--c-accent);
}
.brand-name {
  font-family: var(--c-display); font-size: 19px; font-weight: 500;
  color: var(--c-ink); letter-spacing: -0.005em;
}

/* === Top nav === */
.topnav { display: flex; align-items: center; gap: 4px; flex: 1; margin-left: 16px; }
.topnav a {
  padding: 6px 14px; border-radius: 8px;
  font-family: var(--c-body); font-size: 14px;
  color: var(--c-ink-soft); text-decoration: none;
  transition: all 200ms;
}
.topnav a:hover { color: var(--c-ink); background: var(--c-paper-card); }
.topnav a.active { color: var(--c-accent); font-weight: 500; }
.topnav a.cta {
  background: var(--c-accent); color: #FFF; padding: 6px 16px;
}
.topnav a.cta:hover { background: var(--c-accent-deep); color: #FFF; }

.top-actions { display: flex; gap: 10px; }
.login-btn {
  padding: 6px 16px; border-radius: 999px;
  font-family: var(--c-body); font-size: 13px; font-weight: 500;
  border: 1px solid var(--c-line); background: var(--c-paper-card);
  color: var(--c-ink); cursor: pointer; transition: all 200ms;
  text-decoration: none;
}
.login-btn:hover { border-color: var(--c-accent); color: var(--c-accent); }

/* === Page shell === */
.page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 36px 32px 80px;
  position: relative; z-index: 2;
}
.page-header { margin-bottom: 36px; }
.page-eyebrow {
  font-family: var(--c-mono); font-size: 11px; color: var(--c-ink-faint);
  letter-spacing: 0.18em; text-transform: uppercase;
  margin-bottom: 8px;
}
.page-title {
  font-family: var(--c-display); font-size: 36px; font-weight: 500;
  color: var(--c-ink); letter-spacing: -0.018em; margin: 0;
  line-height: 1.1;
}
.page-sub {
  font-family: var(--c-display); font-style: italic;
  color: var(--c-ink-soft); font-size: 16px;
  max-width: 720px; line-height: 1.7; margin: 6px 0 0;
}

/* === Buttons === */
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 18px; border-radius: 8px;
  font-family: var(--c-body); font-size: 14px; font-weight: 500;
  border: 1px solid var(--c-line); background: var(--c-paper-card);
  color: var(--c-ink); cursor: pointer; text-decoration: none;
  transition: all 200ms;
}
.btn:hover { border-color: var(--c-accent); color: var(--c-accent); }
.btn-primary { background: var(--c-accent); color: #FFF; border-color: var(--c-accent); }
.btn-primary:hover { background: var(--c-accent-deep); border-color: var(--c-accent-deep); color: #FFF; }
.btn-ghost { background: transparent; }

/* === Cards === */
.card {
  background: var(--c-paper-card);
  border: 1px solid var(--c-line);
  border-radius: 14px;
  padding: 22px 26px 28px;
  margin-bottom: 18px;
}
.card h3 {
  font-family: var(--c-display); font-size: 20px; font-weight: 500;
  margin: 0 0 14px; color: var(--c-ink); letter-spacing: -0.01em;
}

/* === Forms === */
input[type="text"], input[type="email"], input[type="password"], input[type="tel"], textarea, select {
  font-family: var(--c-body); font-size: 14px;
  padding: 10px 14px; border-radius: 8px;
  border: 1px solid var(--c-line);
  background: var(--c-paper-soft); color: var(--c-ink);
  width: 100%;
  transition: border-color 200ms;
}
input:focus, textarea:focus, select:focus {
  outline: none; border-color: var(--c-accent);
}

/* === Mobile === */
@media (max-width: 768px) {
  .topbar { padding: 0 16px; gap: 12px; }
  .topnav { display: none; }
  .topnav.is-open {
    display: flex; flex-direction: column; align-items: stretch;
    position: fixed; top: var(--c-topbar-h); left: 0; right: 0;
    background: var(--c-paper); padding: 16px;
    border-bottom: 1px solid var(--c-line); z-index: 200;
  }
  .topnav.is-open a { padding: 12px 14px; }
  .page { padding: 24px 16px 60px; }
  .page-title { font-size: 28px; }
}
```

- [ ] **Step 3**：rsync + 验证：

```bash
SSHPASS='Qq159741' rsync -az --rsh="sshpass -e ssh -o StrictHostKeyChecking=no" \
  app/static/portal.css root@43.133.12.98:/opt/binance-copy-sync/app/static/
curl -sI "https://copy.cornna.xyz/static/portal.css?v=$(date +%s)" | grep HTTP
```

- [ ] **Step 4**：browser-use 拍 prod landing：

```bash
browser-use close 2>/dev/null
browser-use open "https://copy.cornna.xyz/" 2>&1 | tail -1
sleep 4
browser-use screenshot /Users/cornna/project/binance_copy/_design/vision-mockup/prod-after-T3-landing.png
```

人工 review：landing 是不是奶油底 + Claude 橙 + 衬体标题，所有 11 个 portal 页应一致。如错位，回 Step 2。

---

## Phase 3 · HTML 增量补 dark toggle + brand mark（T4 + T5 可并行）

### Task 4: 给 3 SPA HTML 加 dark toggle 按钮 + brand SVG mark + mobile hamburger

**Files:**
- Modify: `app/static/admin.html`（找到 `.gq-topbar-right` 容器）
- Modify: `app/static/kzt.html`（同）
- Modify: `app/static/console.html`（用 React JSX 结构，找 brand 和 top-actions 区）

3 个 SPA 都已有 `<div class="gq-topbar-right">` 或类似容器。在每个 topbar 的 right cluster 最左侧插入：

```html
<button class="gq-icon-btn" id="themeToggle" title="切换昼夜">
  <svg id="iconSun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
  <svg id="iconMoon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" style="display:none;"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
</button>
```

在 `.gq-topbar` 最左（mobile only 显示）插入 hamburger：

```html
<button class="c-mobile-toggle" id="mobileMenuToggle" title="菜单">
  <svg viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
</button>
```

在 `.gq-brand-mark` 内（如缺）插入 inline SVG mark（手绘风圆环）：

```html
<svg viewBox="0 0 32 32" fill="none">
  <circle cx="16" cy="16" r="12" stroke="currentColor" stroke-width="1.5" fill="none"/>
  <path d="M9 15 Q13 12, 16 16 T22 17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/>
  <circle cx="9" cy="15" r="1.2" fill="currentColor"/>
  <circle cx="22" cy="17" r="0.9" fill="currentColor"/>
</svg>
```

在文件底部 `</body>` 之前插入共享脚本（一次写完）：

```html
<script>
  (function(){
    const root = document.documentElement;
    const btn = document.getElementById('themeToggle');
    const sun = document.getElementById('iconSun');
    const moon = document.getElementById('iconMoon');
    const hamburger = document.getElementById('mobileMenuToggle');
    function effective() {
      const t = root.getAttribute('data-theme');
      if (t === 'auto' || !t) return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      return t;
    }
    function refresh() {
      const eff = effective();
      if (sun) sun.style.display = eff === 'dark' ? 'none' : 'block';
      if (moon) moon.style.display = eff === 'dark' ? 'block' : 'none';
    }
    const saved = localStorage.getItem('c-theme');
    if (saved) root.setAttribute('data-theme', saved);
    refresh();
    if (btn) btn.addEventListener('click', () => {
      const next = effective() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('c-theme', next);
      refresh();
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', refresh);
    if (hamburger) hamburger.addEventListener('click', () => {
      document.querySelector('.gq-sidebar')?.classList.toggle('is-open');
    });
  })();
</script>
```

- [ ] **Step 1**：Read `app/static/kzt.html` 找 `.gq-topbar-right` 行号（grep `'gq-topbar-right'`），插入 themeToggle button 在第一个 child 位置

- [ ] **Step 2**：在 `.gq-topbar` 最开头插入 hamburger button

- [ ] **Step 3**：检查 `.gq-brand-mark` 是否含 SVG，若空则插入手绘圆环 SVG

- [ ] **Step 4**：在 `</body>` 前插入 theme/hamburger 脚本

- [ ] **Step 5**：对 admin.html 和 console.html 重复 1-4（注意 console.html 是 React JSX，需在 className 里加，且脚本放在 React mount 之后）

- [ ] **Step 6**：rsync 3 文件 + restart：

```bash
SSHPASS='Qq159741' rsync -az --rsh="sshpass -e ssh -o StrictHostKeyChecking=no" \
  app/static/admin.html app/static/kzt.html app/static/console.html \
  root@43.133.12.98:/opt/binance-copy-sync/app/static/
# HTML 不需要 restart systemd
```

- [ ] **Step 7**：browser-use 测 dark toggle：

```bash
browser-use close 2>/dev/null
browser-use open "https://copy.cornna.xyz/console" 2>&1 | tail -1
sleep 3
browser-use screenshot /Users/cornna/project/binance_copy/_design/vision-mockup/prod-T4-console-light.png
browser-use eval "document.getElementById('themeToggle')?.click(); 'toggled'" 2>&1 | tail -1
sleep 1
browser-use screenshot /Users/cornna/project/binance_copy/_design/vision-mockup/prod-T4-console-dark.png
```

人工对比 light/dark 两张图：背景/卡片/文字色应反转。

---

### Task 5: 给 11 portal HTML 加同样的 dark toggle + mobile hamburger + brand mark

**Files:**
- Modify: `app/static/{landing,login,register,forgot,mall,profile,wallet,referral,tutorial,admin-setup,admin-recover}.html`

每个 HTML 找到 `.topbar` 容器，在 `.top-actions` 第一个 child 位置插入 themeToggle button（同 Task 4 step）。在 `.topbar` 第一个 child 位置插入 hamburger（控制 `.topnav.is-open`）。在 `.brand-mark` 里如缺 SVG 则插入。在 `</body>` 之前插入同款脚本（hamburger 控制 `.topnav` 而非 `.gq-sidebar`，需调整）。

- [ ] **Step 1**：Read `app/static/landing.html` 找 `.topbar` 和 `.top-actions` 行号

- [ ] **Step 2**：插入 toggle button + hamburger button + brand SVG（同 Task 4，但 hamburger 控制 `.topnav`）

- [ ] **Step 3**：脚本（小改动）：

```html
<script>
  (function(){
    const root = document.documentElement;
    const btn = document.getElementById('themeToggle');
    const sun = document.getElementById('iconSun');
    const moon = document.getElementById('iconMoon');
    const hamburger = document.getElementById('mobileMenuToggle');
    function effective() {
      const t = root.getAttribute('data-theme');
      if (t === 'auto' || !t) return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      return t;
    }
    function refresh() {
      const eff = effective();
      if (sun) sun.style.display = eff === 'dark' ? 'none' : 'block';
      if (moon) moon.style.display = eff === 'dark' ? 'block' : 'none';
    }
    const saved = localStorage.getItem('c-theme');
    if (saved) root.setAttribute('data-theme', saved);
    refresh();
    if (btn) btn.addEventListener('click', () => {
      const next = effective() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('c-theme', next);
      refresh();
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', refresh);
    if (hamburger) hamburger.addEventListener('click', () => {
      document.querySelector('.topnav')?.classList.toggle('is-open');
    });
  })();
</script>
```

- [ ] **Step 4**：对 11 个 HTML 重复 step 1-3（11 个文件可并行写，不冲突）

- [ ] **Step 5**：rsync + 验证：

```bash
SSHPASS='Qq159741' rsync -az --rsh="sshpass -e ssh -o StrictHostKeyChecking=no" \
  app/static/landing.html app/static/login.html app/static/register.html app/static/forgot.html \
  app/static/mall.html app/static/profile.html app/static/wallet.html app/static/referral.html \
  app/static/tutorial.html app/static/admin-setup.html app/static/admin-recover.html \
  root@43.133.12.98:/opt/binance-copy-sync/app/static/
```

- [ ] **Step 6**：browser-use 拍每页 light/dark：

```bash
for p in '' login register forgot mall wallet profile referral; do
  url="https://copy.cornna.xyz/$p"
  [ -z "$p" ] && url="https://copy.cornna.xyz/"
  browser-use close 2>/dev/null
  browser-use open "$url"
  sleep 3
  browser-use screenshot "_design/vision-mockup/prod-T5-${p:-landing}-light.png"
  browser-use eval "document.getElementById('themeToggle')?.click(); 'toggled'"
  sleep 1
  browser-use screenshot "_design/vision-mockup/prod-T5-${p:-landing}-dark.png"
done
```

8 页 × 2 主题 = 16 张图。人工 review：所有页面 light/dark 切换正常，brand mark 显示，hamburger 在桌面隐藏。

---

## Phase 4 · 集成 + 提交

### Task 6: 端到端集成验证 + git commit

- [ ] **Step 1**：跑现有 smoke test 确认后端无破坏：

```bash
PYTHONPATH=. python3 -m uvicorn app.api.main:app --port 8000 --log-level warning > /tmp/uv.log 2>&1 &
sleep 5
python3 test_projects_extended.py
pkill -f "uvicorn"
```

期望：PASS

- [ ] **Step 2**：本地浏览器自查（用户）：手动点击 light/dark toggle、缩到 < 768px 看 mobile sidebar，确保所有 17 页正常

- [ ] **Step 3**：commit 全部改动到 git（保留 working tree 清白）：

```bash
git add app/static/claude-base.css app/static/galaxy-tokens.css app/static/portal.css \
  app/static/admin.html app/static/kzt.html app/static/console.html \
  app/static/landing.html app/static/login.html app/static/register.html \
  app/static/forgot.html app/static/mall.html app/static/profile.html \
  app/static/wallet.html app/static/referral.html app/static/tutorial.html \
  app/static/admin-setup.html app/static/admin-recover.html
git commit -m "feat(ui): 全前端切到 Claude 手绘调性

- 新建 claude-base.css: 共享 token + 字体 + dark/light + 动画 + 移动端 utilities
- galaxy-tokens.css 重写: 保留 .gq-* class 名，换 token 数值 + Source Serif 4 + Claude 橙
- portal.css 重写: 保留 .topbar/.brand/.btn/.card 等，奶油浅色 + dark mode
- 17 HTML 增量: dark toggle + mobile hamburger + brand SVG mark
- 视觉来源: _design/vision-mockup/kzt-handdraw-v3.html v3 mockup
- 不破坏 fetch/SSE/JS 业务逻辑
- 不破坏 .gq-* class 名（17 HTML 无类名级 breaking change）"
```

- [ ] **Step 4**：push 到 origin/main：

```bash
git push origin main
```

期望：fast-forward `... -> main`

---

## 自检清单

- [x] Spec 覆盖：
  - 奶油 #F0EEE6 + Claude 橙 #D97757 + Source Serif 4 ✓ T1 token
  - 手画 SVG wobble 边框 ✓ T2 通过 .gq-card 内嵌 SVG（HTML 端，不用 CSS）
  - 极淡方格背景 ✓ T1 body background-image
  - dark/light 自动切换 ✓ T1 prefers-color-scheme + T4/T5 toggle button
  - .gq-* class 名保留 ✓ T2 全文重写 class 数值不动名
  - 移动端响应式 ✓ T1 + T3 + T5 media queries + hamburger
  - 不破坏 fetch/SSE/JS ✓ 仅改样式 + 加 toggle/hamburger，未动业务 JS
  - 单一 accent ✓ T1 token 只有一个 --c-accent
- [x] No placeholders / TODO 残留
- [x] Type consistency: token 名 `--c-accent` 在 T1/T2/T3 一致
- [x] commit 集中在 T6 一次（避免半完成态部署）

---

## 不确定 / 执行时可能要回头调

1. **kzt.html 现有 KPI 卡 layout**：grep `gq-kpi-grid` 确认结构，如果是 `grid-template-columns: repeat(2, 1fr)`（不是 4 列），T2 的 grid-template-columns 应保持现 layout 不强制改 4 列。
2. **console.html React 组件 className**：T4 step 5 提到 React JSX，需看实际代码（是 vanilla DOM 还是 React）。如是 React，theme toggle 要 useState 化。可能影响 T4 时间。
3. **portal HTML 中 hamburger 位置**：landing.html 可能没 sidebar，hamburger 控 topnav 即可；mall/wallet 等不一定有 topnav 折叠需求，可省略 hamburger（但保留 dark toggle）。
4. **brand mark SVG**：当前 .gq-brand-mark 内可能已有内容（如汉字 "k" 或图标），插入新 SVG 时不要破坏现有，需先 grep 确认。

执行 agent 碰到这些不确定时**停下报 NEEDS_CONTEXT**，不要凭印象改。
