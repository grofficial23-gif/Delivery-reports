(function () {
  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    });
  }

  function syncTelegramAppearance(webApp) {
    if (!webApp) {
      return;
    }

    var scheme = webApp.colorScheme === "dark" ? "dark" : "light";
    document.body.dataset.colorScheme = scheme;
    document.documentElement.style.colorScheme = scheme;

    var headerColor = scheme === "dark" ? "#0a0a0a" : "#ffffff";
    var backgroundColor = scheme === "dark" ? "#0a0a0a" : "#ffffff";

    if (typeof webApp.setHeaderColor === "function") {
      try {
        webApp.setHeaderColor(headerColor);
      } catch (error) {
        // Ignore theme API errors and keep the app usable.
      }
    }

    if (typeof webApp.setBackgroundColor === "function") {
      try {
        webApp.setBackgroundColor(backgroundColor);
      } catch (error) {
        // Ignore theme API errors and keep the app usable.
      }
    }

    if (typeof webApp.setBottomBarColor === "function") {
      try {
        webApp.setBottomBarColor(backgroundColor);
      } catch (error) {
        // Ignore theme API errors and keep the app usable.
      }
    }
  }

  function updateAuthStatus(message, isError) {
    var node = document.getElementById("mini-auth-status");
    if (!node) {
      return;
    }
    node.textContent = message;
    node.style.background = isError ? "rgba(239, 68, 68, 0.12)" : "";
    node.style.color = isError ? "#ef4444" : "";
  }

  async function waitForInitData(tg, maxAttempts) {
    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      if (tg.initData) {
        return tg.initData;
      }
      await new Promise(function (resolve) { window.setTimeout(resolve, 300); });
    }
    return null;
  }

  async function ensureMiniAppAuth() {
    var isAuthRequired = document.body.dataset.authRequired === "true";
    if (!isAuthRequired) {
      return;
    }

    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) {
      updateAuthStatus("Откройте приложение внутри Telegram, чтобы войти автоматически.", true);
      return;
    }

    try {
      tg.ready();
      if (typeof tg.expand === "function") { tg.expand(); }
      if (typeof tg.disableVerticalSwipes === "function") { tg.disableVerticalSwipes(); }
      syncTelegramAppearance(tg);

      // Показываем загрузку пока ждём initData
      updateAuthStatus("Подключаюсь к Telegram...");
      showLoading();

      var initData = await waitForInitData(tg, 10);  // до 3 секунд
      if (initData) {
        sessionStorage.setItem('tg_init_data', initData);
      } else {
        initData = sessionStorage.getItem('tg_init_data');
      }
      hideLoading();

      if (!initData) {
        updateAuthStatus("Telegram не передал данные сессии. Закройте приложение и откройте заново через кнопку в боте.", true);
        return;
      }

      updateAuthStatus("Открываю ваш личный кабинет...");
      showLoading();

      var response = await postJson("/auth/telegram", { init_data: initData });
      var payload = await response.json();
      hideLoading();

      if (!response.ok || !payload.ok) {
        updateAuthStatus(payload.error || "Не удалось подтвердить сессию Telegram. Попробуйте позже.", true);
        return;
      }

      // Успех — убираем auth экран без полного reload
      window.location.replace("/dashboard");

    } catch (error) {
      hideLoading();
      updateAuthStatus("Ошибка соединения. Проверьте интернет и откройте Mini App заново.", true);
    }
  }

  async function copyTextFromTarget(targetId, button) {
    var target = document.getElementById(targetId);
    if (!target) {
      return;
    }

    var text = target.value || target.textContent || "";
    if (!text.trim()) {
      return;
    }

    var originalLabel = button ? button.textContent : "";
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else if (target.select) {
        target.focus();
        target.select();
        document.execCommand("copy");
      }
      if (button) {
        button.textContent = "Скопировано";
        window.setTimeout(function () {
          button.textContent = originalLabel;
        }, 1600);
      }
    } catch (error) {
      if (button) {
        button.textContent = "Не удалось";
        window.setTimeout(function () {
          button.textContent = originalLabel;
        }, 1600);
      }
    }
  }

  /* ── Toast Notification System ── */
  function ensureToastContainer() {
    var container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    return container;
  }

  function showToast(message, type) {
    var container = ensureToastContainer();
    var toast = document.createElement("div");
    toast.className = "toast " + (type === "error" ? "error" : "success");
    toast.textContent = message;
    container.appendChild(toast);
    window.setTimeout(function () {
      toast.classList.add("hide");
      window.setTimeout(function () {
        toast.remove();
      }, 300);
    }, 2000); // 2 seconds as requested by user
  }
  window.showToast = showToast;

  /* ── Loading Overlay ── */
  function ensureLoadingOverlay() {
    var overlay = document.getElementById("loading-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "loading-overlay";
      overlay.className = "loading-overlay";
      overlay.innerHTML = '<div class="loading-spinner"></div>';
      document.body.appendChild(overlay);
    }
    return overlay;
  }

  function showLoading() {
    ensureLoadingOverlay().classList.add("active");
  }

  function hideLoading() {
    var overlay = document.getElementById("loading-overlay");
    if (overlay) {
      overlay.classList.remove("active");
    }
  }

  /* ── Show notice from URL param as toast ── */
  function showNoticeFromUrl() {
    var params = new URLSearchParams(window.location.search);
    var notice = params.get("notice");
    if (notice) {
      showToast(notice, "success");
      // Clean the URL without reloading
      var cleanUrl = window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
      tg.ready();
      syncTelegramAppearance(tg);
      if (typeof tg.expand === "function") {
        tg.expand();
      }
      if (typeof tg.onEvent === "function") {
        tg.onEvent("themeChanged", function () {
          syncTelegramAppearance(tg);
        });
      }
    }

    document.querySelectorAll(".copy-trigger").forEach(function (button) {
      button.addEventListener("click", function () {
        copyTextFromTarget(button.dataset.copyTarget, button);
      });
    });

    showNoticeFromUrl();
    ensureMiniAppAuth();
  });
})();

