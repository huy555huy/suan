/* ============================================================
   suan · 当日推送 ·

   - 页面打开时算流日干支 + 月相 + 节气
   - 如果有 profile，去后端 /api/v1/daily 拉一句"今日提示"
   - 没有则只显示干支节气月相
   ============================================================ */

(function () {
  'use strict';

  const KEY_DISMISSED = 'suan.daily.dismissed.';

  function _today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  function alreadyDismissed() {
    try {
      return localStorage.getItem(KEY_DISMISSED + _today()) === '1';
    } catch (e) { return false; }
  }
  function dismiss() {
    try { localStorage.setItem(KEY_DISMISSED + _today(), '1'); } catch (e) {}
  }

  /**
   * 拉今日提示
   * 后端 /api/v1/daily 接受 {profile} 返回 {gz, term, moon, hint, lucky_direction, color}
   */
  async function fetchToday(profile) {
    if (!profile) return null;
    try {
      const r = await fetch('/api/v1/daily', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile }),
      });
      if (!r.ok) return null;
      return await r.json();
    } catch (e) { return null; }
  }

  /**
   * 渲染当日推送卡（顶部位置）
   */
  function render(container, data) {
    if (!container || !data) return;
    container.innerHTML = `
      <div class="daily-card">
        <div class="daily-head">
          <span class="font-kai" style="letter-spacing:0.32em;color:var(--vermilion);font-size:11.5px;">今日 · 提示</span>
          <button class="daily-close" aria-label="关闭" onclick="this.closest('.daily-wrap').remove(); window.SuanDaily.dismiss();">×</button>
        </div>
        <div class="daily-meta">
          <span class="font-kai">${data.gz || ''}日</span>
          <span class="dot">·</span>
          <span class="font-kai">${data.term || ''}</span>
          <span class="dot">·</span>
          <span class="font-kai">${data.moon || ''}</span>
        </div>
        <div class="daily-hint font-serif-cn">${data.hint || '今日宜安静观心，不宜冒进。'}</div>
        ${data.lucky_direction ? `<div class="daily-lucky">利方位 · <span class="text-vermilion">${data.lucky_direction}</span> &nbsp;&nbsp; 利色 · <span style="color:${data.color || 'var(--gold)'}">${data.color_name || '黛青'}</span></div>` : ''}
      </div>
    `;
  }

  window.SuanDaily = { fetchToday, render, dismiss, alreadyDismissed };
})();
