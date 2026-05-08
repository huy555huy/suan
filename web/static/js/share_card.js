/* ============================================================
   suan · 结论卡截图分享（PNG 生成）

   做法：在 SVG 里画整张卡（朱砂印 + 落款 + 引用块 + 日期），
   再用 Canvas 把 SVG 序列化转 PNG，下载。

   优点：不依赖外部库，纯原生 SVG → Canvas → PNG。
   ============================================================ */

(function () {
  'use strict';

  const W = 1080;   // PNG 输出宽
  const H = 1080;   // 1:1 方形（社交分享通用）

  function escXml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
  }

  function wrap(text, perLine) {
    if (!text) return [];
    const out = [];
    let line = '';
    for (const ch of text) {
      line += ch;
      if (line.length >= perLine) {
        out.push(line); line = '';
      }
    }
    if (line) out.push(line);
    return out;
  }

  /**
   * 渲染一张结论卡
   * @param {Object} payload {
   *   title:         '今年事业研判',
   *   conclusion:    '稳中求变，先稳后动',
   *   confidence:    'high' | 'medium' | 'low',
   *   profileLine:   '坤造 · 1991-08-15 · 北京',
   *   councilSig:    ['八字','紫微','占星'],
   *   date:          '丙午年 立夏第三日',
   *   source:        '算 suan · 中西命理研判',
   * }
   * @returns {string} SVG 源
   */
  function buildSvg(p) {
    const conf = p.confidence || 'medium';
    const confLabel = conf === 'high' ? '高 · 置信' : conf === 'medium' ? '中 · 置信' : '低 · 置信';
    const confColor = conf === 'high' ? '#5d7c6a' : conf === 'medium' ? '#b89968' : '#a09b94';

    const title = escXml(p.title || '一段研判');
    const conclLines = wrap(p.conclusion || '', 18).map(escXml);
    const profile = escXml(p.profileLine || '');
    const date = escXml(p.date || '');
    const source = escXml(p.source || '算 suan · 中西命理研判');
    const council = (p.councilSig || []).map(escXml);

    // 标题字号根据长度动态
    const titleFs = title.length > 14 ? 36 : 44;

    // 结论位置 + 行高
    const conclLineH = 56;
    const conclYStart = 380 - (conclLines.length - 1) * conclLineH / 2;

    // 朱砂印章（中央右上方）
    const sealX = 920, sealY = 160;

    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="font-family: 'Source Han Serif SC','Songti SC',serif;">
  <!-- 背景：宣纸米白 + 微噪点 -->
  <defs>
    <pattern id="paper" width="6" height="6" patternUnits="userSpaceOnUse">
      <rect width="6" height="6" fill="#faf6f0"/>
      <circle cx="2" cy="2" r="0.4" fill="#ede5d3" opacity="0.6"/>
      <circle cx="4" cy="5" r="0.3" fill="#ede5d3" opacity="0.4"/>
    </pattern>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#paper)"/>

  <!-- 装饰：四角朱砂细线 -->
  <line x1="60" y1="60" x2="120" y2="60" stroke="#c8403c" stroke-width="2"/>
  <line x1="60" y1="60" x2="60" y2="120" stroke="#c8403c" stroke-width="2"/>
  <line x1="${W-60}" y1="60" x2="${W-120}" y2="60" stroke="#c8403c" stroke-width="2"/>
  <line x1="${W-60}" y1="60" x2="${W-60}" y2="120" stroke="#c8403c" stroke-width="2"/>
  <line x1="60" y1="${H-60}" x2="120" y2="${H-60}" stroke="#c8403c" stroke-width="2"/>
  <line x1="60" y1="${H-60}" x2="60" y2="${H-120}" stroke="#c8403c" stroke-width="2"/>
  <line x1="${W-60}" y1="${H-60}" x2="${W-120}" y2="${H-60}" stroke="#c8403c" stroke-width="2"/>
  <line x1="${W-60}" y1="${H-60}" x2="${W-60}" y2="${H-120}" stroke="#c8403c" stroke-width="2"/>

  <!-- 顶部品牌 -->
  <text x="120" y="160" font-size="22" letter-spacing="0.3em" fill="#a09b94" font-family="'Kaiti SC','STKaiti',serif">研判 · 一帖</text>

  <!-- 主标 -->
  <text x="120" y="240" font-size="${titleFs}" fill="#1a1a1a" letter-spacing="0.06em" font-weight="500">${title}</text>

  <!-- 横分割线 -->
  <line x1="120" y1="280" x2="${W-120}" y2="280" stroke="#1a1a1a" stroke-width="1.5"/>

  <!-- 结论正文（多行）-->
  ${conclLines.map((line, i) =>
    `<text x="${W/2}" y="${conclYStart + i * conclLineH}" font-size="44" fill="#2c2c2c" text-anchor="middle" letter-spacing="0.1em" font-weight="500">${line}</text>`
  ).join('\n  ')}

  <!-- 置信度徽章 -->
  <g transform="translate(${W/2 - 100}, ${conclYStart + conclLines.length * conclLineH + 40})">
    <rect x="0" y="0" width="200" height="48" fill="none" stroke="${confColor}" stroke-width="1.5"/>
    <text x="100" y="32" font-size="20" fill="${confColor}" letter-spacing="0.32em" text-anchor="middle" font-family="'Kaiti SC','STKaiti',serif">${confLabel}</text>
  </g>

  <!-- 合议堂签名 -->
  <text x="${W/2}" y="${H-280}" font-size="18" fill="#5d7c6a" text-anchor="middle" letter-spacing="0.32em" font-family="'Kaiti SC','STKaiti',serif">合议堂 · ${council.join(' · ') || '中西七路'}</text>

  <!-- 档案行 -->
  <text x="120" y="${H-200}" font-size="18" fill="#a09b94" letter-spacing="0.18em" font-family="'Kaiti SC','STKaiti',serif">档 · ${profile}</text>

  <!-- 落款 + 日期 -->
  <text x="120" y="${H-160}" font-size="18" fill="#a09b94" letter-spacing="0.18em" font-family="'Kaiti SC','STKaiti',serif">录 · ${date}</text>

  <!-- 朱砂印章（"算"字方印）-->
  <g transform="translate(${sealX}, ${sealY})">
    <rect x="-50" y="-50" width="100" height="100" fill="#c8403c" rx="3"/>
    <rect x="-46" y="-46" width="92" height="92" fill="none" stroke="#faf6f0" stroke-width="2"/>
    <text x="0" y="22" font-size="68" fill="#faf6f0" text-anchor="middle" font-family="'Kaiti SC','STKaiti','Songti SC',serif" font-weight="500">算</text>
  </g>

  <!-- 小字源标 -->
  <text x="${W-120}" y="${H-160}" font-size="14" fill="#a09b94" text-anchor="end" letter-spacing="0.4em" font-family="'Lora',serif">${source}</text>

  <!-- 底部品牌印 -->
  <text x="${W-120}" y="${H-200}" font-size="14" fill="#a09b94" text-anchor="end" letter-spacing="0.32em" font-family="'Kaiti SC','STKaiti',serif">— suan.app</text>
</svg>`;
  }

  /**
   * 把 SVG 转成 PNG Blob
   */
  function svgToPng(svgString, scale = 1) {
    return new Promise((resolve, reject) => {
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = W * scale;
        canvas.height = H * scale;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#faf6f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob(blob => blob ? resolve(blob) : reject('toBlob failed'), 'image/png', 0.95);
      };
      img.onerror = e => { URL.revokeObjectURL(url); reject(e); };
      img.src = url;
    });
  }

  /**
   * 生成 PNG 并触发下载
   */
  async function downloadCard(payload, filename) {
    const svg = buildSvg(payload);
    const blob = await svgToPng(svg, 1);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `suan-${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  /**
   * 获得预览（data URL）
   */
  async function previewDataUrl(payload) {
    const svg = buildSvg(payload);
    const blob = await svgToPng(svg, 0.5);
    return new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.readAsDataURL(blob);
    });
  }

  window.SuanShareCard = { buildSvg, svgToPng, downloadCard, previewDataUrl };
})();
