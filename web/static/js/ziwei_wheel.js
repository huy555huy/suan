/* ============================================================
   suan · 紫微斗数 · 十二宫环形盘
   ------------------------------------------------------------
   纯 SVG / 无外部依赖。
   API:
     window.SuanZiweiWheel = {
       render(svgEl, chart, opts = {}),
       destroy(svgEl),
     }

   chart 形状（来自后端 ZiweiChart）：
     palaces: [{
       name: '命宫', branch: '巳', stem: '癸', ganzhi: '癸巳',
       stars: ['廉贞','贪狼'],
       auxiliary: ['天马','铃星'],
       si_hua: ['文昌化忌']  // 四化命中字符串
     }, ...]
     life_palace: '命宫',
     body_palace: '迁移',
     five_element_bureau: '水二局',
     si_hua: {化禄:'巨门', 化权:'太阳', 化科:'文曲', 化忌:'文昌'}
     da_xian: [...]

   opts:
     size:  600        (画布边长)
     compact: false    (true 时去掉文字密度，仅保留主结构)
     onPalaceClick: fn (兼容 CustomEvent 之外的回调)

   交互：
     hover 宫 → 扇区底色加深 + tooltip
     click 宫 → svgEl.dispatchEvent(CustomEvent('ziwei-palace-click',{detail:{palace}}))
   ============================================================ */
