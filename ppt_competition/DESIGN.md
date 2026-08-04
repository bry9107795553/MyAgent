# DESIGN.md — MyAgent Competition Deck

## 1. Style match

**Trigger evaluation**:
- Domain keywords: "AI agent platform / AMD Radeon GPU / hackathon / Track 2 / inference optimization / privacy-first / local-only inference".
- Audience: AMD technical judges + product reviewers.
- Verdict: Not a match for academic / consulting / redgold presets. → **General design path**.
- Locked tone: **硬核技术 / 数据驱动 / 极简克制** → dark theme + monospace-flavored typography + accent pop from AMD red on otherwise cool palette.

## 2. Canvas & global master

| Region | Vertical px | Height | Contents |
|--------|------------:|-------:|----------|
| A · Title block | 0–120 | 120 | Page title 32–40px bold (left-aligned) + L3 brand badge top-right |
| B · Content | 120–660 | 540 | Primary payload |
| C · Footer | 660–720 | 60 | Project name left, slide number right, monospace 12px |

- Page padding: top 20 / bottom 20 / left 60 / right 60.
- Canvas: 1280 × 720 (16:9).
- Cover (01) and ending (10) use custom full-bleed layouts without the strict A/B/C split.

## 3. Color system (5 hex max)

| Role | Hex | Used for |
|------|-----|----------|
| Background (deepest) | `#0B1220` | Page background, B & C region |
| Background (panel) | `#111827` | Cards / panels (slightly raised) |
| Border / Divider | `#1F2937` | 1px hairlines, dividers |
| Primary brand (AMD red) | `#ED1C24` | Accents, hero highlights, key numbers |
| Secondary (cyan / data) | `#06B6D4` | Data points, callouts, structural emphasis |
| Text (foreground) | `#E5E7EB` | Default text |
| Text (muted) | `#94A3B8` | Subtitles, footnotes |

(Locked ≤ 4 brand colors per the design rule, expanded slightly to support both AMD red and cyan for data viz. Used as a 5-color extended system but visually reads as 3: red / cyan / gray-scale.)

### Color area allocation per page role

| Page role | Background % | Brand red % | Cyan % | Neutral text % |
|-----------|-------------:|------------:|-------:|---------------:|
| Hero (peak) | 50% | 15–20% | 5% | 25–30% |
| Supporting | 65% | ≤5% | 10% | 20–25% |
| Cover / Ending | 60% | 25% | 5% | 10% |

### Gradients

| Usage | Definition |
|-------|------------|
| Cover backdrop | `linear-gradient(135deg, #0B1220 0%, #1E293B 60%, #0B1220 100%)` with a faint radial AMD-red glow at top-right |
| Hero number callout | `linear-gradient(135deg, #ED1C24 0%, #F97316 100%)` text via `backgroundClip: text` |
| Section divider on hero pages | `linear-gradient(90deg, #ED1C24 0%, transparent 100%)` 3px line |
| Card panel | solid `#111827` with 1px `#1F2937` border (no gradient on cards — flat reads cleaner) |

## 4. Typography stack

| Tier | Size px | Weight | Line-height | Family |
|------|--------:|-------:|------------:|--------|
| Cover hero | 72 | bold | 1.0 | 'Space Grotesk', 'Inter', sans-serif |
| Hero H1 (page title) | 38–44 | bold | 1.15 | 'Inter', 'PingFang SC', sans-serif |
| Section H2 | 28–32 | 600 / bold | 1.25 | 'Inter', 'PingFang SC' |
| Hero number (anchor) | 96–140 | bold | 1.0 | 'Space Grotesk', monospace numeric |
| Body | 18 | regular | 1.55 | 'Inter' |
| Body emphasis | 18 | 600 | 1.55 | 'Inter' |
| Footer / page number | 12 | regular | 1.0 | 'JetBrains Mono', monospace |
| Code / token | 14 | 500 | 1.4 | 'JetBrains Mono' |

