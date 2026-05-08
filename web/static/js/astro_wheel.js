/* ============================================================
   suan · 中西命理 AI Agent
   astro_wheel.js — 占星本命盘圆轮 SVG 渲染器（纯原生）
   ------------------------------------------------------------
   设计原则：
   - 纯 SVG / 原生 DOM API，零外部依赖；可以塞到任何 <svg> 容器
   - 视觉：3 圆环（宫位 / 星座扇区 / 行星 + 中心算印）
   - 占星标准：ASC 在 9 点钟（左侧）方向；黄道**逆时针**增长
   - 行星位置按真实黄经；冲突 < 6° 时 fan-out 防重叠
   - 5 类相位线、上升/天顶轴线、宫位线、月相微标，俱全
   - 配色：墨黑 / 宣纸 / 朱砂 / 黛青 / 翠玉 / 鎏金
   - hover / click 交互 + tooltip + CustomEvent 派发
   ============================================================ */
(function () {
  'use strict';

  // ────────────────────────────────────────────────────────────
  // 常量：占星符号、配色
  // ────────────────────────────────────────────────────────────
  // 12 黄道 — 中文名 → Unicode 占星符号
  const SIGN_GLYPH = {
    '白羊座':'♈','金牛座':'♉','双子座':'♊','巨蟹座':'♋',
    '狮子座':'♌','处女座':'♍','天秤座':'♎','天蝎座':'♏',
    '射手座':'♐','摩羯座':'♑','水瓶座':'♒','双鱼座':'♓',
  };
  // 中文星座名（按黄经 0° 开始的 12 顺序）
  const SIGNS_ORDER = [
    '白羊座','金牛座','双子座','巨蟹座','狮子座','处女座',
    '天秤座','天蝎座','射手座','摩羯座','水瓶座','双鱼座',
  ];
  // 星座二字简写（圆环狭窄时用）
  const SIGN_SHORT = {
    '白羊座':'白羊','金牛座':'金牛','双子座':'双子','巨蟹座':'巨蟹',
    '狮子座':'狮子','处女座':'处女','天秤座':'天秤','天蝎座':'天蝎',
    '射手座':'射手','摩羯座':'摩羯','水瓶座':'水瓶','双鱼座':'双鱼',
  };
  // 元素配色（淡背景）
  const SIGN_ELEMENT = {
    '白羊座':'fire','狮子座':'fire','射手座':'fire',
    '金牛座':'earth','处女座':'earth','摩羯座':'earth',
    '双子座':'air','天秤座':'air','水瓶座':'air',
    '巨蟹座':'water','天蝎座':'water','双鱼座':'water',
  };
  const ELEMENT_FILL = {
    fire:  'rgba(200, 64, 60, 0.05)',
    earth: 'rgba(184,153,104, 0.05)',
    air:   'rgba(74, 102,112, 0.04)',
    water: 'rgba(93, 124,106, 0.05)',
  };
  const ELEMENT_TINT = {
    fire:'#c8403c', earth:'#b89968', air:'#4a6670', water:'#5d7c6a',
  };

  // 行星 → Unicode + 中文 + 配色
  const PLANET_DEF = {
    sun:        { glyph:'☉', cn:'太阳', color:'#c8403c' },
    moon:       { glyph:'☽', cn:'月亮', color:'#4a6670' },
    mercury:    { glyph:'☿', cn:'水星', color:'#8a8c8e' },
    venus:      { glyph:'♀', cn:'金星', color:'#b89968' },
    mars:       { glyph:'♂', cn:'火星', color:'#9c2f2c' },
    jupiter:    { glyph:'♃', cn:'木星', color:'#5d7c6a' },
    saturn:     { glyph:'♄', cn:'土星', color:'#2c2c2c' },
    uranus:     { glyph:'⛢', cn:'天王星', color:'#4a6670' },
    neptune:    { glyph:'♆', cn:'海王星', color:'#5d7c6a' },
    pluto:      { glyph:'♇', cn:'冥王星', color:'#1a1a1a' },
    north_node: { glyph:'☊', cn:'北交点', color:'#b89968' },
    south_node: { glyph:'☋', cn:'南交点', color:'#a09b94' },
    chiron:     { glyph:'⚷', cn:'凯龙', color:'#8d7449' },
  };

  // 5 大相位（后端键 → 显示与配色）
  // 同时支持中文和英文键
  const ASPECT_DEF = {
    conjunction: { cn:'合', deg:0,   color:'#a09b94', dash:'2 3', width:0.6 },
    sextile:     { cn:'六合', deg:60, color:'#4a6670', dash:null,  width:0.7 },
    square:      { cn:'四分相', deg:90, color:'#c8403c', dash:'4 3', width:1.0 },
    trine:       { cn:'三分相', deg:120,color:'#5d7c6a', dash:null,  width:1.0 },
    opposition:  { cn:'对分相', deg:180,color:'#4a6670', dash:'8 3', width:1.2 },
  };
  const ASPECT_KEY_BY_CN = {
    '合':'conjunction','六合':'sextile','四分相':'square','三分相':'trine','对分相':'opposition',
  };

  // 罗马数字 1..12
  const ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

  // 中文宫位名（参考性）
  const HOUSE_CN = ['命宫','财帛','兄弟','田宅','子女','奴仆','夫妻','疾厄','迁移','官禄','福德','父母'];

  // SVG 命名空间
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // ────────────────────────────────────────────────────────────
  // 工具：度数 → 屏幕坐标
  // ────────────────────────────────────────────────────────────
  // 占星标准：ASC 在 9 点钟方向（屏幕左侧），黄经逆时针增长。
  // SVG 角度：0° 在 +x（右），顺时针为正；这里用三角函数（数学约定）
  // 我们采用：屏幕角 θ（rad），点 = (cx + r*cos θ, cy - r*sin θ)
  // 因为 SVG 的 y 轴向下，取负 sin 让 +y 指上 → 90° 即 12 点钟方向。
  // 占星黄经 lon（0-360）相对于 ASC 的角差 = lon - ascLon（逆时针）
  // 想要 lon=ascLon 落在屏幕 180° (9 点钟) → screenAngle = 180 + (lon-ascLon)
  function lonToAngleRad(lon, ascLon) {
    const a = (180 + (lon - ascLon)) * Math.PI / 180;
    return a;
  }
  function lonToXY(lon, ascLon, r, cx, cy) {
    const a = lonToAngleRad(lon, ascLon);
    return { x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) };
  }
  function angDeg(lon, ascLon) {
    // 屏幕实际角（度，用于绘制弧路径）
    return 180 + (lon - ascLon);
  }
  function norm360(x) { x = x % 360; if (x < 0) x += 360; return x; }

  // 圆弧 path（SVG 大弧 / 短弧）—— 用于宫位 / 星座扇区填色
  function arcPath(cx, cy, rOuter, rInner, startLon, endLon, ascLon) {
    // 顺着黄经从 start 到 end 顺时针（黄经递增）；屏幕上呈逆时针
    const a1 = lonToAngleRad(startLon, ascLon);
    const a2 = lonToAngleRad(endLon, ascLon);
    const x1Out = cx + rOuter * Math.cos(a1), y1Out = cy - rOuter * Math.sin(a1);
    const x2Out = cx + rOuter * Math.cos(a2), y2Out = cy - rOuter * Math.sin(a2);
    const x1In  = cx + rInner * Math.cos(a1), y1In  = cy - rInner * Math.sin(a1);
    const x2In  = cx + rInner * Math.cos(a2), y2In  = cy - rInner * Math.sin(a2);
    // 弧度差（黄经 → 屏幕角；屏幕上"逆时针"是负方向，所以 sweep 反一下）
    let dlon = (endLon - startLon);
    dlon = ((dlon % 360) + 360) % 360;
    const largeArc = dlon > 180 ? 1 : 0;
    // SVG sweep=0 表示 counter-clockwise（屏幕坐标系），等价于黄经递增方向
    const sweepOuter = 0;
    const sweepInner = 1;
    return [
      `M ${x1Out.toFixed(2)} ${y1Out.toFixed(2)}`,
      `A ${rOuter} ${rOuter} 0 ${largeArc} ${sweepOuter} ${x2Out.toFixed(2)} ${y2Out.toFixed(2)}`,
      `L ${x2In.toFixed(2)} ${y2In.toFixed(2)}`,
      `A ${rInner} ${rInner} 0 ${largeArc} ${sweepInner} ${x1In.toFixed(2)} ${y1In.toFixed(2)}`,
      'Z',
    ].join(' ');
  }

  // ────────────────────────────────────────────────────────────
  // SVG 元素工厂
  // ────────────────────────────────────────────────────────────
  function el(name, attrs, parent) {
    const e = document.createElementNS(SVG_NS, name);
    if (attrs) {
      for (const k in attrs) {
        if (attrs[k] === null || attrs[k] === undefined) continue;
        e.setAttribute(k, attrs[k]);
      }
    }
    if (parent) parent.appendChild(e);
    return e;
  }
  function group(parent, cls) {
    return el('g', cls ? { class: cls } : null, parent);
  }

  // ────────────────────────────────────────────────────────────
  // CSS 注入（一次性）
  // ────────────────────────────────────────────────────────────
  let CSS_INJECTED = false;
  function ensureStyles() {
    if (CSS_INJECTED) return;
    CSS_INJECTED = true;
    // 优先尝试链接已经放在文档里的 astro_wheel.css；否则把简版样式塞 <style>
    if (document.querySelector('link[href*="astro_wheel.css"]') ||
        document.querySelector('style[data-suan-astro]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/js/astro_wheel.css';
    link.setAttribute('data-suan-astro', '1');
    document.head.appendChild(link);
  }

  // ────────────────────────────────────────────────────────────
  // fan-out 防重叠：把太挤的行星组沿黄经"摊开"
  // 输入：[{name, lon, ...}]，已按 lon 升序
  // 输出：在每个 obj 上加 displayLon（用于绘制中环上的小标记）
  // 算法：把任意两两距离 < threshold 的连成一组；组内均匀分布。
  // ────────────────────────────────────────────────────────────
  function fanOutPlanets(items, threshold) {
    if (!items.length) return;
    // 默认所有人 displayLon = lon
    items.forEach(it => { it.displayLon = it.lon; });
    if (items.length < 2) return;

    // 由于 lon 是环形，先按 lon 排序，再尝试把首尾跨 0 的处理掉
    items.sort((a, b) => a.lon - b.lon);

    // 分组：相邻 < threshold 归一组
    const groups = [];
    let cur = [items[0]];
    for (let i = 1; i < items.length; i++) {
      const prev = items[i - 1];
      const it = items[i];
      const gap = it.lon - prev.lon;
      if (gap < threshold) cur.push(it);
      else { groups.push(cur); cur = [it]; }
    }
    groups.push(cur);

    // 跨 0° 的合并：第一组首与最后一组尾
    if (groups.length > 1) {
      const first = groups[0];
      const last = groups[groups.length - 1];
      const wrapGap = (first[0].lon + 360) - last[last.length - 1].lon;
      if (wrapGap < threshold) {
        // 合并成一个跨 0° 的组：把 last 的元素 lon 视作 - (360 - lon)
        // 为了重排，给每个 last 元素一个临时 wrappedLon
        last.forEach(it => { it._wrappedLon = it.lon - 360; });
        const merged = last.concat(first);
        merged.sort((a, b) => (a._wrappedLon ?? a.lon) - (b._wrappedLon ?? b.lon));
        groups.length = 0;
        groups.push(merged);
        // 还原其它组（这里只剩一个）
      }
    }

    // 每组打散
    for (const grp of groups) {
      if (grp.length < 2) {
        if (grp[0]) grp[0].displayLon = grp[0]._wrappedLon ?? grp[0].lon;
        continue;
      }
      const N = grp.length;
      const step = Math.max(threshold, threshold * 0.95);
      const total = step * (N - 1);
      // 中心是组内平均 lon（用 wrapped lon 计算时把负值留给后面 norm360）
      const lons = grp.map(it => it._wrappedLon ?? it.lon);
      const center = lons.reduce((a,b)=>a+b,0) / N;
      grp.forEach((it, i) => {
        const dl = -total/2 + i * step;
        it.displayLon = norm360(center + dl);
      });
    }
  }

  // ────────────────────────────────────────────────────────────
  // 主渲染入口
  // ────────────────────────────────────────────────────────────
  /**
   * @param {SVGElement} svgEl
   * @param {Object} chart - AstroNatalChart JSON
   * @param {Object} opts
   */
  function render(svgEl, chart, opts) {
    if (!svgEl || !chart) return;
    opts = opts || {};
    const size = opts.size || 600;
    const showAspects = opts.showAspects !== false;
    const showHouses = opts.showHouses !== false;

    ensureStyles();

    // 清空 svg
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);

    // viewBox 让外面随意缩放
    svgEl.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svgEl.setAttribute('class', (svgEl.getAttribute('class') || '') + ' suan-astro-wheel');
    svgEl.setAttribute('xmlns', SVG_NS);

    // ── 几何参数（基于 size） ────────────────────────────────
    const cx = size / 2;
    const cy = size / 2;
    const rOuter   = size * 0.495;   // 最外圈 — 不用画整圆，留一点边
    const rHouse   = size * 0.470;   // 宫位环外
    const rZodiac  = size * 0.420;   // 星座扇区外
    const rZodiacI = size * 0.350;   // 星座扇区内（=行星标记环）
    const rTick    = size * 0.345;   // 小度数刻度环外
    const rPlanet  = size * 0.295;   // 行星 glyph 落点环
    const rInnerCircle = size * 0.165; // 中心圆
    const rSeal    = size * 0.085;   // 中心朱砂印章半径

    // ASC / MC / DSC / IC（必须存在）
    const angles = chart.angles || {};
    const ascLon = (angles.ASC ?? 0);
    const mcLon  = (angles.MC  ?? norm360(ascLon - 90));
    const dscLon = (angles.DSC ?? norm360(ascLon + 180));
    const icLon  = (angles.IC  ?? norm360(mcLon + 180));

    // 房宫边界
    const houses = chart.houses || [];
    const houseCusps = houses.length === 12
      ? houses.map(h => h.cusp_longitude || 0)
      : Array.from({length:12}, (_, i) => norm360(ascLon + i * 30));

    // 行星
    const planets = chart.planets || {};
    const aspects = chart.aspects || [];

    // ── defs：渐变 / 阴影 ─────────────────────────────────────
    const defs = el('defs', null, svgEl);
    // 中心印章径向渐变
    const radial = el('radialGradient', { id: 'suan-seal-grad', cx:'50%', cy:'50%', r:'50%' }, defs);
    el('stop', { offset:'0%',  'stop-color':'#c8403c', 'stop-opacity':'0.92' }, radial);
    el('stop', { offset:'100%','stop-color':'#9c2f2c', 'stop-opacity':'1.00' }, radial);

    // 行星圆点的微光晕
    const filter = el('filter', { id:'suan-glyph-soft', x:'-30%', y:'-30%', width:'160%', height:'160%' }, defs);
    el('feGaussianBlur', { in:'SourceAlpha', stdDeviation:'0.6', result:'blur' }, filter);
    el('feOffset', { in:'blur', dx:'0', dy:'0.3', result:'offsetBlur' }, filter);
    const merge = el('feMerge', null, filter);
    el('feMergeNode', { in:'offsetBlur' }, merge);
    el('feMergeNode', { in:'SourceGraphic' }, merge);

    // ── 背景 paper（纸） ──────────────────────────────────────
    el('circle', {
      cx, cy, r: rOuter,
      fill: '#faf6f0',
      stroke: 'none',
      class: 'suan-aw-paper',
    }, svgEl);

    // ── 第 1 圈：宫位环（最外） ─────────────────────────────
    if (showHouses) {
      const gHouse = group(svgEl, 'suan-aw-houses');
      // 12 宫位扇区背景（极淡色，给数字垫底）
      for (let i = 0; i < 12; i++) {
        const start = houseCusps[i];
        const end = houseCusps[(i + 1) % 12];
        const path = arcPath(cx, cy, rHouse, rZodiac, start, end, ascLon);
        el('path', {
          d: path,
          fill: i % 2 === 0 ? 'rgba(26,26,26,0.012)' : 'transparent',
          stroke: 'none',
          class: 'suan-aw-house-bg',
          'data-house': i + 1,
        }, gHouse);
      }
      // 12 条宫位分界线
      for (let i = 0; i < 12; i++) {
        const lon = houseCusps[i];
        const inner = lonToXY(lon, ascLon, rZodiac, cx, cy);
        const outer = lonToXY(lon, ascLon, rHouse, cx, cy);
        // ASC / MC 用强朱砂色，其它用墨色淡
        const isASC = i === 0;
        const isMC  = i === 9;
        const cls = isASC ? 'suan-aw-cusp-asc' :
                   isMC  ? 'suan-aw-cusp-mc'  : 'suan-aw-cusp';
        el('line', {
          x1: inner.x, y1: inner.y, x2: outer.x, y2: outer.y, class: cls,
        }, gHouse);
      }
      // 罗马数字 — 放在每宫中段
      for (let i = 0; i < 12; i++) {
        const start = houseCusps[i];
        const end = houseCusps[(i + 1) % 12];
        let mid = (start + end) / 2;
        if (end < start) mid = norm360((start + end + 360) / 2);
        const p = lonToXY(mid, ascLon, (rHouse + rZodiac) / 2, cx, cy);
        el('text', {
          x: p.x, y: p.y, class: 'suan-aw-house-num',
          'text-anchor':'middle', 'dominant-baseline':'middle',
        }, gHouse).textContent = ROMAN[i];
      }
    }

    // ── 第 2 圈：12 星座扇区 ───────────────────────────────
    const gZodiac = group(svgEl, 'suan-aw-zodiac');
    for (let i = 0; i < 12; i++) {
      const lonStart = i * 30;
      const lonEnd = (i + 1) * 30;
      const sign = SIGNS_ORDER[i];
      const elem = SIGN_ELEMENT[sign];
      const path = arcPath(cx, cy, rZodiac, rZodiacI, lonStart, lonEnd, ascLon);
      el('path', {
        d: path,
        fill: ELEMENT_FILL[elem] || 'transparent',
        stroke: 'none',
        class: 'suan-aw-sign-bg',
        'data-sign': sign,
        'data-elem': elem,
      }, gZodiac);
    }
    // 12 条星座分界（每 30°）
    for (let i = 0; i < 12; i++) {
      const lon = i * 30;
      const inner = lonToXY(lon, ascLon, rZodiacI, cx, cy);
      const outer = lonToXY(lon, ascLon, rZodiac, cx, cy);
      el('line', {
        x1: inner.x, y1: inner.y, x2: outer.x, y2: outer.y,
        class: 'suan-aw-sign-divider',
      }, gZodiac);
    }
    // 度数刻度（每 5°一短，10°一长）— 刻在最内的细环
    const gTick = group(svgEl, 'suan-aw-ticks');
    for (let d = 0; d < 360; d += 5) {
      const isLong = d % 30 === 0;
      const isMid = d % 10 === 0;
      const len = isLong ? 6 : (isMid ? 3.5 : 2);
      const inner = lonToXY(d, ascLon, rZodiacI, cx, cy);
      const outer = lonToXY(d, ascLon, rZodiacI - len, cx, cy);
      el('line', {
        x1: inner.x, y1: inner.y, x2: outer.x, y2: outer.y,
        class: isLong ? 'suan-aw-tick-long' : (isMid ? 'suan-aw-tick-mid' : 'suan-aw-tick'),
      }, gTick);
    }
    // 星座符号（Unicode glyph）+ 中文小注 — 居中在每段 30°
    for (let i = 0; i < 12; i++) {
      const lonMid = i * 30 + 15;
      const sign = SIGNS_ORDER[i];
      const glyph = SIGN_GLYPH[sign];
      const elem = SIGN_ELEMENT[sign];
      // glyph 大字
      const pGlyph = lonToXY(lonMid, ascLon, (rZodiac + rZodiacI) / 2 + 4, cx, cy);
      el('text', {
        x: pGlyph.x, y: pGlyph.y,
        class: 'suan-aw-sign-glyph',
        fill: ELEMENT_TINT[elem] || '#1a1a1a',
        'text-anchor':'middle', 'dominant-baseline':'middle',
        'data-sign': sign,
      }, gZodiac).textContent = glyph;
      // 中文短名
      const pTxt = lonToXY(lonMid, ascLon, (rZodiac + rZodiacI) / 2 - 12, cx, cy);
      el('text', {
        x: pTxt.x, y: pTxt.y,
        class: 'suan-aw-sign-txt',
        'text-anchor':'middle', 'dominant-baseline':'middle',
      }, gZodiac).textContent = SIGN_SHORT[sign] || sign;
    }

    // ── 第 3 圈：行星位置 ──────────────────────────────────
    // 准备行星条目
    const planetEntries = [];
    for (const key in planets) {
      const p = planets[key];
      if (!p || typeof p.longitude !== 'number') continue;
      const def = PLANET_DEF[key];
      if (!def) continue;  // 仅画已知行星
      planetEntries.push({
        key, name: def.cn, glyph: def.glyph, color: def.color,
        lon: p.longitude, sign: p.sign, signDeg: p.sign_degree,
        house: p.house, retro: !!p.retrograde, raw: p,
      });
    }
    // fan-out 防挤
    fanOutPlanets(planetEntries, 6.5);

    const gPlanet = group(svgEl, 'suan-aw-planets');

    // 中环上每行星的"实际位置短线"（始终在真实 lon），不偏移
    planetEntries.forEach(p => {
      const a1 = lonToXY(p.lon, ascLon, rZodiacI - 1, cx, cy);
      const a2 = lonToXY(p.lon, ascLon, rZodiacI - 14, cx, cy);
      el('line', {
        x1: a1.x, y1: a1.y, x2: a2.x, y2: a2.y,
        stroke: p.color, 'stroke-width':'1.2',
        class: 'suan-aw-planet-tick',
      }, gPlanet);
    });

    // 行星符号（在 displayLon 上，避免重叠）
    planetEntries.forEach(p => {
      const center = lonToXY(p.displayLon, ascLon, rPlanet, cx, cy);
      // 引线：从真实位置 → 显示位置（如果偏移）
      if (Math.abs(p.displayLon - p.lon) > 0.05) {
        const a = lonToXY(p.lon, ascLon, rZodiacI - 14, cx, cy);
        const b = lonToXY(p.displayLon, ascLon, rPlanet + 14, cx, cy);
        el('line', {
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          class: 'suan-aw-planet-leader',
        }, gPlanet);
      }
      // 行星组（hover 放大、click 派事件）
      const gP = el('g', {
        class: 'suan-aw-planet',
        'data-planet': p.key,
        transform: `translate(${center.x}, ${center.y})`,
      }, gPlanet);
      // 不可见的 hit area（更好 hover）
      el('circle', { cx:0, cy:0, r:14, fill:'transparent' }, gP);
      // 圆底（淡色）
      el('circle', {
        cx:0, cy:0, r: 11, fill:'#faf6f0', stroke: p.color,
        'stroke-width':'0.8', class:'suan-aw-planet-disc',
      }, gP);
      // 符号
      el('text', {
        x:0, y:0, fill: p.color, class: 'suan-aw-planet-glyph',
        'text-anchor':'middle','dominant-baseline':'central',
        filter:'url(#suan-glyph-soft)',
      }, gP).textContent = p.glyph;
      // 逆行 ℞ 微标
      if (p.retro) {
        el('text', {
          x: 9, y: -7, fill:'#c8403c', class:'suan-aw-retro',
          'text-anchor':'start', 'dominant-baseline':'middle',
        }, gP).textContent = '℞';
      }
      // tooltip 数据（用 JS 渲染时挂到元素上）
      gP.__suanTip = formatPlanetTip(p);
      // 交互
      gP.style.cursor = 'pointer';
      gP.addEventListener('mouseenter', (ev) => onPlanetHover(svgEl, gP, p, true));
      gP.addEventListener('mouseleave', (ev) => onPlanetHover(svgEl, gP, p, false));
      gP.addEventListener('click', (ev) => {
        const detail = { planet: p.key, name: p.name, sign: p.sign, sign_degree: p.signDeg, house: p.house, retro: p.retro, longitude: p.lon };
        svgEl.dispatchEvent(new CustomEvent('astro-planet-click', { detail, bubbles: true }));
      });
    });

    // ── 第 4 圈：相位线 ────────────────────────────────────
    // 用每颗行星的"真实位置"画从 rPlanet-12 → 对侧的连线
    if (showAspects && aspects.length) {
      const gAsp = group(svgEl, 'suan-aw-aspects');
      // 把名字到 lon 的映射先准备好（如果 aspects 引用 ASC / MC，也支持）
      const lonByName = {};
      planetEntries.forEach(p => { lonByName[p.key] = p.lon; });
      lonByName.ASC = ascLon;
      lonByName.MC = mcLon;
      lonByName.DSC = dscLon;
      lonByName.IC = icLon;

      aspects.forEach(asp => {
        const a = asp.planet_a, b = asp.planet_b;
        const lonA = lonByName[a], lonB = lonByName[b];
        if (typeof lonA !== 'number' || typeof lonB !== 'number') return;
        // 兼容中文/英文 aspect_type
        let key = asp.aspect_type;
        if (ASPECT_KEY_BY_CN[key]) key = ASPECT_KEY_BY_CN[key];
        const def = ASPECT_DEF[key];
        if (!def) return;
        // 端点：稍稍内缩到 rPlanet - 12，避免穿过 glyph 圆
        const rEnd = rPlanet - 14;
        const pA = lonToXY(lonA, ascLon, rEnd, cx, cy);
        const pB = lonToXY(lonB, ascLon, rEnd, cx, cy);
        el('line', {
          x1: pA.x, y1: pA.y, x2: pB.x, y2: pB.y,
          stroke: def.color,
          'stroke-width': def.width,
          'stroke-dasharray': def.dash || null,
          opacity: 0.55,
          class: 'suan-aw-aspect ' + 'suan-aw-aspect--' + key,
          'data-aspect': key,
          'data-orb': asp.orb,
        }, gAsp);
      });
    }

    // ── 第 5 圈：中心 — 内圈 + 月相微标 + 算印 ─────────────
    const gCenter = group(svgEl, 'suan-aw-center');
    // 内圈
    el('circle', {
      cx, cy, r: rInnerCircle,
      fill:'transparent', stroke:'#2c2c2c', 'stroke-width':'0.8',
      class:'suan-aw-inner-ring',
    }, gCenter);

    // ASC / DSC / MC / IC 轴线（穿过中心的对角线）
    // 主 ASC-DSC 用粗朱砂；MC-IC 用朱砂虚线
    const ascA = lonToXY(ascLon, ascLon, rZodiacI, cx, cy);
    const ascB = lonToXY(ascLon, ascLon, rInnerCircle, cx, cy);
    const dscA = lonToXY(dscLon, ascLon, rZodiacI, cx, cy);
    const dscB = lonToXY(dscLon, ascLon, rInnerCircle, cx, cy);
    el('line', { x1: ascA.x, y1: ascA.y, x2: ascB.x, y2: ascB.y, class:'suan-aw-axis-asc' }, gCenter);
    el('line', { x1: dscA.x, y1: dscA.y, x2: dscB.x, y2: dscB.y, class:'suan-aw-axis-asc' }, gCenter);
    const mcA = lonToXY(mcLon, ascLon, rZodiacI, cx, cy);
    const mcB = lonToXY(mcLon, ascLon, rInnerCircle, cx, cy);
    const icA = lonToXY(icLon, ascLon, rZodiacI, cx, cy);
    const icB = lonToXY(icLon, ascLon, rInnerCircle, cx, cy);
    el('line', { x1: mcA.x, y1: mcA.y, x2: mcB.x, y2: mcB.y, class:'suan-aw-axis-mc' }, gCenter);
    el('line', { x1: icA.x, y1: icA.y, x2: icB.x, y2: icB.y, class:'suan-aw-axis-mc' }, gCenter);

    // ASC / MC 角度文本
    const ascTxtPos = lonToXY(ascLon, ascLon, rZodiacI - 22, cx, cy);
    el('text', {
      x: ascTxtPos.x, y: ascTxtPos.y,
      class:'suan-aw-axis-label suan-aw-axis-label--asc',
      'text-anchor':'middle', 'dominant-baseline':'middle',
    }, gCenter).textContent = 'ASC';
    const mcTxtPos = lonToXY(mcLon, ascLon, rZodiacI - 22, cx, cy);
    el('text', {
      x: mcTxtPos.x, y: mcTxtPos.y,
      class:'suan-aw-axis-label suan-aw-axis-label--mc',
      'text-anchor':'middle', 'dominant-baseline':'middle',
    }, gCenter).textContent = 'MC';

    // 中心朱砂"算"字印鉴
    const gSeal = group(gCenter, 'suan-aw-seal');
    el('circle', {
      cx, cy, r: rSeal,
      fill: 'url(#suan-seal-grad)', stroke:'#9c2f2c','stroke-width':'1.3',
    }, gSeal);
    // 印章内框
    el('circle', {
      cx, cy, r: rSeal - 4,
      fill:'transparent', stroke:'rgba(255,250,240,0.55)','stroke-width':'0.8',
    }, gSeal);
    el('text', {
      x: cx, y: cy + 2,
      class:'suan-aw-seal-char',
      'text-anchor':'middle', 'dominant-baseline':'central',
    }, gSeal).textContent = '算';

    // 月相文本（放在中心圆下方）
    if (chart.moon_phase) {
      el('text', {
        x: cx, y: cy + rSeal + 18,
        class:'suan-aw-moon-phase',
        'text-anchor':'middle', 'dominant-baseline':'middle',
      }, gCenter).textContent = '月相 · ' + chart.moon_phase;
    }

    // ── tooltip 容器（在 svg 之上） ────────────────────────
    if (!svgEl.__suanTip) {
      const tip = document.createElement('div');
      tip.className = 'suan-aw-tooltip';
      tip.style.position = 'absolute';
      tip.style.display = 'none';
      tip.style.zIndex = '50';
      tip.style.pointerEvents = 'none';
      // 把 tip 挂到 svg 的 offsetParent（最近 position:relative 的祖先）；
      // 实际计算坐标时用 client 坐标转换
      document.body.appendChild(tip);
      svgEl.__suanTip = tip;
    }
  }

  // ────────────────────────────────────────────────────────────
  // hover 处理
  // ────────────────────────────────────────────────────────────
  function onPlanetHover(svgEl, gP, p, enter) {
    const tip = svgEl.__suanTip;
    if (!tip) return;
    if (enter) {
      gP.classList.add('is-hover');
      tip.innerHTML = gP.__suanTip;
      tip.style.display = 'block';
      const onMove = (ev) => {
        tip.style.left = (ev.clientX + 14) + 'px';
        tip.style.top  = (ev.clientY + 14) + 'px';
      };
      // 立即定位一次（用元素中心）
      const r = gP.getBoundingClientRect();
      tip.style.left = (r.left + r.width / 2 + 14) + 'px';
      tip.style.top  = (r.top  + r.height/ 2 + 14) + 'px';
      gP.__suanMoveHandler = onMove;
      gP.addEventListener('mousemove', onMove);
    } else {
      gP.classList.remove('is-hover');
      tip.style.display = 'none';
      if (gP.__suanMoveHandler) {
        gP.removeEventListener('mousemove', gP.__suanMoveHandler);
        gP.__suanMoveHandler = null;
      }
    }
  }

  function formatPlanetTip(p) {
    // 度·分·秒
    function dms(deg) {
      const d = Math.floor(deg);
      const mFloat = (deg - d) * 60;
      const m = Math.floor(mFloat);
      const s = Math.round((mFloat - m) * 60);
      return `${d}°${String(m).padStart(2,'0')}′${String(s).padStart(2,'0')}″`;
    }
    const sign = p.sign || '—';
    const dmsTxt = (typeof p.signDeg === 'number') ? dms(p.signDeg) : '—';
    const house = p.house ? `第 ${p.house} 宫` : '—';
    const retro = p.retro ? '<span class="suan-aw-tip-retro">逆 ℞</span>' : '';
    return `
      <div class="suan-aw-tip-head">
        <span class="suan-aw-tip-glyph" style="color:${p.color}">${p.glyph}</span>
        <span class="suan-aw-tip-name">${p.name}</span>
        ${retro}
      </div>
      <div class="suan-aw-tip-row"><span class="k">星座</span><span class="v">${sign}</span></div>
      <div class="suan-aw-tip-row"><span class="k">度数</span><span class="v">${dmsTxt}</span></div>
      <div class="suan-aw-tip-row"><span class="k">宫位</span><span class="v">${house}</span></div>
      <div class="suan-aw-tip-row"><span class="k">黄经</span><span class="v">${(p.lon||0).toFixed(2)}°</span></div>
    `;
  }

  function destroy(svgEl) {
    if (!svgEl) return;
    if (svgEl.__suanTip) {
      try { svgEl.__suanTip.remove(); } catch(e) {}
      svgEl.__suanTip = null;
    }
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
  }

  // ────────────────────────────────────────────────────────────
  // export
  // ────────────────────────────────────────────────────────────
  window.SuanAstroWheel = {
    render,
    destroy,
    // 暴露常量给其它脚本引用
    SIGN_GLYPH, PLANET_DEF, ASPECT_DEF, ROMAN, HOUSE_CN,
  };
})();