/* ========================================================================= */
/* DIGEST LIGHT THEME: DNA Wave Canvas                                       */
/* ========================================================================= */
document.addEventListener('DOMContentLoaded', function() {
  const canvas = document.getElementById('dna-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  
  let width, height;
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  const particles = [];
  const particleCount = 600; // More particles for dense white spiral
  
  for(let i=0; i<particleCount; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 2 + 0.5,
      speedX: (Math.random() - 0.5) * 0.3,
      speedY: (Math.random() - 0.5) * 0.3,
      phase: Math.random() * Math.PI * 2,
      isAccent: Math.random() > 0.85 // 15% of particles are lime green
    });
  }

  let time = 0;
  function render() {
    ctx.clearRect(0, 0, width, height);
    time += 0.005;
    
    const centerY = height / 2;
    
    particles.forEach(p => {
      p.x += p.speedX;
      p.y += p.speedY;
      
      if(p.x > width) p.x = 0;
      if(p.x < 0) p.x = width;
      if(p.y > height) p.y = 0;
      if(p.y < 0) p.y = height;
      
      const dx = p.x - width/2;
      const wave = Math.sin(dx * 0.004 + time + p.phase) * 180;
      const wave2 = Math.cos(dx * 0.004 + time + p.phase) * 180;
      
      // Strand 1
      ctx.beginPath();
      ctx.arc(p.x, centerY + wave + p.y*0.05, p.size, 0, Math.PI * 2);
      ctx.fillStyle = p.isAccent ? 'rgba(163, 230, 53, 0.9)' : 'rgba(200, 205, 210, 0.6)';
      ctx.fill();
      
      // Strand 2
      ctx.beginPath();
      ctx.arc(p.x, centerY + wave2 + p.y*0.05, p.size * 0.8, 0, Math.PI * 2);
      ctx.fillStyle = p.isAccent ? 'rgba(132, 204, 22, 0.7)' : 'rgba(220, 225, 230, 0.5)';
      ctx.fill();
      
      // Draw connecting lines for accents
      if (p.isAccent && Math.random() > 0.98) {
        ctx.beginPath();
        ctx.moveTo(p.x, centerY + wave + p.y*0.05);
        ctx.lineTo(p.x, centerY + wave2 + p.y*0.05);
        ctx.strokeStyle = 'rgba(163, 230, 53, 0.1)';
        ctx.stroke();
      }
    });
    
    requestAnimationFrame(render);
  }
  render();
});
