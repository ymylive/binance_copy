# 银河量化 Galaxy Quantitative · Brand Spec
> 采集日期：2026-05-08
> 来源：browser-use 登录 galaxyquantitative.com 实拍 6 页 + bundled CSS `/assets/index-BVhBjcNK.css`（428KB）解析
> 资产完整度：完整（6 屏截图 + 同名 HTML + computed CSS + 解析后的 Element Plus token 表）
> 技术底座：Vue 3 SPA + Element Plus（`el-aside / el-header / el-menu / el-table / el-alert / el-switch / el-tabs`），通过 `--el-color-primary: #3acbbe` 等 CSS 变量覆盖默认主题。

---

## 🎯 核心资产

### Logo
- 描述：**圆形薄荷绿底 + 白色简笔图标 + "银河量化 / GalaxyQuant"** 中英双语，中文衬体（宋体）+ 英文小号衬体；marker 与文字水平排列。
- 文件：`/Users/cornna/project/binance_copy/_design/galaxy_live/bu-1-dashboard.png` 左上角（top-left 0..120 × 0..56 区域可裁剪）。
- 尺寸：圆形 marker 28×28，整体 lockup 约 130×40。
- 说明：在所有页面都呈现于 sidebar 顶部白底区，不在深色背景出现。

### UI 截图（6 页 / 8 张）
| 截图 | 表达内容 |
| --- | --- |
| `_design/galaxy_live/bu-1-dashboard.png` (+ `-full.png`) | `/kzt` Dashboard：4 KPI 卡 + iframe 占位 + 资讯卡 + BTC 行情条 + 6 数据指标卡 + POLONIEX 广告卡 + 帮助卡 |
| `_design/galaxy_live/bu-2-accounts.png` (+ `-full.png`) | `/account` 账户管理：账户胶囊 tabs + 当前账户卡（IP / 交易所 / API Key 等）+ 收益曲线（薄荷绿折线）|
| `_design/galaxy_live/bu-2b-menu-expanded.png` | 智能跟单子菜单展开状态（交易员广场 / 交易所自选 / 币 Coin 自选 / 持仓详情）|
| `_design/galaxy_live/bu-3-traders-plaza.png` (+ `-full.png`) | `/trader` 交易员广场：橙色警示 banner + 交易所 chip 过滤 + 4 列卡片（每张含小型 sparkline + 总收益% + 跟单按钮）|
| `_design/galaxy_live/bu-3-positions.png` (+ `-full.png`) | `/position` 持仓详情：账户下拉 + 服务时长 + 内嵌 tabs（持仓列表 / 操作记录 / 跟单分析）+ 9 列表头表格 + 「暂无数据」+ 多/空 pill |
| `_design/galaxy_live/bu-3-exchange-watchlist.png` | `/documentary` 交易所自选 |
| `_design/galaxy_live/bu-3-coin-watchlist.png` | `/thirdPartyDocumentary` 币 Coin 自选 |
| `_design/galaxy_live/bu-4-system.png` (+ `-full.png`) | `/set` 系统控制：语言设置 / 通知渠道（微信/Telegram/QQ邮箱/手机短信）/ 软件更新 |

---

## 🎨 色板（精确 hex，含来源）

