/* ============================================================
   suan · Phase A 视觉戏剧化增强（运行时辅助函数）

   - 计算今日干支 + 节气 + 月相
   - 提供月相 SVG 渲染
   - 提供入场印章落下动画触发
   - 触发 cross_link / verdict / done 时的全屏闪光
   ============================================================ */

(function() {
  'use strict';

  // ── 干支表 ─────────────────────────────────────────────
  const TG = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
  const DZ = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];

  // ── 节气近似（按月份取最近的节气）──────────────────────
  // 真实节气日期每年浮动±2 天，这里用近似（足够展示）
  const SOLAR_TERMS_BY_DATE = [
    [1, 5, '小寒'], [1, 20, '大寒'],
    [2, 4, '立春'], [2, 19, '雨水'],
    [3, 5, '惊蛰'], [3, 20, '春分'],
    [4, 5, '清明'], [4, 20, '谷雨'],
    [5, 5, '立夏'], [5, 21, '小满'],
    [6, 5, '芒种'], [6, 21, '夏至'],
    [7, 7, '小暑'], [7, 23, '大暑'],
    [8, 7, '立秋'], [8, 23, '处暑'],
    [9, 7, '白露'], [9, 23, '秋分'],
    [10, 8, '寒露'], [10, 23, '霜降'],
    [11, 7, '立冬'], [11, 22, '小雪'],
    [12, 7, '大雪'], [12, 22, '冬至'],
  ];

  function currentSolarTerm(date) {
    const m = date.getMonth() + 1;
    const d = date.getDate();
    let last = '小寒';
    for (const [mm, dd, name] of SOLAR_TERMS_BY_DATE) {
      if (mm < m || (mm === m && dd <= d)) {
        last = name;
      } else {
        break;
      }
    }
    return last;
  }

  // 当日干支：1900-01-01 = 甲戌（idx 10）
  function todayGanzhi(date) {
    const anchor = new Date(1900, 0, 1).getTime();
    const days = Math.floor((date.getTime() - anchor) / 86400000);
    const idx = ((10 + days) % 60 + 60) % 60;
    return TG[idx % 10] + DZ[idx % 12];
  }

  // 当日年份干支（按立春边界粗略）
  function yearGanzhi(date) {
    let y = date.getFullYear();
    if (date.getMonth() === 0 || (date.getMonth() === 1 && date.getDate() < 4)) y -= 1;
    const idx = (y - 1984) % 60;
    const i = (idx + 60) % 60;
    return TG[i % 10] + DZ[i % 12];
  }

  // ── 月相计算（同会期 29.530589 天）─────────────────────
  function moonPhase(date) {
    // 已知 2000-01-06 18:14 UTC 为新月
    const knownNew = Date.UTC(2000, 0, 6, 18, 14, 0);
    const synodic = 29.530589 * 86400000;
    const since = (date.getTime() - knownNew) % synodic;
    const phase = (since + synodic) % synodic / synodic; // 0~1
    return phase;
  }

  function moonPhaseName(phase) {
    if (phase < 0.03 || phase > 0.97) return '新月';
    if (phase < 0.22) return '蛾眉月';
    if (phase < 0.28) return '上弦月';
    if (phase < 0.47) return '盈凸月';
    if (phase < 0.53) return '满月';
    if (phase < 0.72) return '亏凸月';
    if (phase < 0.78) return '下弦月';
    return '残月';
  }

  // 月相 SVG（一个圆，亮面用 path 画弧）
  function moonPhaseSvg(phase, size = 14) {
    // phase 0=新月 0.5=满月
    const r = size / 2;
    const cx = r, cy = r;
    // 朔望角（0~2π）
    const lit = phase < 0.5 ? phase * 2 : (1 - phase) * 2; // 0~1 亮面比例
    const waxing = phase < 0.5; // 上弦在前半，下弦在后半（盈→亏）

    // SVG 月相：基础底圆（暗面）+ 一个椭圆（用 path 形成 D 形或月牙）
    // 简化做法：椭圆 mask
    const xR = r * (1 - 2 * lit); // 椭圆短半轴（可负）
    const ellipseRx = Math.abs(xR);
    const dirSwitch = waxing ? (phase < 0.25 ? 1 : 0) : (phase > 0.75 ? 0 : 1);

    // 用 path：左/右半圆 + 椭圆弧
    const sweep1 = waxing ? 0 : 1;
    const sweep2 = phase < 0.5 ? (waxing ? 0 : 1) : (waxing ? 1 : 0);

    const path = (
      `M ${cx},${cy - r} ` +
      `A ${r},${r} 0 1 ${sweep1} ${cx},${cy + r} ` +
      `A ${ellipseRx},${r} 0 1 ${sweep2} ${cx},${cy - r} Z`
    );

    return (
      `<svg class="moon-glyph" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">` +
        `<circle cx="${cx}" cy="${cy}" r="${r}" fill="var(--paper-dark, #ede5d3)" stroke="var(--silver-grey, #a09b94)" stroke-width="0.4"/>` +
        `<path d="${path}" fill="var(--ink-soft, #2c2c2c)"/>` +
      `</svg>`
    );
  }

  // 农历日（粗略）：以 1900-01-31 为农历正月初一
  function lunarDay(date) {
    const ref = new Date(1900, 0, 31).getTime();
    const days = Math.floor((date.getTime() - ref) / 86400000);
    const synodic = 29.530589;
    const cur = days % synodic;
    return Math.floor(cur) + 1; // 1~30
  }
  function lunarDayChineseName(d) {
    const NAMES = ['初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
                    '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
                    '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'];
    return NAMES[(d - 1) % 30] || '初一';
  }

  // ── 渲染气象条 ─────────────────────────────────────────
  function renderWeatherRibbon(container) {
    if (!container) return;
    const now = new Date();
    const term = currentSolarTerm(now);
    const dayGZ = todayGanzhi(now);
    const yearGZ = yearGanzhi(now);
    const phase = moonPhase(now);
    const phName = moonPhaseName(phase);
    const lunDay = lunarDayChineseName(lunarDay(now));
    container.innerHTML = (
      `<span class="ribbon-jieqi">${term}时分</span>` +
      `<span class="ribbon-sep"></span>` +
      `<span>今日 <span class="ribbon-gz">${dayGZ}</span></span>` +
      `<span class="ribbon-sep"></span>` +
      `<span>${moonPhaseSvg(phase, 13)}<span style="margin-left:6px;">${phName} · ${lunDay}</span></span>` +
      `<span class="ribbon-sep"></span>` +
      `<span class="font-kai">${yearGZ}年</span>`
    );
  }

  // ── 全屏闪光（cross_link / verdict 来时）────────────────
  let flashEl = null;
  function flashOnce() {
    if (!flashEl) {
      flashEl = document.createElement('div');
      flashEl.className = 'flash-overlay';
      document.body.appendChild(flashEl);
    }
    flashEl.classList.remove('flash-trigger');
    void flashEl.offsetWidth; // reflow
    flashEl.classList.add('flash-trigger');
  }

  // ── 入场印章落下：仅本会话首次触发 ──────────────────────
  function trySealDrop(seal) {
    if (!seal) return;
    const KEY = 'suan.seal-dropped.v1';
    if (sessionStorage.getItem(KEY)) return;
    seal.classList.add('brand-seal-drop');
    sessionStorage.setItem(KEY, '1');
  }

  // ── 暴露 ──────────────────────────────────────────────
  window.SuanEnhance = {
    renderWeatherRibbon,
    moonPhaseSvg,
    todayGanzhi,
    yearGanzhi,
    currentSolarTerm,
    moonPhaseName,
    moonPhase,
    flashOnce,
    trySealDrop,
  };

  // 自动挂载 — DOM ready 后查 .weather-ribbon-auto / .brand-seal-auto
  function autoMount() {
    document.querySelectorAll('.weather-ribbon-auto').forEach(renderWeatherRibbon);
    document.querySelectorAll('.brand-seal-auto').forEach(trySealDrop);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoMount);
  } else {
    autoMount();
  }
})();