(function (global) {
  'use strict';

  // SVG 命名空间
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // 12 地支顺序（起子）
  const ZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];

  // 地支 → 时钟位映射（语义层）—— 子 6 点 / 午 12 点 / 卯 3 点 / 酉 9 点
  // SVG 角度：0° = 3 点钟，顺时针 +
  // 6 点钟  = 90°  | 12 点钟 = -90° (即 270°) | 9 点 = 180° | 3 点 = 0°
  const CLOCK = {
    '子': 6,  '丑': 5,  '寅': 4,  '卯': 3,  '辰': 2,  '巳': 1,
    '午': 12, '未': 11, '申': 10, '酉': 9,  '戌': 8,  '亥': 7,
  };
  function zhiToClock(zhi) { return CLOCK[zhi]; }
  /** 时钟位 → 该扇区中心角（度，SVG 坐标，0=3点 顺时针） */
  function clockToCenterAngle(clk) {
    // 12 点 → -90°；3 点 → 0°；6 点 → 90°；9 点 → 180°
    return (clk * 30) - 90;
  }
  /** 地支 → 该扇区中心角 */
  function zhiToCenterAngle(zhi) {
    return clockToCenterAngle(zhiToClock(zhi));
  }
  /** 地支 → 该扇区起止角度（左→右扇区边界） */
  function zhiToWedge(zhi) {
    const c = zhiToCenterAngle(zhi);
    return { a1: c - 15, a2: c + 15 };
  }

  // 14 主星颜色编码
  const STAR_COLOR = {
    // 紫微帝座系（鎏金）
    '紫微': '#b89968',
    '天府': '#b89968',
    // 朱砂太阳
    '太阳': '#c8403c',
    // 廉贞 — 朱砂深
    '廉贞': '#a32d2c',
    // 月白太阴
    '太阴': '#857642',
    // 黛青武耀（武曲 / 七杀 / 破军 / 贪狼）
    '武曲': '#4a6670',
    '七杀': '#4a6670',
    '破军': '#4a6670',
    '贪狼': '#4a6670',
    // 翠玉文耀（天机 / 天梁 / 天同 / 巨门 / 天相）
    '天机': '#5d7c6a',
    '天梁': '#5d7c6a',
    '天同': '#5d7c6a',
    '巨门': '#5d7c6a',
    '天相': '#5d7c6a',
  };
  const STAR_DEFAULT_COLOR = '#2c2c2c';

  // 四化色 + 字（按右上角小色点）
  const SI_HUA_COLOR = {
    '化禄': '#5d7c6a', // 翠玉绿
    '化权': '#4a6670', // 黛青
    '化科': '#b89968', // 鎏金
    '化忌': '#c8403c', // 朱砂
  };

  // 扇形 SVG path（带内外环）
  function sectorPath(cx, cy, rIn, rOut, a1, a2) {
    const d2r = Math.PI / 180;
    const x1 = cx + rIn  * Math.cos(a1 * d2r);
    const y1 = cy + rIn  * Math.sin(a1 * d2r);
    const x2 = cx + rOut * Math.cos(a1 * d2r);
    const y2 = cy + rOut * Math.sin(a1 * d2r);
    const x3 = cx + rOut * Math.cos(a2 * d2r);
    const y3 = cy + rOut * Math.sin(a2 * d2r);
    const x4 = cx + rIn  * Math.cos(a2 * d2r);
    const y4 = cy + rIn  * Math.sin(a2 * d2r);
    const large = Math.abs(a2 - a1) > 180 ? 1 : 0;
    return `M${x1},${y1} L${x2},${y2} A${rOut},${rOut} 0 ${large} 1 ${x3},${y3} L${x4},${y4} A${rIn},${rIn} 0 ${large} 0 ${x1},${y1} Z`;
  }

  function polar(cx, cy, r, angleDeg) {
    const a = angleDeg * Math.PI / 180;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }

  function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const k in attrs) {
        if (attrs[k] === null || attrs[k] === undefined) continue;
        node.setAttribute(k, attrs[k]);
      }
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  // 简易 tooltip（DOM 节点，附在 svgEl 父容器上）
  function ensureTooltip(svgEl) {
    let host = svgEl.__zwTooltip;
    if (host && document.body.contains(host)) return host;
    host = document.createElement('div');
    host.className = 'zw-tooltip';
    host.style.cssText = [
      'position:fixed', 'pointer-events:none',
      'z-index:1000',
      'background:rgba(26,26,26,0.94)',
      'color:#faf6f0',
      'font-family:"Source Han Serif SC","Noto Serif SC",serif',
      'font-size:12.5px', 'line-height:1.7',
      'padding:10px 14px',
      'border:1px solid #b89968',
      'box-shadow:0 6px 20px rgba(26,26,26,.18)',
      'max-width:240px', 'opacity:0',
      'transition:opacity 120ms ease',
      'letter-spacing:0.04em',
      'white-space:normal',
    ].join(';');
    document.body.appendChild(host);
    svgEl.__zwTooltip = host;
    return host;
  }

  function showTooltip(svgEl, html, x, y) {
    const t = ensureTooltip(svgEl);
    t.innerHTML = html;
    t.style.left = (x + 14) + 'px';
    t.style.top  = (y + 14) + 'px';
    t.style.opacity = '1';
  }
  function hideTooltip(svgEl) {
    const t = svgEl.__zwTooltip;
    if (t) t.style.opacity = '0';
  }

  // 简易 escape
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // 把宫 si_hua 字符串拆成 { star, hua } —— 形如 "文昌化忌"
  function parseSiHua(siHuaArr) {
    const out = [];
    if (!Array.isArray(siHuaArr)) return out;
    siHuaArr.forEach(s => {
      const m = /^(.+?)(化禄|化权|化科|化忌)$/.exec(s);
      if (m) out.push({ star: m[1], hua: m[2] });
    });
    return out;
  }

  // 主入口
  function render(svgEl, chart, opts) {
    if (!svgEl || !chart) return;
    opts = opts || {};
    const SIZE = opts.size || 600;
    const compact = !!opts.compact;
    const cx = SIZE / 2, cy = SIZE / 2;

    // 半径分层 — 外环（宫名 + 干支）/ 中环（主星）/ 内环（辅星 + 四化）/ 中心圆（五行局）
    const rOuter      = SIZE * 0.490;  // 最外圆边
    const rOuterRing  = SIZE * 0.430;  // 外环内边
    const rMiddleRing = SIZE * 0.300;  // 中环（主星）内边
    const rInnerRing  = SIZE * 0.215;  // 内环（辅星）内边
    const rCenter     = SIZE * 0.205;  // 中心圆外边

    // 清空 svgEl
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    svgEl.setAttribute('viewBox', `0 0 ${SIZE} ${SIZE}`);
    svgEl.setAttribute('width',  SIZE);
    svgEl.setAttribute('height', SIZE);
    svgEl.setAttribute('xmlns', SVG_NS);
    svgEl.style.userSelect = 'none';
    svgEl.style.fontFamily = '"Source Han Serif SC", "Noto Serif SC", "Songti SC", serif';

    // 防止重渲染时残余 listener
    if (svgEl.__zwHandler) {
      svgEl.removeEventListener('mouseleave', svgEl.__zwHandler);
    }
    svgEl.__zwHandler = () => hideTooltip(svgEl);
    svgEl.addEventListener('mouseleave', svgEl.__zwHandler);

    // 背景纸色
    el('rect', { x: 0, y: 0, width: SIZE, height: SIZE, fill: '#faf6f0' }, svgEl);

    // 罗盘最外圈 — 极细边
    el('circle', { cx, cy, r: rOuter, fill: 'none', stroke: '#1a1a1a', 'stroke-width': 0.6, opacity: 0.55 }, svgEl);
    el('circle', { cx, cy, r: rOuterRing, fill: 'none', stroke: '#1a1a1a', 'stroke-width': 0.4, opacity: 0.35 }, svgEl);
    el('circle', { cx, cy, r: rMiddleRing, fill: 'none', stroke: '#1a1a1a', 'stroke-width': 0.4, opacity: 0.25 }, svgEl);
    el('circle', { cx, cy, r: rInnerRing, fill: 'none', stroke: '#1a1a1a', 'stroke-width': 0.4, opacity: 0.20 }, svgEl);

    // 12 等分扇区（先画底色 + 分隔线）
    const palaces = (chart.palaces || []);
    const palaceByBranch = {};
    palaces.forEach(p => { if (p && p.branch) palaceByBranch[p.branch] = p; });

    const lifeName = chart.life_palace || '';
    const bodyName = chart.body_palace || '';

    // 渲染顺序：先 12 个底层扇区（背景 + 高亮），再分隔线，再文字
    ZHI.forEach(branch => {
      const w = zhiToWedge(branch);
      const pal = palaceByBranch[branch];
      const isLife = pal && pal.name === lifeName;
      const isBody = pal && pal.name === bodyName;

      // 整个扇区可点击区
      const sectorAll = sectorPath(cx, cy, rCenter, rOuter, w.a1, w.a2);
      const baseFill = isLife
        ? 'rgba(200,64,60,0.06)'
        : (isBody ? 'rgba(74,102,112,0.05)' : 'transparent');

      const wedge = el('path', {
        d: sectorAll,
        fill: baseFill,
        stroke: 'none',
        'data-branch': branch,
        class: 'zw-wedge',
      }, svgEl);
      wedge.style.cursor = pal ? 'pointer' : 'default';

      // hover / click 处理
      if (pal) {
        wedge.addEventListener('mouseenter', (ev) => {
          wedge.setAttribute('fill', isLife
            ? 'rgba(200,64,60,0.14)'
            : (isBody ? 'rgba(74,102,112,0.13)' : 'rgba(26,26,26,0.06)'));
        });
        wedge.addEventListener('mousemove', (ev) => {
          const html = buildTooltipHTML(pal);
          showTooltip(svgEl, html, ev.clientX, ev.clientY);
        });
        wedge.addEventListener('mouseleave', () => {
          wedge.setAttribute('fill', baseFill);
          hideTooltip(svgEl);
        });
        wedge.addEventListener('click', () => {
          const detail = { palace: pal.name, branch: pal.branch, stem: pal.stem,
                            stars: pal.stars || [], auxiliary: pal.auxiliary || [],
                            si_hua: pal.si_hua || [] };
          try {
            const evt = new CustomEvent('ziwei-palace-click', { detail, bubbles: true });
            svgEl.dispatchEvent(evt);
          } catch (e) {}
          if (typeof opts.onPalaceClick === 'function') {
            opts.onPalaceClick(detail);
          }
        });
      }

      // 命宫粗边
      if (isLife) {
        el('path', {
          d: sectorAll,
          fill: 'none',
          stroke: '#c8403c',
          'stroke-width': 1.6,
          opacity: 0.9,
          'pointer-events': 'none',
        }, svgEl);
      } else if (isBody) {
        el('path', {
          d: sectorAll,
          fill: 'none',
          stroke: '#4a6670',
          'stroke-width': 1.0,
          opacity: 0.65,
          'stroke-dasharray': '3 2',
          'pointer-events': 'none',
        }, svgEl);
      }
    });

    // 12 条分隔线（从中心圆到最外）
    ZHI.forEach(branch => {
      const w = zhiToWedge(branch);
      const p1 = polar(cx, cy, rCenter, w.a1);
      const p2 = polar(cx, cy, rOuter, w.a1);
      el('line', {
        x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y,
        stroke: '#1a1a1a', 'stroke-width': 0.5, opacity: 0.32,
        'pointer-events': 'none',
      }, svgEl);
    });

    // ── 文字层 ─────────────────────────────────────────────────
    ZHI.forEach(branch => {
      const w = zhiToWedge(branch);
      const center = (w.a1 + w.a2) / 2;
      const pal = palaceByBranch[branch];

      // 1) 外环：宫名（小） + 天干地支（更小）
      const outerLabelR = (rOuter + rOuterRing) / 2;
      const outerPos = polar(cx, cy, outerLabelR, center);
      const palaceName = pal ? pal.name : '';
      const ganzhi = pal ? `${pal.stem || ''}${pal.branch}` : branch;

      // 宫名 — 楷体
      const nameTxt = el('text', {
        x: outerPos.x, y: outerPos.y - 6,
        'text-anchor': 'middle', 'dominant-baseline': 'central',
        'font-family': '"Kaiti SC", "STKaiti", "Source Han Serif SC", serif',
        'font-size': 13.5,
        'letter-spacing': '0.18em',
        fill: pal && pal.name === lifeName ? '#c8403c' : '#1a1a1a',
        'pointer-events': 'none',
      }, svgEl);
      nameTxt.textContent = palaceName;

      // 干支 — 篆书风（备选 STZhongsong / STKaiti）
      const gzTxt = el('text', {
        x: outerPos.x, y: outerPos.y + 10,
        'text-anchor': 'middle', 'dominant-baseline': 'central',
        'font-family': '"STZhongsong", "STKaiti", "Source Han Serif SC", serif',
        'font-size': 11,
        'letter-spacing': '0.20em',
        fill: '#4a6670',
        opacity: 0.85,
        'pointer-events': 'none',
      }, svgEl);
      gzTxt.textContent = ganzhi;

      // 2) 中环：主星（纵向，从外向内排）
      const stars = (pal && pal.stars) || [];
      // 把"该宫主星" 与 "该宫四化命中" 关联，给主星挂角标
      const palaceSiHua = parseSiHua(pal && pal.si_hua);
      const siHuaByStar = {};
      palaceSiHua.forEach(o => { siHuaByStar[o.star] = o.hua; });

      const middleOuterR = rOuterRing - 6;
      const middleInnerR = rMiddleRing + 6;
      const stepCount = Math.max(stars.length, 1);
      // 等距分 stepCount 个槽位，取每槽中心
      const slotSize = (middleOuterR - middleInnerR) / Math.max(stepCount, 2);

      stars.slice(0, 4).forEach((star, idx) => {
        // 每颗主星对应一个半径位置（从外到内）
        const r = middleOuterR - slotSize * (idx + 0.5);
        const pt = polar(cx, cy, r, center);
        const color = STAR_COLOR[star] || STAR_DEFAULT_COLOR;
        const txt = el('text', {
          x: pt.x, y: pt.y,
          'text-anchor': 'middle', 'dominant-baseline': 'central',
          'font-family': '"Source Han Serif SC", "Noto Serif SC", "Songti SC", serif',
          'font-size': stars.length >= 3 ? 14 : 16,
          'font-weight': 600,
          fill: color,
          'letter-spacing': '0.12em',
          'pointer-events': 'none',
        }, svgEl);
        txt.textContent = star;

        // 主星右侧的四化角标
        const hua = siHuaByStar[star];
        if (hua) {
          // 在该主星 text 的右上角追加微小色点 + 字
          // 算视觉角度：让字出现在径向方向偏外侧 12px 处
          const angOff = center;  // 用同向辐射偏移
          const ptDot = polar(cx, cy, r + 8, angOff + 4); // 沿切向偏一点
          const huaColor = SI_HUA_COLOR[hua] || '#1a1a1a';
          el('circle', { cx: ptDot.x, cy: ptDot.y, r: 2.2, fill: huaColor,
                         opacity: 0.95, 'pointer-events': 'none' }, svgEl);
          const huaLetterPt = polar(cx, cy, r + 14, angOff + 4);
          const huaTxt = el('text', {
            x: huaLetterPt.x, y: huaLetterPt.y,
            'text-anchor': 'middle', 'dominant-baseline': 'central',
            'font-family': '"Kaiti SC", "STKaiti", serif',
            'font-size': 9.5,
            'letter-spacing': '0',
            fill: huaColor,
            'pointer-events': 'none',
          }, svgEl);
          // 化禄 / 化权 / 化科 / 化忌 → 取第二字"禄/权/科/忌"
          huaTxt.textContent = hua.charAt(1) || '';
        }
      });

      // 3) 内环：辅星（前 3 个，简化呈现） + 该宫所有四化命中（小色块栏）
      if (!compact) {
        const aux = (pal && pal.auxiliary) || [];
        const innerOuterR = rMiddleRing - 6;
        const innerInnerR = rInnerRing + 4;
        const aSlot = (innerOuterR - innerInnerR) / 3;
        aux.slice(0, 3).forEach((a, idx) => {
          const r = innerOuterR - aSlot * (idx + 0.5);
          const pt = polar(cx, cy, r, center);
          const txt = el('text', {
            x: pt.x, y: pt.y,
            'text-anchor': 'middle', 'dominant-baseline': 'central',
            'font-family': '"Source Han Serif SC", "Songti SC", serif',
            'font-size': 10.5,
            'fill': '#4a4a4a',
            'opacity': 0.78,
            'letter-spacing': '0.08em',
            'pointer-events': 'none',
          }, svgEl);
          txt.textContent = a;
        });
      }
    });

    // ── 中心圆 ────────────────────────────────────────────────
    el('circle', { cx, cy, r: rCenter,
                   fill: '#faf6f0',
                   stroke: '#b89968',
                   'stroke-width': 0.8,
                   opacity: 0.9 }, svgEl);
    // 内边纹（淡）
    el('circle', { cx, cy, r: rCenter - 6,
                   fill: 'none',
                   stroke: '#b89968',
                   'stroke-width': 0.4,
                   opacity: 0.35 }, svgEl);

    // 中心文本：紫微 · 五行局 · 命/身宫
    const centerLines = [];
    centerLines.push({ text: '紫微斗数', font: '"Kaiti SC", serif', size: 11, color: '#a09b94', spacing: '0.36em', dy: -rCenter * 0.48 });
    if (chart.five_element_bureau) {
      centerLines.push({ text: chart.five_element_bureau, font: '"Source Han Serif SC", serif', size: 18, color: '#1a1a1a', spacing: '0.10em', dy: -rCenter * 0.16 });
    }
    if (chart.life_palace) {
      const lifePalaceObj = palaces.find(p => p.name === chart.life_palace);
      const lifeBranch = lifePalaceObj ? lifePalaceObj.branch : '';
      centerLines.push({ text: `命宫 · ${lifeBranch}`, font: '"Kaiti SC", serif', size: 12, color: '#c8403c', spacing: '0.22em', dy: rCenter * 0.18 });
    }
    if (chart.body_palace) {
      centerLines.push({ text: `身宫 · ${chart.body_palace}`, font: '"Kaiti SC", serif', size: 11, color: '#4a6670', spacing: '0.22em', dy: rCenter * 0.42 });
    }
    centerLines.forEach(line => {
      const t = el('text', {
        x: cx, y: cy + line.dy,
        'text-anchor': 'middle', 'dominant-baseline': 'central',
        'font-family': line.font,
        'font-size': line.size,
        fill: line.color,
        'letter-spacing': line.spacing,
        'pointer-events': 'none',
      }, svgEl);
      t.textContent = line.text;
    });

    // 命字朱印（只在中心圆上方挂个小印章 — 当尺寸够大时）
    if (SIZE >= 360) {
      const sealR = SIZE * 0.034;
      const sealCx = cx;
      const sealCy = cy - rCenter - sealR - 4;
      el('rect', {
        x: sealCx - sealR, y: sealCy - sealR,
        width: sealR * 2, height: sealR * 2,
        fill: '#c8403c',
        opacity: 0.94,
        rx: 1, ry: 1,
        'pointer-events': 'none',
      }, svgEl);
      const sealTxt = el('text', {
        x: sealCx, y: sealCy,
        'text-anchor': 'middle', 'dominant-baseline': 'central',
        'font-family': '"Kaiti SC", "STKaiti", serif',
        'font-size': sealR * 1.2,
        fill: '#faf6f0',
        'pointer-events': 'none',
      }, svgEl);
      sealTxt.textContent = '命';
    }

    // 四化图例（左下角小条 — 只在尺寸较大时显示）
    if (!compact && SIZE >= 360 && chart.si_hua) {
      const legendY = SIZE - 18;
      let legendX = 18;
      const items = ['化禄', '化权', '化科', '化忌'];
      items.forEach((hua, idx) => {
        const star = chart.si_hua[hua];
        if (!star) return;
        const color = SI_HUA_COLOR[hua];
        el('circle', { cx: legendX + 4, cy: legendY, r: 2.6, fill: color, 'pointer-events': 'none' }, svgEl);
        const t = el('text', {
          x: legendX + 12, y: legendY,
          'text-anchor': 'start', 'dominant-baseline': 'central',
          'font-family': '"Kaiti SC", serif',
          'font-size': 10.5,
          fill: '#2c2c2c',
          'letter-spacing': '0.04em',
          'pointer-events': 'none',
        }, svgEl);
        t.textContent = `${hua.charAt(1)} · ${star}`;
        legendX += t.getComputedTextLength ? (t.getComputedTextLength() + 22) : 80;
      });
    }
  }

  function buildTooltipHTML(pal) {
    const stars = (pal.stars || []).join(' · ');
    const aux = (pal.auxiliary || []).join(' · ');
    const sihua = (pal.si_hua || []).join(' · ');
    const lines = [];
    lines.push(`<div style="font-family:'Kaiti SC',serif;letter-spacing:0.18em;color:#b89968;font-size:11px;">${esc(pal.stem || '')}${esc(pal.branch || '')} · 宫</div>`);
    lines.push(`<div style="font-family:'Source Han Serif SC',serif;font-size:15px;letter-spacing:0.06em;margin:2px 0 6px;">${esc(pal.name || '')}</div>`);
    if (stars) lines.push(`<div><span style="color:#b89968;font-family:'Kaiti SC',serif;letter-spacing:0.18em;">主星</span>　<span>${esc(stars)}</span></div>`);
    if (aux)   lines.push(`<div style="margin-top:3px;"><span style="color:#5d7c6a;font-family:'Kaiti SC',serif;letter-spacing:0.18em;">辅星</span>　<span style="color:#c7c1b8;">${esc(aux)}</span></div>`);
    if (sihua) lines.push(`<div style="margin-top:3px;"><span style="color:#c8403c;font-family:'Kaiti SC',serif;letter-spacing:0.18em;">四化</span>　<span style="color:#c8403c;">${esc(sihua)}</span></div>`);
    return lines.join('');
  }

  function destroy(svgEl) {
    if (!svgEl) return;
    if (svgEl.__zwHandler) {
      svgEl.removeEventListener('mouseleave', svgEl.__zwHandler);
      svgEl.__zwHandler = null;
    }
    if (svgEl.__zwTooltip) {
      try { svgEl.__zwTooltip.remove(); } catch (e) {}
      svgEl.__zwTooltip = null;
    }
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
  }

  global.SuanZiweiWheel = { render, destroy };
})(window);
