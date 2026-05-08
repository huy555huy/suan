/* ============================================================
   suan · 命运日记（本机持久化 + 时间到主动回访）

   功能：
   - 用户在任何 advice / consensus / verdict 旁边点"记下"，存入本机
   - /journal 页面看所有记下条目（按时间排序）
   - 每条可挂"提醒回访时间"（30 天 / 90 天 / 半年 / 一年）
   - 进入 chat 时若有到期未回访条目，自动弹出"还记得吗"提醒
   ============================================================ */

(function () {
  'use strict';

  const KEY = 'suan.journal.v1';

  function _now() { return Date.now(); }
  function _uuid() { return 'j_' + Math.random().toString(36).slice(2, 11); }

  function _load() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || '[]');
    } catch (e) { return []; }
  }
  function _save(items) {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) {}
  }

  /**
   * 添加一条命运日记
   * @param {Object} entry { kind, text, source, sessionId, advice, recallAfterDays }
   *   kind: 'consensus' | 'advice' | 'caution' | 'verdict' | 'cross_link' | 'reflection' | 'custom'
   *   text: 主要内容
   *   source: { question, profileName }
   *   sessionId: 来源会话
   *   advice: 可选额外内容
   *   recallAfterDays: 几天后提醒回访（默认 90）
   */
  function add(entry) {
    const items = _load();
    const it = {
      id: _uuid(),
      kind: entry.kind || 'custom',
      text: entry.text || '',
      source: entry.source || {},
      sessionId: entry.sessionId || null,
      advice: entry.advice || '',
      createdAt: _now(),
      recallAt: _now() + (entry.recallAfterDays || 90) * 86400000,
      recalled: false,
      verdict: entry.verdict || null,  // 用户回访时填的"应了/没应/部分应"
    };
    items.unshift(it);
    _save(items);
    return it;
  }

  function list() { return _load(); }
  function get(id) { return _load().find(x => x.id === id); }
  function remove(id) {
    const items = _load().filter(x => x.id !== id);
    _save(items);
  }
  function update(id, patch) {
    const items = _load();
    const i = items.findIndex(x => x.id === id);
    if (i >= 0) {
      Object.assign(items[i], patch);
      _save(items);
    }
  }

  /**
   * 找到期未回访的条目（recallAt <= now 且 !recalled）
   */
  function dueRecalls() {
    const now = _now();
    return _load().filter(x => !x.recalled && x.recallAt <= now);
  }

  function markRecalled(id, verdict) {
    update(id, { recalled: true, recalledAt: _now(), verdict });
  }

  function clear() {
    _save([]);
  }

  function exportJSON() {
    return JSON.stringify(_load(), null, 2);
  }
  function importJSON(text) {
    try {
      const items = JSON.parse(text);
      if (Array.isArray(items)) _save(items);
      return true;
    } catch (e) { return false; }
  }

  // 暴露
  window.SuanJournal = {
    add, list, get, remove, update,
    dueRecalls, markRecalled,
    clear, exportJSON, importJSON,
  };
})();