All English-only text — no CJK fallback needed, but `PingFang SC` stays as fallback for any legacy embed.

## 5. Page mapping table

| # | File | Type | Role | Layout | L1 | 字数 | 留白% | Color allocation | Key constraint |
|---|------|------|------|--------|----|----:|------:|------------------|----------------|
| 01 | `slide_01_cover.jsx` | cover | hero | 全屏视觉+骑线文字 | — | 30 | 45% | Red 25% / Cyan 5% / Bg 60% | AMD badge top-right; title centered vertically |
| 02 | `slide_02_catalog.jsx` | catalog | supporting | 左标题+右图文 | — | 130 | 25% | Red ≤5% / Cyan 10% / Bg 65% | Each chapter ≥30 chars |
| 03 | `slide_03_problem.jsx` | content | hero | 巨型数字+洞察 | — | 165 | 28% | Red 18% / Cyan 5% / Bg 60% | ≥48px anchor number on each pain point |
| 04 | `slide_04_architecture.jsx` | content | hero | 左大图+右侧文字 | `architecture.png` | 220 | 22% | Red 12% / Cyan 8% / Bg 60% | L1 fills left 60%, caption text overlay 40% |
| 05 | `slide_05_capabilities.jsx` | content | supporting | 上大图+下方卡片 (5-card grid) | — | 280 | 25% | Red ≤5% / Cyan 12% / Bg 65% | 5 icons + 5 names + 5 short descriptions |
| 06 | `slide_06_memory.jsx` | content | hero | 上大图+下方卡片 (4-tier layout) | L2 SVG memory diagram | 240 | 20% | Red 14% / Cyan 12% / Bg 60% | Must show ≤−3 eviction rule visually |
| 07 | `slide_07_prompt_slim.jsx` | content | hero | 巨型数字+洞察 + 表格锚点 | — | 200 | 22% | Red 16% / Cyan 6% / Bg 60% | Top-left number ≥96px; table 18 rows but summarized compactly |
| 08 | `slide_08_amd_deploy.jsx` | content | supporting | 非对称双栏 (60:40) | — | 220 | 25% | Red ≤5% / Cyan 15% / Bg 65% | Show PENDING data placeholder, no fabrication |
| 09 | `slide_09_demo.jsx` | content | supporting | 上大图+下方卡片 (chain diagram) | L2 SVG dev_full chain | 230 | 22% | Red ≤5% / Cyan 18% / Bg 65% | 7-role relay visualizable on one screen |
| 10 | `slide_10_ending.jsx` | ending | hero | 居中金句/大字 | — | 30 | 50% | Red 25% / Cyan 5% / Bg 60% | Title centered, subtitle small below |

## 6. Image inventory

| File | Level | Source | Page | Status |
|------|-------|--------|------|--------|
| `architecture.png` | L1 | Material (already on disk) | 04 | ✅ Read & verified |
| memory-4tier SVG | L2 | Inline `<SVG>` (this deck, page 06) | 06 | ✅ Custom-built |
| dev_full chain SVG | L2 | Inline `<SVG>` (this deck, page 09) | 09 | ✅ Custom-built |

No ImageGen needed — `architecture.png` is a user-supplied, dense, well-sized material asset. The two SVG diagrams cover the structural visualization needs (memory tiers, pipeline chain). All other visuals are typographic or icon-based.

## 7. Density & self-check targets

| Metric | Target |
|--------|--------|
| Hero page whitespace | ≤ 45% (cover/ending up to 50%) |
| Supporting page whitespace | ≤ 30% |
| At least one ≥ 48px visual anchor per hero page | Mandatory |
| At least one ≥ 96px anchor number on hero pages 03 + 07 | Mandatory |
| Footer page numbers on every page | Mandatory |
| Color palette strict per page | ≤ 4 functional hex |
| Layout variety, no 2x symmetric in a row | Enforced (only cover + ending are symmetric) |
| No fabricated benchmark numbers | Strict — Page 08 marks PENDING |