| Token | Hex | 来源 |
| --- | --- | --- |
| 主色 mint | `#3ACBBE` | `index-BVhBjcNK.css` 中 `--el-color-primary: #3acbbe`、`.el-menu-item.is-active{background-color:#3acbbe}`，频次 40+ |
| 主色暗 mint-dark | `#23A599` | `linear-gradient(135deg,#23a599,#3acbbe)`（mobile-menu-header / 头像高亮）+ `.el-color-primary-dark-2: rgb(46,153,146)` 不同梯度，13 次 |
| 主色软 mint-soft（hover/选中底） | `#DEF6F4` | `--el-color-primary-light-9: rgb(222,246,244)` |
| 主色超浅 mint-tint | `#F9FFFF` | 持仓页多头 pill 内联 `background: rgb(249,255,255)` |
| 主色亮（active 描边） | `#62DAD2` | `--el-color-primary-light-3: rgb(98,218,210)` |
| 页面背景 | `#F8F9FA` | tokens.json body computed bg + Element Plus 默认 `--el-bg-color-page` 被该应用覆盖 |
| 卡片底 | `#FFFFFF` | `--el-bg-color: #ffffff`，所有卡片 inline `background-color: rgb(255,255,255)` |
| 文字主 | `#344054` | 频次 58；正文与表头主色 |
| 文字次 | `#606266` | `--el-text-color-regular: #606266` |
| 文字弱 | `#8B929C` | 持仓页内联 `color: rgb(139,146,156)` |
| 文字超弱 / placeholder | `#A8ABB2` | `--el-text-color-placeholder: #a8abb2` |
| 文字 disabled | `#C0C4CC` | `--el-text-color-disabled` |
| 边框 | `#DCDFE6` | `--el-border-color` |
| 边框浅 | `#E4E7ED` | `--el-border-color-light` |
| 边框更浅（表格行） | `#EBEEF5` | `--el-border-color-lighter` |
| 填充 / 表头底 | `#F5F7FA` | `--el-fill-color-light` |
| 跌色 / 空头 / danger | `#EB4A61` | bundle 内 `#eb4a61` 8 次（持仓多头之外的所有 pill 与百分比红字）|
| Element 默认 danger（备选） | `#F56C6C` | `--el-color-danger`，仅 toast/弹窗用 |
| 涨色 / 多头 / success | `#23A599` | 持仓多头 pill 文字色 `rgb(35,165,153)`；与主色暗共享 |
| Element 默认 success（图表/绿点） | `#67C23A` | `--el-color-success`，仅图表用 |
| 警告橙 / banner | `#FEF5EA` 底 + `#E6A23C` 文 | 交易员广场 inline `background: rgb(254,245,234)` + `--el-color-warning: #e6a23c` |
| 警告红 / banner alt | `#FEE` / `#F56C6C` | `el-alert--error is-light` Element Plus 默认变体 |
| SVIP 金（徽） | `#F4C45A → #E0A341` | 截图取色（topbar 右侧 SVIP 胶囊渐变；CSS 未独立暴露，按图片像素估算）|
| 链接蓝（IP 地址） | `#718EBF` | 持仓页 inline `color: rgb(113,142,191)`（el-link 默认覆盖）|
| 阴影 | `rgba(0,0,0,.04)` / `rgba(0,0,0,.08)` | `--el-box-shadow: 0px 12px 32px 4px rgba(0,0,0,.04),0px 8px 20px rgba(0,0,0,.08)` |

> 注：主色一族在 Element Plus 体系下生成 9 级浅化与 2 级深化，已全部以 light-3/5/7/8/9 / dark-2 形式列入 token CSS。
>
> 主色衍生（`galaxy-tokens.css` 暴露但来源同一族 Element Plus 计算）：
> - `#2E9992` — `--gq-mint-2` (`primary-dark-2`)
> - `#62DAD2` — `--gq-mint-3` (`primary-light-3`)
> - `#8BE3DD` — `--gq-mint-5` (`primary-light-5`)
> - `#B4ECE8` — `--gq-mint-7` (`primary-light-7`)
> - `#C9F1EE` — `--gq-mint-8` (`primary-light-8`)
>
> Element Plus 中性辅助：
> - `#F0F2F5` — `--el-fill-color`
> - `#FAFCFF` — `--el-fill-color-extra-light`

---

## ✍️ 字型

```
--gq-sans:    "Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB",
              "Microsoft YaHei", "微软雅黑", Arial, sans-serif;
--gq-display: "Songti SC", "STSong", "Noto Serif SC", "PingFang SC", serif;
--gq-mono:    "SF Mono", ui-monospace, "JetBrains Mono", "Menlo",
              "PingFang SC", monospace;
```

来源：`--el-font-family` 直接来自 bundle；display 仅供 logo / 重点页面标题（Songti / 思源宋）。**不要使用 Inter / Roboto / Poppins**——银河整站没有 Latin webfont。

字号梯度（从 `--el-font-size-*` 实测）：
- `--gq-text-xl: 20px`（页面 H1）
- `--gq-text-lg: 18px`（卡片 H2）
- `--gq-text-md: 16px`（KPI 数字 / section 标题）
- `--gq-text-base: 14px`（正文 / 表格）
- `--gq-text-sm: 13px`（卡片副本）
- `--gq-text-xs: 12px`（页脚 / 次说明 / 单位 USDT）

字重：标题 500，正文 400，强调 600（Element Plus `--el-font-weight-primary: 500`）。

---

## 📐 间距 · 圆角 · 阴影 · 几何

