/* ============================================================
   suan · 中西命理 AI Agent
   前端应用脚本（Alpine.js + 真后端 SSE）
   ------------------------------------------------------------
   关键设计：
   1. Alpine 注册做了"无论谁先到都能 hook"的双保险
      （既监听 alpine:init，也检测 window.Alpine 是否已就位）
   2. /health 探测走绝对路径（后端在根，不在 /api/v1 下）
   3. SSE 事件名严格对齐后端 orchestrator.py 实际发出的事件
      （phase / classifier_done / chart_ready / charts_summary /
       expert_done / verifier_log / synth_done / aligner_done /
       aligner_skipped / verdict_done / narrative / narrative_chunk / done / error）
   4. chatStream 内嵌生辰表单 modal —— 没 profile 时不让用户回首页
   ============================================================ */

(() => {
  'use strict';

  // ---------- Constants ----------
  const API_BASE = (window.SUAN_API_BASE || '/api/v1');
  const HEALTH_URL = '/health';   // ← 后端 health 在根，不在 /api/v1
  const SESSION_KEY = 'suan.session.v1';
  const PROFILE_KEY = 'suan.profile.v1';

  // ---------- Static reference tables ----------
  const ELEMENTS = {
    '甲':'wood','乙':'wood','丙':'fire','丁':'fire',
    '戊':'earth','己':'earth','庚':'metal','辛':'metal',
    '壬':'water','癸':'water',
    '子':'water','丑':'earth','寅':'wood','卯':'wood',
    '辰':'earth','巳':'fire','午':'fire','未':'earth',
    '申':'metal','酉':'metal','戌':'earth','亥':'water'
  };
  const PALACES = ['命宫','兄弟','夫妻','子女','财帛','疾厄','迁移','奴仆','官禄','田宅','福德','父母'];
  const SCENARIOS = [
    { key: 'personality', label: '性格洞察', hint: '本命格局与气质底色' },
    { key: 'career',      label: '今年事业', hint: '当前流年的职业脉络' },
    { key: 'relation',    label: '婚恋情感', hint: '感情走向与配对参考' },
    { key: 'wealth',      label: '财运研判', hint: '财源结构与流向' },
    { key: 'single',      label: '单一事项', hint: '具体事件择时与决策' },
    { key: 'fengshui',    label: '居所方位', hint: '环境与气场调适建议' },
  ];

  // 跨页面的 Expert 列表（与后端一致 8 路）
  const COUNCIL = [
    { id: 'classifier', name: '问题路由', desc: '决定本次激活哪几路代理' },
    { id: 'parser',     name: '排盘计算', desc: '八字 / 紫微 / 占星 / 数命' },
    { id: 'bazi',       name: '八字 · 子平派',     desc: '十神 · 格局 · 大运' },
    { id: 'ziwei',      name: '紫微 · 中州派',     desc: '十二宫 · 四化' },
    { id: 'liunian',    name: '流年',             desc: '今年趋势研判' },
    { id: 'yijing',     name: '易经 · 京房',       desc: '六爻 · 梅花' },
    { id: 'fengshui',   name: '风水 · 玄空',       desc: '坐向 · 命卦' },
    { id: 'astrology',  name: '占星 · 现代心理',   desc: '本命 · 行运' },
    { id: 'tarot',      name: '塔罗 · 韦特',       desc: '牌阵 · 启发' },
    { id: 'numerology', name: '数字命理 · 毕氏',   desc: '生命数 · 个人年' },
    { id: 'verifier',   name: 'VRP 反思镜',       desc: '事实校验 + 软反馈' },
    { id: 'cn_synth',   name: '中式合议',         desc: 'CN 组小综合' },
    { id: 'wt_synth',   name: '西式合议',         desc: 'WT 组小综合' },
    { id: 'aligner',    name: '中西互照',         desc: '共识 / 分歧 / 互补' },
    { id: 'judge',      name: '综合判官',         desc: '权重综合，矛盾显式' },
    { id: 'narrative',  name: '撰写答覆',         desc: '边生成边显示' },
    { id: 'safety',     name: '合规',             desc: '红线词 / 心理风险' },
  ];

  // ---------- Utilities ----------
  function $store() { return window.Alpine && Alpine.store('suan'); }

  function uuid() {
    return 'sid_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  }

  function loadJSON(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
    catch (e) { return fallback; }
  }
  function saveJSON(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }
  function delJSON(key) { try { localStorage.removeItem(key); } catch (e) {} }

  function formatDateTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const Y = d.getFullYear();
      const M = String(d.getMonth()+1).padStart(2,'0');
      const D = String(d.getDate()).padStart(2,'0');
      const h = String(d.getHours()).padStart(2,'0');
      const m = String(d.getMinutes()).padStart(2,'0');
      return `${Y}-${M}-${D} ${h}:${m}`;
    } catch (e) { return iso; }
  }

  function pickElementFromGanZhi(s) {
    if (!s) return null;
    return ELEMENTS[s.charAt(0)] || null;
  }

  /* ============================================================
     SSE 事件流（与后端 orchestrator.py 严格对齐）
     ============================================================ */
  function openEventStream(sid, handlers) {
    const url = `${API_BASE}/sessions/${encodeURIComponent(sid)}/stream`;
    let es;
    try { es = new EventSource(url); }
    catch (e) { handlers.onError && handlers.onError(e); return null; }

    // 后端 Planner-Executor 主循环 + 旧固定流水线 全部事件
    const known = [
      // 通用
      'start', 'phase', 'error', 'done',
      // Planner 模式（v2 主路径）
      'planner_start', 'planner_thinking', 'planner_thought',
      'planner_executing', 'planner_max_steps',
      'ask_user', 'user_replied', 'waiting_user',
      'cross_link_insight', 'reflection', 'action_error',
      'narrative_start',
      // 计算 / 检索
      'chart_ready', 'chart_failed', 'charts_summary',
      'classifier_done',
      // Expert / 综合 / 判官
      'expert_done',
      'verifier_log',
      'synth_done', 'aligner_done', 'aligner_skipped',
      'verdict_done',
      // 正文
      'narrative_chunk', 'narrative',
      // 不确定性
      'input_caveats',
    ];
    known.forEach(evt => {
      es.addEventListener(evt, (e) => {
        let data; try { data = JSON.parse(e.data); } catch(_) { data = e.data; }
        handlers.onEvent && handlers.onEvent(evt, data);
      });
    });
    es.onerror = (e) => {
      // EventSource 在请求结束时也会触发 onerror，这里只在没收到 done 时才报错
      if (handlers.onConnectionEnd) handlers.onConnectionEnd();
    };
    return es;
  }

  /* ============================================================
     Alpine 注册 —— 双保险：alpine:init 或已加载
     ============================================================ */
  function registerAlpineApp() {
    if (!window.Alpine) return;

    // 防止重复注册
    if (window.__SUAN_REGISTERED__) return;
    window.__SUAN_REGISTERED__ = true;

    // -------- Global store --------
    Alpine.store('suan', {
      profile: loadJSON(PROFILE_KEY, null),
      sessions: loadJSON(SESSION_KEY, []),
      backendOnline: false,
      backendChecking: true,

      saveProfile(p) {
        this.profile = p;
        saveJSON(PROFILE_KEY, p);
      },
      clearProfile() {
        this.profile = null;
        delJSON(PROFILE_KEY);
      },
      addSession(s) {
        this.sessions.unshift(s);
        if (this.sessions.length > 30) this.sessions = this.sessions.slice(0, 30);
        saveJSON(SESSION_KEY, this.sessions);
      },
      clearAll() {
        this.profile = null; this.sessions = [];
        delJSON(PROFILE_KEY); delJSON(SESSION_KEY);
      },
    });

    // 后端探测（绝对路径 /health，不带 API_BASE 前缀）
    fetch(HEALTH_URL, { method: 'GET' })
      .then(r => {
        Alpine.store('suan').backendOnline = r.ok;
        Alpine.store('suan').backendChecking = false;
      })
      .catch(() => {
        Alpine.store('suan').backendOnline = false;
        Alpine.store('suan').backendChecking = false;
      });

    /* ---------- birthForm (用于 index.html / report.html，能互相复用) ---------- */
    Alpine.data('birthForm', () => ({
      form: {
        name: '', gender: 'female', date: '', time: '',
        unknownTime: false, place: '北京', question: '',
        scenario: 'chat',
      },
      errors: {},
      submitting: false,

      init() {
        const p = $store() && $store().profile;
        if (p) Object.assign(this.form, p);
      },

      validate() {
        const e = {};
        if (!this.form.name) e.name = '请填称呼';
        if (!this.form.date) e.date = '请填阳历生日';
        if (!this.form.unknownTime && !this.form.time) e.time = '请填出生时间，或勾选时辰未知';
        if (!this.form.place) e.place = '请填出生地';
        this.errors = e;
        return Object.keys(e).length === 0;
      },

      async submit(redirectTo) {
        if (!this.validate()) return;
        this.submitting = true;
        const profile = { ...this.form };
        $store().saveProfile(profile);
        // 不需要在这里注册 session — chatStream/reportFlow 自己会做
        if (redirectTo) {
          window.location.href = redirectTo;
        }
        this.submitting = false;
      },
    }));

    /* ---------- chatStream（聊天主体）---------- */
    Alpine.data('chatStream', () => ({
      // 档案 / 会话
      sid: null,
      profile: null,
      needProfile: false,    // 没填生辰时显示 modal
      profileForm: {
        name: '', gender: 'female', date: '', time: '',
        unknownTime: false, place: '北京', question: '',
      },
      profileErrors: {},

      // 会话状态
      messages: [],
      currentAgent: null,
      agents: COUNCIL.map(a => ({ ...a, status: 'idle', progress: 0, lastMsg: '' })),
      chart: null,
      chartsSummary: null,
      verifierStats: {},
      alignment: [],
      verdict: null,
      narrativeBuffer: '',
      streaming: false,
      waitingForUserReply: false,    // ★ Planner 在等用户回答
      activeBubbleIdx: null,          // 当前接事件的 agent bubble
      input: '',
      es: null,
      sidebarOpen: true,
      backendOnline: false,
      eventCount: 0,
      streamStartedAt: 0,
      currentStep: 0,
      stepsTotal: 0,

      quickChips: [
        { label: '本命格局', text: '请概括我的本命主格局与气质底色。' },
        { label: '今年事业', text: '今年我的事业重点在哪里？需要规避什么？' },
        { label: '感情走向', text: '近一年的感情走向与配对建议。' },
        { label: '财运研判', text: '我的财运结构是什么样的？流年财气如何？' },
        { label: '居所方位', text: '我的居所方位如何调适？' },
      ],

      init() {
        const url = new URL(window.location.href);
        this.sid = url.searchParams.get('sid') || null;
        this.profile = $store() && $store().profile;
        this.backendOnline = $store() && $store().backendOnline;

        // ── 加载今日推送（如果有 profile + 后端在线）──
        const tryDaily = () => {
          if (!this.profile || !this.backendOnline || !window.SuanDaily) return;
          if (window.SuanDaily.alreadyDismissed && window.SuanDaily.alreadyDismissed()) return;
          window.SuanDaily.fetchToday(this.profile).then(data => {
            const wrap = document.getElementById('daily-wrap');
            if (!wrap || !data) return;
            wrap.style.display = 'block';
            window.SuanDaily.render(wrap, data);
          });
        };
        setTimeout(tryDaily, 800);
        // 后端 ready 后再试一次（可能首次 init 时 backendChecking 还没完）
        const watcher = setInterval(() => {
          const s = $store();
          if (s && !s.backendChecking) {
            this.backendOnline = s.backendOnline;
            tryDaily();
            clearInterval(watcher);
          }
        }, 300);

        // 监听 store 后端在线变化
        const checkBackend = setInterval(() => {
          const s = $store();
          if (s && !s.backendChecking) {
            this.backendOnline = s.backendOnline;
            clearInterval(checkBackend);
            this.afterBackendKnown();
          }
        }, 200);

        // 没档案 → 弹生辰 modal
        if (!this.profile) {
          this.needProfile = true;
        }

        // 初始问候
        const greeting = this.profile
          ? `${this.profile.name}，你好。已为你备下中西七路通道，请提你的问题，或选下方常见情境。`
          : '欢迎。请先填入生辰，我才能为你排盘并研判。';
        this.messages.push({
          role: 'agent', agent: { id: 'host', name: 'suan' },
          text: greeting, confidence: null, traceOpen: false, trace: null,
        });
      },

      afterBackendKnown() {
        if (!this.backendOnline) {
          this.messages.push({
            role: 'agent', agent: { id: 'host', name: 'suan' },
            text: '⚠ 后端未连接（/health 探测失败）。请先 `python3 server.py` 起服务，再刷新本页。',
            confidence: null, traceOpen: false, trace: null,
          });
        }
      },

      // 生辰提交
      validateProfile() {
        const e = {};
        if (!this.profileForm.name) e.name = '请填称呼';
        if (!this.profileForm.date) e.date = '请填阳历生日';
        if (!this.profileForm.unknownTime && !this.profileForm.time) e.time = '请填出生时间，或勾选时辰未知';
        if (!this.profileForm.place) e.place = '请填出生地';
        this.profileErrors = e;
        return Object.keys(e).length === 0;
      },
      async submitProfile() {
        if (!this.validateProfile()) return;
        this.profile = { ...this.profileForm };
        $store().saveProfile(this.profile);
        this.needProfile = false;
        this.messages = this.messages.slice(0, 1);
        this.messages.push({
          role: 'agent', agent: { id: 'host', name: 'suan' },
          text: `好的，${this.profile.name}。已记下你的生辰（${this.profile.date}${this.profile.time ? ' '+this.profile.time : ' · 时辰未知'}, ${this.profile.place}）。请问吧。`,
          confidence: null, traceOpen: false, trace: null,
        });
      },
      editProfile() {
        if (this.profile) Object.assign(this.profileForm, this.profile);
        this.needProfile = true;
      },
      clearAndReturn() {
        $store().clearAll();
        window.location.reload();
      },

      // 主消息发送：分两种情况
      // (a) 首次 / 没有活跃 SSE：POST /sessions（注册档案）+ POST /messages + 开 SSE 长连接
      // (b) Agent 在等用户回答（waitingForUserReply=true）：仅 POST /messages（不开新 SSE）
      async send(textOverride) {
        const text = (textOverride ?? this.input).trim();
        if (!text) return;
        if (!this.profile) { this.needProfile = true; return; }
        if (!this.backendOnline) {
          this.messages.push({
            role: 'agent', agent: { id: 'host', name: 'suan' },
            text: '后端未连接，无法发起研判。请先启动 server.py。',
            confidence: null, traceOpen: false, trace: null,
          });
          return;
        }
        // 已经在跑且不是在等用户回答 → 忽略（避免重复 send）
        if (this.streaming && !this.waitingForUserReply) return;

        this.input = '';
        this.messages.push({ role: 'user', text });

        if (this.waitingForUserReply && this.es && this.sid) {
          // ★ 多轮：把回答投进 queue，planner 自动恢复
          this.waitingForUserReply = false;
          await fetch(`${API_BASE}/sessions/${this.sid}/messages`, {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ text }),
          });
          // 标记当前 agent bubble 重新进入"研判中"
          if (this.activeBubbleIdx !== null && this.messages[this.activeBubbleIdx]) {
            this.messages[this.activeBubbleIdx].streaming = true;
            this.messages[this.activeBubbleIdx].phase = '收到你的回复，继续研判…';
          }
          return;
        }

        // 首次：开新会话
        // 准备 agent 气泡
        const idx = this.messages.length;
        this.activeBubbleIdx = idx;
        this.messages.push({
          role: 'agent', agent: { id: 'synth', name: '研判合议' },
          text: '', confidence: null, citations: [],
          traceOpen: false, trace: { steps: [] },
          streaming: true,
          phase: '入门 · 召集中',
          chartsSummary: null,
          alignment: [],
          consensus: [], conflicts: [],
          advice: [], cautions: [],
          plannerThoughts: [],
          insights: [],
          reflections: [],
        });

        this.streaming = true;
        this.streamStartedAt = Date.now();
        this.resetAgentStatuses();
        this.narrativeBuffer = '';
        this.chartsSummary = null;
        this.verifierStats = {};
        this.alignment = [];
        this.eventCount = 0;
        this.waitingForUserReply = false;

        try {
          // 1) 注册 / 更新档案
          const reg = await fetch(`${API_BASE}/sessions`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ ...this.profile, scenario: 'chat' }),
          }).then(r => r.json());
          if (reg && reg.session_id) this.sid = reg.session_id;
        } catch (e) { this.handleError(idx, e); return; }

        $store().addSession({
          id: this.sid,
          createdAt: new Date().toISOString(),
          name: this.profile.name,
          scenario: 'chat',
          question: text,
        });

        // 2) POST 问题（首条进 queue 启动 planner）
        try {
          await fetch(`${API_BASE}/sessions/${this.sid}/messages`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ text }),
          });
        } catch (e) { this.handleError(idx, e); return; }

        // 3) 开 SSE 长连接
        this.es = openEventStream(this.sid, {
          onEvent: (evt, data) => this.handleEvent(this.activeBubbleIdx, evt, data),
          onConnectionEnd: () => { /* 流结束时正常 */ },
          onError: (e) => this.handleError(this.activeBubbleIdx, e),
        });
      },

      sendChip(text) { this.input = text; this.send(text); },

      handleEvent(idx, evt, data) {
        const bubble = this.messages[idx];
        if (!bubble) return;
        this.eventCount++;

        switch (evt) {
          case 'start':
          case 'planner_start':
            bubble.phase = 'Planner 开始调度';
            if (data.question) bubble.firstQuestion = data.question;
            break;

          case 'planner_thinking':
            bubble.phase = '思考下一步…';
            this.currentStep = data.step || this.currentStep;
            break;

          case 'planner_thought': {
            // ★ 这是 agent 行为最可见的环节：把 Planner 的思考显式呈现
            this.currentStep = data.step || (this.currentStep + 1);
            bubble.phase = `第 ${this.currentStep} 步 · ${data.action}`;
            bubble.plannerThoughts = bubble.plannerThoughts || [];
            bubble.plannerThoughts.push({
              step: this.currentStep,
              thought: data.thought,
              action: data.action,
              args: data.args,
              expected: data.expected_outcome,
            });
            bubble.trace.steps.push({
              kind: 'planner',
              step: this.currentStep,
              thought: data.thought,
              action: data.action,
              args: data.args,
            });
            break;
          }

          case 'planner_executing':
            bubble.phase = `执行 · ${data.action || ''}` + (data.expert ? ' · ' + data.expert : '');
            // 高亮对应 agent
            const exec_id = data.expert || (data.action === 'synthesize' ? (data.scope === 'cross' ? 'aligner' : (data.scope || 'judge')) :
                          data.action === 'compute_chart' ? 'parser' :
                          data.action === 'cross_link' ? 'aligner' :
                          data.action === 'reflect' ? 'verifier' :
                          data.action === 'finalize' ? 'narrative' : null);
            if (exec_id) {
              const ax = this.agents.find(x => x.id === exec_id);
              if (ax) { ax.status = 'running'; ax.progress = Math.min(40, ax.progress); }
            }
            break;

          case 'ask_user': {
            // ★ Planner 主动追问
            this.waitingForUserReply = true;
            bubble.phase = '⟶ 在等你的回答';
            bubble.streaming = false;  // 暂停 spinner
            // 在对话区显式渲染 ask_user
            this.messages.push({
              role: 'agent',
              agent: { id: 'planner', name: 'Planner · 主动追问' },
              isAskUser: true,
              question: data.question,
              why: data.why,
              text: data.question,
              confidence: null, traceOpen: false, trace: null,
            });
            // 输入框聚焦
            setTimeout(() => {
              const ta = document.querySelector('textarea[x-model="input"]');
              if (ta) ta.focus();
            }, 50);
            break;
          }

          case 'waiting_user': {
            // 心跳：保持连接，前端不需要做什么
            break;
          }

          case 'user_replied': {
            // 后端确认收到了用户回答，准备继续
            bubble.streaming = true;
            // 在用户气泡之后挂个新 agent bubble 以接续渲染
            const newIdx = this.messages.length;
            this.activeBubbleIdx = newIdx;
            this.messages.push({
              role: 'agent', agent: { id: 'synth', name: '研判合议' },
              text: '', confidence: null, citations: [],
              traceOpen: false, trace: { steps: [] }, streaming: true,
              phase: '继续研判…',
              plannerThoughts: [], insights: [], reflections: [],
            });
            break;
          }

          case 'cross_link_insight': {
            // ★ 跨系统涌现联结 — 单独显式渲染 + 全屏闪光
            bubble.insights = bubble.insights || [];
            bubble.insights.push({
              headline: data.headline,
              narrative: data.narrative,
              strength: data.strength,
              implication: data.implication,
              systems: data.systems,
              topic: data.topic,
            });
            // 高亮 aligner
            const a = this.agents.find(x => x.id === 'aligner');
            if (a) { a.status = 'done'; a.progress = 100; a.lastMsg = data.headline || '联结完成'; }
            // 触发全屏闪光（金色径向）
            if (window.SuanEnhance && window.SuanEnhance.flashOnce) {
              window.SuanEnhance.flashOnce();
            }
            break;
          }

          case 'reflection': {
            // ★ 元认知反思
            bubble.reflections = bubble.reflections || [];
            bubble.reflections.push({
              headline: data.headline,
              narrative: data.narrative,
              calibrated_confidence: data.calibrated_confidence,
              needs_followup: data.needs_followup,
            });
            const v = this.agents.find(x => x.id === 'verifier');
            if (v) { v.status = 'done'; v.progress = 100; v.lastMsg = '反思' + (data.calibrated_confidence || ''); }
            break;
          }

          case 'action_error': {
            bubble.trace.steps.push({ kind: 'error', action: data.action, error: data.error });
            break;
          }

          case 'input_caveats': {
            bubble.caveats = data.caveats || [];
            break;
          }

          case 'planner_max_steps': {
            bubble.phase = '步数已达上限，强制收束';
            break;
          }

          case 'narrative_start': {
            bubble.phase = '撰写最终回应（流式）…';
            const a = this.agents.find(x => x.id === 'narrative');
            if (a) { a.status = 'running'; a.progress = 30; }
            break;
          }

          case 'phase':
            bubble.phase = data.message || data.phase || '';
            if (data.phase) {
              const a = this.agents.find(x => x.id === data.phase);
              if (a && a.status === 'idle') a.status = 'running';
            }
            break;

          case 'classifier_done': {
            const a = this.agents.find(x => x.id === 'classifier');
            if (a) { a.status = 'done'; a.progress = 100; a.lastMsg = (data.activated || []).join(' · '); }
            (data.activated || []).forEach(e => {
              const ax = this.agents.find(x => x.id === e);
              if (ax) { ax.status = 'running'; ax.progress = 10; }
            });
            bubble.trace.steps.push({ kind: 'classifier', activated: data.activated, reason: data.reason });
            break;
          }

          case 'chart_ready': {
            const p = this.agents.find(x => x.id === 'parser');
            if (p) { p.status = 'running'; p.progress = Math.min((p.progress||0) + 18, 95); p.lastMsg = `${data.chart_type} 已排`; }
            break;
          }
          case 'chart_failed': {
            const p = this.agents.find(x => x.id === 'parser');
            if (p) { p.lastMsg = `${data.chart_type} 排盘失败`; }
            break;
          }
          case 'charts_summary': {
            const p = this.agents.find(x => x.id === 'parser');
            if (p) { p.status = 'done'; p.progress = 100; p.lastMsg = '已排盘'; }
            this.chartsSummary = data.charts;
            bubble.chartsSummary = data.charts;
            break;
          }

          case 'expert_done': {
            const a = this.agents.find(x => x.id === data.expert);
            if (a) {
              a.status = 'done'; a.progress = 100;
              a.lastMsg = (data.headline || '').slice(0, 24) + (data.headline && data.headline.length > 24 ? '…' : '');
            }
            bubble.trace.steps.push({
              kind: 'expert',
              agent: data.expert,
              system_group: data.system_group,
              school: data.school,
              summary: data.headline,
              detail: data.summary,
              confidence: data.confidence,
              n_points: data.n_points,
            });
            break;
          }

          case 'verifier_log': {
            const v = this.agents.find(x => x.id === 'verifier');
            if (v) { v.status = 'running'; v.progress = Math.min((v.progress||0) + 25, 95); v.lastMsg = `${data.expert}: ${(data.stats && data.stats.total) || 0} 条`; }
            this.verifierStats[data.expert] = data.stats;
            break;
          }

          case 'synth_done': {
            const aId = data.group === 'chinese' ? 'cn_synth' : 'wt_synth';
            const a = this.agents.find(x => x.id === aId);
            if (a) {
              a.status = data.is_skipped ? 'idle' : 'done';
              a.progress = 100;
              a.lastMsg = data.is_skipped ? '本组未激活' : (data.headline || '').slice(0, 24) + '…';
            }
            // verifier 收尾
            const v = this.agents.find(x => x.id === 'verifier');
            if (v && v.status === 'running') { v.status = 'done'; v.progress = 100; }
            break;
          }

          case 'aligner_done': {
            const a = this.agents.find(x => x.id === 'aligner');
            if (a) { a.status = 'done'; a.progress = 100;
              a.lastMsg = `共识 ${(data.consensus_score*100).toFixed(0)}% / 分歧 ${(data.divergence_score*100).toFixed(0)}%`; }
            this.alignment = data.by_topic ? Object.values(data.by_topic) : [];
            bubble.alignment = this.alignment;
            bubble.trace.steps.push({ kind: 'aligner',
              consensus_score: data.consensus_score,
              divergence_score: data.divergence_score,
              n_topics: data.n_topics,
              summary: data.summary,
            });
            break;
          }

          case 'aligner_skipped': {
            const a = this.agents.find(x => x.id === 'aligner');
            if (a) { a.status = 'idle'; a.lastMsg = data.reason || '单系统跳过'; }
            break;
          }

          case 'verdict_done': {
            const a = this.agents.find(x => x.id === 'judge');
            if (a) { a.status = 'done'; a.progress = 100; a.lastMsg = '已成判断'; }
            bubble.confidence = data.confidence;
            bubble.consensus = data.consensus || [];
            bubble.conflicts = data.conflicts || [];
            bubble.advice = data.advice || [];
            bubble.cautions = data.cautions || [];
            this.verdict = { text: (data.summary || '').slice(0, 60), confidence: data.confidence };
            break;
          }

          case 'narrative_chunk': {
            // 流式 token
            const a = this.agents.find(x => x.id === 'narrative');
            if (a && a.status !== 'done') { a.status = 'running'; a.progress = Math.min((a.progress||0) + 3, 95); }
            bubble.text += (data.text || '');
            this.narrativeBuffer += (data.text || '');
            break;
          }

          case 'narrative': {
            // 兜底：如果服务端没流式推 chunk，会发一次完整 text
            const a = this.agents.find(x => x.id === 'narrative');
            if (a) { a.status = 'done'; a.progress = 100; }
            const safety = this.agents.find(x => x.id === 'safety');
            if (safety) { safety.status = 'done'; safety.progress = 100; }
            // 只在 chunk 没填过时使用 full text
            if (!bubble.text || bubble.text.length < 30) {
              bubble.text = data.text || '';
            }
            break;
          }

          case 'done': {
            this.streaming = false;
            bubble.streaming = false;
            bubble.phase = '已完成';
            const elapsed = Math.round((Date.now() - this.streamStartedAt)/1000);
            bubble.elapsed = elapsed;
            // 把所有还在 running 的 agent 置完成
            this.agents.forEach(a => { if (a.status === 'running') { a.status = 'done'; a.progress = 100; } });
            const narA = this.agents.find(x => x.id === 'narrative');
            if (narA && narA.status === 'idle') { narA.status = 'done'; narA.progress = 100; }
            const safety = this.agents.find(x => x.id === 'safety');
            if (safety) { safety.status = 'done'; safety.progress = 100; }
            if (this.es && this.es.close) { try { this.es.close(); } catch(e) {} }
            this.es = null;
            break;
          }

          case 'error': {
            this.handleError(idx, data);
            break;
          }
        }
      },

      handleError(idx, e) {
        const bubble = this.messages[idx];
        if (bubble) {
          bubble.error = '研判流断开。' + (e && e.message ? '原因：' + e.message : '可重试。');
          bubble.streaming = false;
        }
        this.streaming = false;
        if (this.es && this.es.close) { try { this.es.close(); } catch (_) {} }
        this.es = null;
      },

      retry(idx) {
        const userMsg = [...this.messages].slice(0, idx).reverse().find(m => m.role === 'user');
        if (userMsg) {
          this.messages = this.messages.slice(0, idx);
          this.send(userMsg.text);
        }
      },

      resetAgentStatuses() {
        this.agents.forEach(a => { a.status = 'idle'; a.progress = 0; a.lastMsg = ''; });
      },
      toggleTrace(i) { this.messages[i].traceOpen = !this.messages[i].traceOpen; },

      // ── B4：记下到命运日记 ──
      markToJournal(kind, text, m) {
        if (!window.SuanJournal) { alert('命运日记模块未加载'); return; }
        const profile = this.profile || {};
        const recallDays = (kind === 'advice' || kind === 'consensus') ? 90 : 180;
        const it = window.SuanJournal.add({
          kind,
          text,
          source: {
            question: m && m.firstQuestion ? m.firstQuestion : (this.messages.find(x => x.role === 'user') || {}).text,
            profileName: profile.name || '匿名',
          },
          sessionId: this.sid,
          recallAfterDays: recallDays,
        });
        // 视觉反馈
        const el = window.event && window.event.target;
        if (el && el.classList) {
          el.classList.add('journaled');
          setTimeout(() => el.classList.remove('journaled'), 1500);
        }
        this._toast(`已记入命运日记 · 将于 ${recallDays} 天后回访`);
      },

      recordVerdict(m) {
        if (!window.SuanJournal) return;
        const profile = this.profile || {};
        const summary = m.text ? m.text.slice(0, 200) : (m.consensus || []).join(' / ');
        const it = window.SuanJournal.add({
          kind: 'verdict',
          text: summary,
          advice: (m.advice || []).join(' / '),
          source: {
            question: (this.messages.find(x => x.role === 'user') || {}).text,
            profileName: profile.name || '匿名',
            confidence: m.confidence,
          },
          sessionId: this.sid,
          recallAfterDays: 90,
        });
        this._toast('已记下整次判官 · 90 天后回访');
      },

      // ── B5：生成结论卡 PNG ──
      async shareCard(m) {
        if (!window.SuanShareCard) { alert('结论卡模块未加载'); return; }
        const profile = this.profile || {};
        const userQ = (this.messages.find(x => x.role === 'user') || {}).text || '一段研判';

        // 找最有代表性的一句结论
        let conclusion = '';
        if (m.consensus && m.consensus.length) conclusion = m.consensus[0];
        else if (m.advice && m.advice.length) conclusion = m.advice[0];
        else if (m.text) {
          // 取 narrative 第一段非空文本
          const firstPara = m.text.split(/\n\n+/).find(p => p && !/^[\s>#-]/.test(p));
          conclusion = (firstPara || m.text).slice(0, 80);
        }

        const date = (window.SuanEnhance && window.SuanEnhance.yearGanzhi)
          ? `${window.SuanEnhance.yearGanzhi(new Date())}年 · ${window.SuanEnhance.currentSolarTerm(new Date())}`
          : new Date().toISOString().slice(0,10);

        const profileLine = (profile.gender === 'male' ? '乾造' : profile.gender === 'female' ? '坤造' : '中性')
          + ' · ' + (profile.date || '') + ' · ' + (profile.place || '');

        const council = (m.trace && m.trace.steps || [])
          .filter(s => s.kind === 'expert')
          .map(s => ({ bazi:'八字', ziwei:'紫微', astrology:'占星', tarot:'塔罗',
                       numerology:'数命', yijing:'易经', fengshui:'风水', liunian:'流年' }[s.agent] || s.agent))
          .filter((v, i, a) => v && a.indexOf(v) === i)
          .slice(0, 4);

        await window.SuanShareCard.downloadCard({
          title: userQ.slice(0, 22),
          conclusion: conclusion.slice(0, 60),
          confidence: m.confidence,
          profileLine,
          councilSig: council,
          date,
          source: '算 suan · 中西命理研判',
        });
      },

      _toast(text) {
        let el = document.getElementById('suan-toast');
        if (!el) {
          el = document.createElement('div');
          el.id = 'suan-toast';
          el.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--paper);padding:12px 22px;font-family:var(--font-serif-cn);font-size:13px;letter-spacing:0.14em;border-radius:2px;z-index:9999;opacity:0;transition:opacity .3s ease;';
          document.body.appendChild(el);
        }
        el.textContent = text;
        el.style.opacity = '1';
        clearTimeout(el._t);
        el._t = setTimeout(() => { el.style.opacity = '0'; }, 2400);
      },
      element(s) { return pickElementFromGanZhi(s); },
    }));

    /* ---------- feedbackForm ---------- */
    Alpine.data('feedbackForm', () => ({
      rating: 0, tags: [], text: '',
      tagOptions: ['表述清晰','典籍可溯','结论中肯','分析有深度','流派标注明确','需要更具体','偏离问题','证据不足'],
      submitted: false, submitting: false,
      toggleTag(t) {
        if (this.tags.includes(t)) this.tags = this.tags.filter(x => x !== t);
        else this.tags.push(t);
      },
      async submit(sid) {
        if (this.rating === 0) return;
        this.submitting = true;
        try {
          await fetch(`${API_BASE}/feedback`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ session_id: sid || '_unknown', rating: this.rating, tags: this.tags, text: this.text }),
          });
        } catch (e) {}
        this.submitting = false;
        this.submitted = true;
      },
    }));

    // 暴露给页面 inline script 用
    window.SUAN = Object.assign(window.SUAN || {}, {
      ELEMENTS, COUNCIL, SCENARIOS,
      formatDateTime, pickElementFromGanZhi,
      $store: $store,
    });
  }

  // 双保险注册：alpinejs 还没 ready 就监听 alpine:init；已 ready 就立即注册
  if (window.Alpine) {
    registerAlpineApp();
  } else {
    document.addEventListener('alpine:init', registerAlpineApp);
    // 兜底：DOMContentLoaded 之后再次尝试（防止 alpine:init 在脚本加载之前就触发过）
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        if (window.Alpine && !window.__SUAN_REGISTERED__) registerAlpineApp();
      });
    } else {
      // 文档已 ready，等下一个 tick 再尝试
      setTimeout(() => {
        if (window.Alpine && !window.__SUAN_REGISTERED__) registerAlpineApp();
      }, 0);
    }
  }
})();
