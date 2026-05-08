/* ============================================================
   suan · 塔罗翻牌动画组件

   用途：
   - chat / report 中收到 chartsSummary.tarot 或 charts.tarot 时
   - 渲染牌阵布局 + 翻牌动画（从牌堆飞出 / flip）

   API:
   window.SuanTarot.render(container, tarotChart, opts)
   ============================================================ */

(function () {
  'use strict';

  const SUIT_GLYPH = {
    'wands': '🜂', 'cups': '🜄', 'swords': '🜁', 'pentacles': '🜃',
  };
  const SUIT_NAME = {
    'wands': '权杖', 'cups': '圣杯', 'swords': '宝剑', 'pentacles': '星币',
  };

  // 牌阵位置（相对于容器尺寸 0-1）
  const SPREADS = {
    single: [
      { x: 0.5, y: 0.5, label: '指引' },
    ],
    three_card: [
      { x: 0.2, y: 0.5, label: '过去' },
      { x: 0.5, y: 0.5, label: '现在' },
      { x: 0.8, y: 0.5, label: '未来' },
    ],
    celtic_cross: [
      { x: 0.30, y: 0.50, label: '现状' },
      { x: 0.30, y: 0.50, label: '挑战', rotate: 90 },
      { x: 0.30, y: 0.78, label: '根源' },
      { x: 0.10, y: 0.50, label: '过去' },
      { x: 0.30, y: 0.22, label: '高点' },
      { x: 0.50, y: 0.50, label: '近期' },
      { x: 0.78, y: 0.85, label: '自己' },
      { x: 0.78, y: 0.65, label: '环境' },
      { x: 0.78, y: 0.45, label: '希望' },
      { x: 0.78, y: 0.20, label: '结局' },
    ],
    relationship_seven: [
      { x: 0.2, y: 0.3, label: '你' },
      { x: 0.8, y: 0.3, label: '对方' },
      { x: 0.5, y: 0.5, label: '关系底色' },
      { x: 0.2, y: 0.7, label: '你对关系的感受' },
      { x: 0.8, y: 0.7, label: '对方的感受' },
      { x: 0.35, y: 0.85, label: '当前障碍' },
      { x: 0.65, y: 0.85, label: '可能的方向' },
    ],
    decision_cross: [
      { x: 0.5, y: 0.2, label: '核心议题' },
      { x: 0.2, y: 0.5, label: '选择 A' },
      { x: 0.8, y: 0.5, label: '选择 B' },
      { x: 0.5, y: 0.5, label: '当下心境' },
      { x: 0.5, y: 0.85, label: '建议' },
    ],
    year_twelve: Array.from({length: 12}, (_, i) => {
      const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
      return {
        x: 0.5 + 0.36 * Math.cos(a),
        y: 0.5 + 0.36 * Math.sin(a),
        label: ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'][i],
      };
    }),
  };

  function ensureCss() {
    if (document.getElementById('suan-tarot-css')) return;
    const css = document.createElement('style');
    css.id = 'suan-tarot-css';
    css.textContent = `
      .suan-tarot-board {
        position: relative; width: 100%;
        background: linear-gradient(180deg, rgba(26,26,26,.04), transparent);
        padding: 24px 12px;
        border: 1px solid var(--line, #d8d4cc);
      }
      .suan-tarot-card {
        position: absolute;
        width: 80px; height: 130px;
        transform-style: preserve-3d;
        transition: transform .8s cubic-bezier(.2,.7,.2,1);
        cursor: pointer;
      }
      .suan-tarot-card .face {
        position: absolute; inset: 0;
        backface-visibility: hidden;
        border: 1px solid var(--ink, #1a1a1a);
        background: var(--paper, #faf6f0);
        display: flex; flex-direction: column;
        align-items: center; justify-content: space-between;
        padding: 10px 6px;
        box-shadow: 0 2px 12px rgba(0,0,0,.08);
      }
      .suan-tarot-card .back {
        background: var(--vermilion, #c8403c);
        border-color: var(--vermilion);
        position: absolute; inset: 0;
        backface-visibility: hidden;
        transform: rotateY(180deg);
        display: flex; align-items: center; justify-content: center;
      }
      .suan-tarot-card .back::after {
        content: '算'; color: var(--paper, #faf6f0);
        font-family: 'Kaiti SC', 'STKaiti', serif;
        font-size: 28px; letter-spacing: 0;
        border: 1px solid var(--paper); padding: 6px 12px;
      }
      .suan-tarot-card.is-flipped { transform: rotateY(180deg); }
      .suan-tarot-card.is-flipped .face { transform: rotateY(0deg); }
      .suan-tarot-card.is-flipped .back { transform: rotateY(180deg); }

      /* 翻面后展示 */
      .suan-tarot-card.is-flipped { transform: rotateY(0deg); }
      .suan-tarot-card .back { display: flex; transform: rotateY(0deg); }
      .suan-tarot-card.is-flipped .back { display: none; }

      .suan-tarot-card .num {
        font-family: 'Lora', serif;
        font-size: 11px; letter-spacing: 0.2em;
        color: var(--silver-grey, #a09b94);
      }
      .suan-tarot-card .name {
        font-family: 'Source Han Serif SC', serif;
        font-size: 13px;
        text-align: center;
        color: var(--ink, #1a1a1a);
        line-height: 1.3;
      }
      .suan-tarot-card .glyph {
        font-size: 22px;
        color: var(--vermilion, #c8403c);
      }
      .suan-tarot-card.reversed .face {
        transform: rotate(180deg);
      }
      .suan-tarot-card .pos-label {
        position: absolute;
        top: -22px; left: 0; right: 0;
        text-align: center;
        font-family: 'Kaiti SC', serif;
        font-size: 11px; letter-spacing: 0.22em;
        color: var(--silver-grey, #a09b94);
      }
      .suan-tarot-card.dealt {
        animation: deal-flip-in 1s cubic-bezier(.2,.7,.2,1) both;
      }
      @keyframes deal-flip-in {
        0% { transform: translate(0, -200px) rotate(-30deg) scale(.4); opacity: 0; }
        60% { transform: translate(0, 8px) rotate(0) scale(1.05); opacity: 1; }
        100% { transform: translate(0, 0) rotate(0) scale(1); opacity: 1; }
      }
      .suan-tarot-card:hover {
        z-index: 10;
        transform: translateY(-4px) scale(1.05);
      }
      .suan-tarot-card.reversed:hover {
        transform: translateY(-4px) scale(1.05) rotate(180deg);
      }
    `;
    document.head.appendChild(css);
  }

  function render(container, tarot, opts = {}) {
    if (!container || !tarot) return;
    ensureCss();
    container.classList.add('suan-tarot-board');
    container.innerHTML = '';

    const spreadKey = tarot.spread || 'three_card';
    const positions = SPREADS[spreadKey] || SPREADS.three_card;
    const cards = tarot.drawn_cards || [];
    const cardsCount = Math.min(positions.length, cards.length);

    // 根据牌阵设定容器高度
    const aspectRatio = spreadKey === 'celtic_cross' ? 1 :
                        spreadKey === 'year_twelve' ? 1 :
                        spreadKey === 'relationship_seven' ? 0.95 :
                        0.55;
    const containerWidth = container.offsetWidth || 600;
    const containerHeight = containerWidth * aspectRatio;
    container.style.height = containerHeight + 'px';

    // 渲染每张牌
    for (let i = 0; i < cardsCount; i++) {
      const pos = positions[i];
      const card = cards[i];
      const cardEl = document.createElement('div');
      cardEl.className = 'suan-tarot-card';
      if (card.reversed) cardEl.classList.add('reversed');

      const left = pos.x * containerWidth - 40;
      const top = pos.y * containerHeight - 65;
      cardEl.style.left = left + 'px';
      cardEl.style.top = top + 'px';
      if (pos.rotate) {
        cardEl.style.transform = `rotate(${pos.rotate}deg)`;
      }

      const isMajor = card.arcana === 'major' || (card.card_id || '').startsWith('major_');
      const num = card.number !== undefined ? card.number : '';
      const numLabel = isMajor ? (typeof num === 'number' ? toRoman(num) : num) :
                                 (typeof num === 'number' ? num : (num || ''));
      const suit = card.suit;
      const glyph = isMajor ? '☉' : (SUIT_GLYPH[suit] || '✦');

      cardEl.innerHTML = `
        <div class="pos-label">${pos.label || ''}</div>
        <div class="back"></div>
        <div class="face">
          <div class="num">${numLabel}</div>
          <div class="glyph">${glyph}</div>
          <div class="name">${card.card_name || card.name || ''}</div>
          <div class="num" style="font-size:9px;">${suit ? SUIT_NAME[suit] || '' : ''}</div>
        </div>
      `;
      cardEl.title = (card.card_name || '') +
                     (card.reversed ? ' · 逆位' : ' · 正位') +
                     (pos.label ? ` · ${pos.label}` : '');

      container.appendChild(cardEl);

      // 错峰翻牌（dramatic）
      const delay = 200 + i * 280;
      setTimeout(() => {
        cardEl.classList.add('dealt');
      }, delay);
    }
  }

  function toRoman(n) {
    const map = [['M',1000],['CM',900],['D',500],['CD',400],['C',100],['XC',90],['L',50],['XL',40],['X',10],['IX',9],['V',5],['IV',4],['I',1]];
    if (n === 0) return '0';
    let r = ''; let x = n;
    for (const [s, v] of map) { while (x >= v) { r += s; x -= v; } }
    return r;
  }

  window.SuanTarot = { render };
})();