| Token | 值 | 来源 |
| --- | --- | --- |
| 顶栏高 | `60px` | `--el-header-height: 60px`（覆盖默认） |
| 顶栏左右 padding | `0 36px 0 50px` | bundle scoped |
| Sidebar 宽 | `245px` | bundle `aside{width:245px!important}` |
| Sidebar 菜单项 radius | `12px` | `[data-v-42f0e8c9] .el-menu-item{border-radius:12px;margin-bottom:10px}` |
| 卡片 radius | `8px` | bundle 内 `border-radius:8px` 出现 10 次（最高频）|
| 按钮 radius | `4px` | `--el-border-radius-base` 默认 4，频次 9 |
| 输入框 radius | `4px` | 同上 |
| 大胶囊 / 状态 pill radius | `2px` 或 `4px` | 持仓多/空 pill；交易员卡片标签使用 `4px` |
| Active 圆角填充菜单项 | `12px` | 同 sidebar 菜单 |
| 卡片内 padding | `20px` | inline 实测 |
| 表格行高 | `≈ 44–48px` | 按 row-padding 12 + line-height 24 推算 |
| 卡片阴影 | `0 1px 2px rgba(0,0,0,.04)` 极轻 + 大幅 hover `0 12px 32px rgba(0,0,0,.04), 0 8px 20px rgba(0,0,0,.08)` | `--el-box-shadow` |
| 主按钮 hover 阴影 | `0 4px 16px rgba(35,165,153,.3)` | bundle scoped |

---

## 🧱 组件签名

### Topbar（白底）
- 高 60px，纯白底，无下边框，仅靠下方内容偏移产生分隔。
- 左：仅显示当前 user greeting（"Hello Maietry"）。
- 右：⚙️ 设置图标（薄荷描边 svg） · 🔔 通知 · `SVIP` 金色胶囊（左侧钻石 svg 图标，渐变金底） · 积分 chip（白底 + 圆形头像 + 文字「积分：0」）。
- Logo 实际**位于 sidebar 顶部**而不是 topbar；sidebar 上沿与 topbar 顶部齐平。

### Sidebar（245px / 白底）
- 顶部：白底 + Logo（圆形 mint marker + 中英双语衬体字）。
- 列表项默认：透明底 / 文字 #344054 / 16px line svg 图标。
- 列表项 active：薄荷绿底 `#3ACBBE` 填充 + 圆角 12 + 文字白 + 图标白。
- 一级菜单上方有小号灰色 group title（"智能跟单"等）位于菜单组上方，11–12px。
- 子菜单展开后向右无缩进显示，但子项无图标、靠 group title 区隔。
- 底部固定：⚙️ "系统控制"，使用 active 同款 mint 高亮当 `/set` 路由命中。

### KPI 卡（4 列）
- 白底 / radius 8 / shadow ≈ 0 / inner padding ≈ 20px。
- 左：上「标签」中灰 13px → 下「数值」#344054 22–26px 加粗 + 单位灰 12px。
- 右：方形 mint-soft 圆角 6 块 + 内嵌薄荷线性 svg 图标。

### 顶部胶囊 Tabs（账户管理用）
- 形态：胶囊 radius 4 / 高 28–32px / 间距 8px。
- 默认：`#F2F6FC` 浅灰底 + `#606266` 文字 + 末尾 `el-link` 铅笔图标。
- Active：薄荷绿 `#3ACBBE` 底 + 白字 + 浅描边 `#62DAD2`。

### 内嵌 Tabs（持仓页用）
- 形态：方块 radius `8px 8px 0 0`（仅顶部圆角）/ 紧贴表格上沿。
- 默认：白底 + 灰描边 + `#606266` 文字 + 弱投影。
- Active：mint-soft `#DEF6F4` 底 + `#23A599` 加粗文字 + 与表格之间无边框（视觉拼接）。

### 数据表
- 表头：底 `#F5F7FA` + 列名 `#3ACBBE` 或 `#23A599` 加粗 14px + 排序箭头 `el-icon-caret`。
- 行：白底 + 行底边 `#EBEEF5` + hover 行 `#F5F7FA`。
- 单元字号 14px / `#344054`。
- 空状态：「暂无数据」`#909399` 居中 + 上下 padding 32–48px，无 illustration。

