# Badminton Studio Pro NLE UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Badminton Studio Web UI from an AI-themed/Codex-style dark hacker interface into an Apple Final Cut Pro / CapCut-inspired professional sports video editing workstation with Apple Pro Blue styling, clean system typography, and explicit icon+text paired controls.

**Architecture:** Single-file cohesive frontend in `scripts/ui/index.html` communicating via JSON REST endpoints with `scripts/codex_server.py`. Replaces design tokens, top navigation, 300px left inspector panel, video cinema viewport, transport trimming bar, multitrack timeline, and rally inspection grid.

**Tech Stack:** Native HTML5, Modern Vanilla CSS (Flexbox, CSS Grid, Custom Properties, SVGs), Vanilla ES6+ JavaScript, Python `http.server` backend.

## Global Constraints

- Retain 100% single-file cohesive architecture in `scripts/ui/index.html` (zero npm/build-chain dependencies).
- Eliminate all `#10a37f` / `#34d399` OpenAI emerald greens and glowing cyber gradients.
- Primary accent color must be Apple Pro Blue (`#0a84ff` in Dark, `#0071e3` in Light).
- Background palette must be Studio Slate Gray (`#16161a` / `#1e1e24` / `#26262d`), avoiding pitch-black `#0c0c0e`.
- Typography must default to Apple native system font `-apple-system, "PingFang SC"`, restricting monospace strictly to timecode numbers.
- Key interactive controls must feature paired SVG outline icons and explicit Chinese labels.

---

### Task 1: Create Automated Test Suite for Pro NLE UI Assets & Themes

**Files:**
- Create: `tests/test_ui_pro_nle.py`
- Test: `tests/test_ui_pro_nle.py`

**Interfaces:**
- Consumes: `scripts/ui/index.html`
- Produces: 5 automated unit test cases verifying design tokens, absence of AI green cliches, presence of Pro NLE mode cards, transport buttons, and theme variables.

- [ ] **Step 1: Write the failing tests in `tests/test_ui_pro_nle.py`**
- [ ] **Step 2: Run `python3 -m unittest tests/test_ui_pro_nle.py` and confirm failures against current UI**
- [ ] **Step 3: Commit initial test suite**

---

### Task 2: Implement Apple Pro Color Tokens & Native System Typography

**Files:**
- Modify: `scripts/ui/index.html:10-180`
- Test: `tests/test_ui_pro_nle.py`

**Interfaces:**
- Consumes: CSS `:root[data-theme="dark"]` and `:root[data-theme="light"]`
- Produces: Studio Slate Gray backgrounds (`#16161a`, `#1e1e24`, `#26262d`), Apple Pro Blue accents (`#0a84ff`, `#0071e3`), refined borders, and `-apple-system` font hierarchy.

- [ ] **Step 1: Update CSS root variables and global font settings**
- [ ] **Step 2: Replace cyber animations and neon gradient classes with Apple Pro focus rings and subtle translucent bevels**
- [ ] **Step 3: Run `python3 -m unittest tests/test_ui_pro_nle.py` and verify token tests pass**
- [ ] **Step 4: Commit token and typography updates**

---

### Task 3: Redesign Top Header & Left Media/Modes Inspector Panel

**Files:**
- Modify: `scripts/ui/index.html:890-985` (HTML) and matching CSS styles
- Test: `tests/test_ui_pro_nle.py`

**Interfaces:**
- Consumes: `MODES_META` in JS, Topbar brand header, Left sidebar container
- Produces: Professional studio title, human-readable summary stats, card-based 6-mode selector with icon + title + explanation, and large Apple Pro Blue export action button.

- [ ] **Step 1: Update Topbar markup with Pro branding and legible stat capsules**
- [ ] **Step 2: Rebuild Sidebar with video source card, card-style mode list, and bottom export console**
- [ ] **Step 3: Update `renderModes()` in JS to generate rich cards instead of 3x2 bare icon chips**
- [ ] **Step 4: Verify responsive layout in desktop resolutions**
- [ ] **Step 5: Commit topbar and sidebar redesign**

---

### Task 4: Redesign Video Stage, Transport Trimming Bar & Rally Inspection Grid

**Files:**
- Modify: `scripts/ui/index.html:985-1150` (HTML/CSS) and JS rendering routines
- Test: `tests/test_ui_pro_nle.py`

**Interfaces:**
- Consumes: `renderTimeline()`, `renderChips()`, video player element
- Produces: Professional cinema monitor, clear transport trimming bar with Chinese button labels (`[⏮ 上一拍]`, `[▶ 播放]`, `[⏭ 下一拍]`, `[起点微调]`, `[终点微调]`, `[✓ 保留本回合]`), NLE multitrack timeline, and game-tabbed rally cards.

- [ ] **Step 1: Update Transport & Trimming Bar markup with paired icon+text controls**
- [ ] **Step 2: Update Timeline track styling and cursor scrubber**
- [ ] **Step 3: Upgrade Rally Grid rendering to produce NLE rally cards (rally ID, timecode, duration, hit count, keep status)**
- [ ] **Step 4: Update Settings dialog to clean macOS dialog styling**
- [ ] **Step 5: Run full test suite `python3 -m unittest discover -s tests` and verify 100% pass**
- [ ] **Step 6: Commit complete UI redesign**

---

### Task 5: Live Verification & Server Restart

**Files:**
- Verify: `http://127.0.0.1:18765/`
- Test: Manual browser inspection & curl checks

**Interfaces:**
- Consumes: Running daemon `task-12600` on port 18765
- Produces: Restarted server with refreshed UI, verification screenshots/evidence.

- [ ] **Step 1: Restart `codex_server.py` on port 18765**
- [ ] **Step 2: Verify HTTP 200 and test API endpoints**
- [ ] **Step 3: Capture full-page screenshot of the redesigned Studio Pro UI**
- [ ] **Step 4: Report to user with clickable links and artifact screenshot**
