/**
 * PM DIGEST V2 — Shared UI
 * Purpose:
 *   Theme bootstrap, background canvas, demo modal, Telegram WebApp theming.
 *   Loaded by landing_v2.html and dashboard_v2.html.
 *   All behaviour is opt-in: each feature activates only when its DOM elements exist.
 * Rollback:
 *   Omit script tag from any V1 template; V1 app.js is unchanged.
 * No side effects on any V1 page.
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Theme bootstrap
  // Production-safe themes only: dark-lime, light-lime, wave-blue.
  // Premium themes excluded from landing.
  // ---------------------------------------------------------------------------
  var SKEY = 'pm-digest-v2-theme';
  var THEMES = ['dark-lime', 'light-lime', 'wave-blue'];

  function resolveTheme() {
    // 1. Saved preference — wins over Telegram colorScheme so PRO/TEAM users
    //    can persist Wave Blue across Mini App reloads.
    try {
      var saved = localStorage.getItem(SKEY);
      if (saved && THEMES.indexOf(saved) !== -1) return saved;
    } catch (_) {}

    // 2. Telegram Mini App colorScheme (only when no saved preference)
    try {
      var tg = window.Telegram && window.Telegram.WebApp;
      if (tg && tg.colorScheme) {
        return tg.colorScheme === 'light' ? 'light-lime' : 'dark-lime';
      }
    } catch (_) {}

    // 3. System prefers-color-scheme
    try {
      if (window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light-lime';
      }
    } catch (_) {}

    return 'dark-lime';
  }

  function applyTheme(theme) {
    if (THEMES.indexOf(theme) === -1) theme = 'dark-lime';
    document.body.dataset.theme = theme;
    try { localStorage.setItem(SKEY, theme); } catch (_) {}
    syncThemeBtns(theme);
    if (typeof updateCanvasColors === 'function') updateCanvasColors();
  }

  function syncThemeBtns(theme) {
    document.querySelectorAll('[data-v2-theme-btn]').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.v2ThemeBtn === theme);
    });
  }

  // Wire theme switcher buttons
  function initThemeSwitcher() {
    document.querySelectorAll('[data-v2-theme-btn]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyTheme(btn.dataset.v2ThemeBtn);
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Background canvas — dots + proximity lines
  // Identical logic to prototype; reads --c-dot / --c-line / --c-ambient.
  // ---------------------------------------------------------------------------
  var canvas, ctx, W, H, rafId = 0, dots = [];
  var cDot = '', cLine = '', cAmb = '';
  var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function cssv(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }

  function updateCanvasColors() {
    cDot  = cssv('--c-dot');
    cLine = cssv('--c-line');
    cAmb  = cssv('--c-ambient');
    buildDots();
  }

  function buildDots() {
    var theme   = document.body.dataset.theme;
    var dark    = theme === 'dark-lime';
    var ltLime  = theme === 'light-lime';
    var density = dark ? 10000 : (ltLime ? 12000 : 18000);
    var minN    = dark ? 58 : (ltLime ? 52 : 36);
    var n = Math.max(minN, Math.floor((W * H) / density));
    dots = [];
    for (var i = 0; i < n; i++) {
      dots.push({
        x:  Math.random() * W,
        y:  Math.random() * H,
        vx: (Math.random() - 0.5) * 0.30,
        vy: (Math.random() - 0.5) * 0.20,
        r:  dark ? (1.1 + Math.random() * 1.7) : (0.8 + Math.random() * 1.3),
        accent: Math.random() < (dark ? 0.30 : (ltLime ? 0.28 : 0.18)),
        alpha:  dark   ? (0.32 + Math.random() * 0.46)
              : ltLime ? (0.26 + Math.random() * 0.36)
              :           (0.14 + Math.random() * 0.22),
      });
    }
  }

  function resizeCanvas() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width  = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    updateCanvasColors();
  }

  var LINE_D = 170;

  function drawFrame() {
    ctx.clearRect(0, 0, W, H);

    // Light-lime: subtle grid
    if (document.body.dataset.theme === 'light-lime') {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = 'rgba(72, 108, 42, 0.092)';
      ctx.lineWidth = 0.5;
      var gs = 44;
      for (var x = gs; x < W; x += gs) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (var y = gs; y < H; y += gs) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }
    }

    // Move dots
    for (var i = 0; i < dots.length; i++) {
      var d = dots[i];
      d.x += d.vx; d.y += d.vy;
      if (d.x < -4)    d.x = W + 4;
      if (d.x > W + 4) d.x = -4;
      if (d.y < -4)    d.y = H + 4;
      if (d.y > H + 4) d.y = -4;
    }

    // Lines
    var th = document.body.dataset.theme;
    var darkLine  = th === 'dark-lime';
    var ltLimeLine = th === 'light-lime';
    ctx.lineWidth = darkLine ? 0.7 : (ltLimeLine ? 0.55 : 0.5);
    var lineAlphaMult = darkLine ? 0.30 : (ltLimeLine ? 0.22 : 0.14);
    for (var ii = 0; ii < dots.length; ii++) {
      for (var jj = ii + 1; jj < dots.length; jj++) {
        var dx = dots[ii].x - dots[jj].x;
        var dy = dots[ii].y - dots[jj].y;
        var d2 = dx * dx + dy * dy;
        if (d2 < LINE_D * LINE_D) {
          ctx.globalAlpha = (1 - Math.sqrt(d2) / LINE_D) * lineAlphaMult;
          ctx.strokeStyle = cLine;
          ctx.beginPath();
          ctx.moveTo(dots[ii].x, dots[ii].y);
          ctx.lineTo(dots[jj].x, dots[jj].y);
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;

    // Dots
    var isDark = document.body.dataset.theme === 'dark-lime';
    var isLtLm = document.body.dataset.theme === 'light-lime';
    for (var k = 0; k < dots.length; k++) {
      var dot = dots[k];
      if (dot.accent) {
        ctx.shadowBlur  = isDark ? 14 : (isLtLm ? 8 : 5);
        ctx.shadowColor = cDot;
      }
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
      ctx.fillStyle   = dot.accent ? cDot : cAmb;
      ctx.globalAlpha = dot.alpha;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    ctx.globalAlpha = 1;

    if (!REDUCE && !document.hidden) rafId = requestAnimationFrame(drawFrame);
  }

  function startCanvas() { if (REDUCE) { drawFrame(); return; } if (!rafId) rafId = requestAnimationFrame(drawFrame); }
  function stopCanvas()  { if (rafId) { cancelAnimationFrame(rafId); rafId = 0; } }

  function initCanvas() {
    canvas = document.getElementById('v2-bg-canvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    document.addEventListener('visibilitychange', function () {
      document.hidden ? stopCanvas() : startCanvas();
    });

    if (window.ResizeObserver) {
      new ResizeObserver(function () { resizeCanvas(); }).observe(document.documentElement);
    } else {
      var rt = 0;
      window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(resizeCanvas, 80); });
    }

    requestAnimationFrame(function () { resizeCanvas(); startCanvas(); });
  }

  // ---------------------------------------------------------------------------
  // Demo modal
  // 4 steps, client-side only, no backend.
  // ---------------------------------------------------------------------------
  var DEMO_STEPS = [
    {
      ico: '📝',
      title: 'Заметка или голос',
      desc: 'Пишите текстовую заметку прямо в Telegram или отправьте голосовое — бот распознает и запомнит всё.'
    },
    {
      ico: '⚡',
      title: 'Парсинг и <mark>структура</mark>',
      desc: 'Бот автоматически разбирает данные по разделам: что сделано, риски, план на завтра — без ручной работы.'
    },
    {
      ico: '📋',
      title: 'Черновик готов',
      desc: 'Открывайте отчёт в Mini App, редактируйте поля и дополняйте детали перед финальной отправкой.'
    },
    {
      ico: '📤',
      title: 'Отправить или скопировать',
      desc: 'Отправьте черновик себе в Telegram, скопируйте текст или экспортируйте в PDF / Word одной кнопкой.'
    }
  ];

  var demoIdx = 0;

  function demoRender() {
    var s = DEMO_STEPS[demoIdx];
    var icoEl   = document.getElementById('demo-ico');
    var titleEl = document.getElementById('demo-title');
    var descEl  = document.getElementById('demo-desc');
    var prevBtn = document.getElementById('demo-prev');
    var nextLabel = document.getElementById('demo-next-label');
    if (icoEl)   icoEl.textContent  = s.ico;
    if (titleEl) titleEl.innerHTML  = s.title;
    if (descEl)  descEl.textContent = s.desc;
    document.querySelectorAll('.demo-pip').forEach(function (pip, i) {
      pip.classList.toggle('active', i === demoIdx);
    });
    if (prevBtn) {
      if (demoIdx === 0) prevBtn.classList.add('is-hidden');
      else prevBtn.classList.remove('is-hidden');
    }
    if (nextLabel) {
      nextLabel.textContent = (demoIdx === DEMO_STEPS.length - 1) ? 'Открыть бота' : 'Далее';
    }
  }

  function demoOpen() {
    demoIdx = 0;
    demoRender();
    var overlay = document.getElementById('demo-overlay');
    if (overlay) overlay.classList.add('open');
  }

  function demoClose() {
    var overlay = document.getElementById('demo-overlay');
    if (overlay) overlay.classList.remove('open');
  }

  function initDemoModal() {
    var openBtn  = document.getElementById('demo-btn');
    var closeBtn = document.getElementById('demo-close-btn');
    var prevBtn  = document.getElementById('demo-prev');
    var nextBtn  = document.getElementById('demo-next');
    var overlay  = document.getElementById('demo-overlay');

    if (openBtn)  openBtn.addEventListener('click', demoOpen);
    if (closeBtn) closeBtn.addEventListener('click', demoClose);
    if (overlay) {
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) demoClose();
      });
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') demoClose();
    });
    if (nextBtn) {
      nextBtn.addEventListener('click', function () {
        if (demoIdx < DEMO_STEPS.length - 1) { demoIdx++; demoRender(); }
        else {
          demoClose();
          // Navigate to bot if bot_url data attr is present
          var botUrl = document.body.dataset.botUrl;
          if (botUrl) window.open(botUrl, '_blank', 'noopener');
        }
      });
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', function () {
        if (demoIdx > 0) { demoIdx--; demoRender(); }
      });
    }
    if (overlay) demoRender();
  }

  // ---------------------------------------------------------------------------
  // Dashboard: mobile nav menu toggle (#v2-mobile-nav-btn / #v2-mobile-nav-menu)
  // Activates only when those elements exist (dashboard_v2.html).
  // ---------------------------------------------------------------------------
  function initMobileNav() {
    var btn  = document.getElementById('v2-mobile-nav-btn');
    var menu = document.getElementById('v2-mobile-nav-menu');
    if (!btn || !menu) return;
    btn.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', function (e) {
      if (!btn.contains(e.target) && !menu.contains(e.target)) {
        menu.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        menu.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Init on DOMContentLoaded
  // ---------------------------------------------------------------------------
  function init() {
    var theme = resolveTheme();
    applyTheme(theme);
    initThemeSwitcher();
    initCanvas();
    initDemoModal();
    initMobileNav();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

}());