### 涨/跌 / 多/空 状态 pill
- 多头 / 涨：底 `#F9FFFF` + 字 `#23A599` + radius 2 + padding `2px 8px` + 文字 12px。
- 空头 / 跌：底 `#FEEAE0`（推断自 `--el-color-danger-light-9` 的 `rgb(254,240,240)` ≈ `#FEF0F0`）+ 字 `#EB4A61`。

### 按钮
- 主按钮：`#3ACBBE` 底 / 白字 / radius 4 / padding `8px 16px` / 字 14px / hover `#23A599` + 极轻 mint 阴影。
- Ghost：白底 / `#DCDFE6` 边 / `#344054` 字 / hover 边变 `#62DAD2`、字变 `#3ACBBE`。
- 危险：`#EB4A61` 底 / 白字（"删除当前账户"）。
- 圆角 icon-only：32×32 / radius 4 / hover mint-soft。

### 输入 / 下拉
- 高 36–40 / 白底 / `#DCDFE6` 1px 边 / radius 4 / focus 边变 `#3ACBBE` 1px。
- 占位 `#A8ABB2`，正常文字 `#344054`。

### 开关 (`el-switch`)
- iOS 样式 / 关闭灰 `#DCDFE6` / 开启薄荷 `#3ACBBE` / 滑块白 + 极轻投影。

### SVIP 徽章
- 渐变金 `linear-gradient(90deg,#F4C45A,#E0A341)` / radius 999 / inset white border / 字白 12px 600。
- 左侧钻石 svg（不要用 emoji）。

### 警示 banner（交易员广场顶部）
- 底 `#FEF5EA` + 文字 `#E6A23C` + radius 8 + padding `12px 16px` + 左侧 ⚠️ 线性 svg + 右上 × 关闭 svg。
- 是 Element Plus `el-alert--error is-light`，但实际使用 warning 色（语义被覆盖）。

### 行情条 / 数据指标卡（dashboard 下半）
- 上行：`BTC报价` 标签薄荷底 mini chip + 价格红字 + 涨跌% pill + 进度条（线性渐变）+ "贪婪指数" 文字。
- 下方网格：6 个白底圆角小卡，每张「标题（mint）+ 来源（ID 灰）+ 数值（粗大字）+ 备注 / 涨跌% pill」。

### 收益曲线（账户管理）
- 折线 stroke `#3ACBBE` 2px + 渐变 area fill `rgba(58,203,190,.18) → rgba(58,203,190,0)`。
- 网格线 `#EBEEF5`，轴文字 `#909399` 12px。

### Modal
- 白底 / radius 8 / 宽 480–560 / 顶部白底 padding 20 / 关闭 × `#A8ABB2` / 主按钮置右底。

---

## 🚫 反 slop 提醒

- **不要紫色渐变**（`#7a25da` 仅 mobile menu 装饰，不许进主线）。
- **不要 emoji 图标**：所有图标使用单色线性 svg（stroke 1.5–2px / size 16–20）。
- **不要给卡片加左 border accent**——银河没有这做法。
- **不要画 SVG 人脸**当 placeholder。
- **不要 Inter / Roboto / Poppins**——遵循中文优先 stack。
- **不要黑暗模式**——银河 console 仅 light。
- **不要给主按钮加大 box-shadow halo**（仅 hover 用 mint 4px alpha 阴影，绝不超过 16px blur）。
- **不要使用 `border-radius > 12`** 在内容卡——只有 pill / 头像 / SVIP 徽是 999。

---

## 🚷 禁区（与本仓库现有错误路线对照）

- 不沿用 `app/static/portal.css` 的深色 + 霓虹绿（那是早期错误路线）。
- 不沿用任何「赛博」「未来感」「科技蓝紫」装饰。
- 文字一律 sans，**只有 logo 与 page hero title** 允许 display 衬体。
- 不动 `admin.html` 的橙金主题——admin 与控制台分离，保留橙渐变以便管理员一眼区分。

---

## 🌬️ 气质关键词

整洁 · 薄荷感 · 轻量 · 工具向 · 数据密集而不拥挤 · 中文金融控制台 · Element Plus 风骨 · 信息层级靠灰阶不靠投影。

---

## 📦 实施清单（生成本 spec 时已交付）

- `_design/galaxy_live/brand-spec.md` — 本文档
- `app/static/galaxy-tokens.css` — CSS 变量 + 通用组件类（自包含，仅 link 即可用）
