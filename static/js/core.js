      // ============================================================================
      // MATRIX RAIN EFFECT
      // ============================================================================

      function initMatrixRain() {
        const canvas = document.getElementById("matrixCanvas");
        if (!canvas || window.getComputedStyle(canvas).display === "none") {
          return;
        }
        const ctx = canvas.getContext("2d");

        // Set canvas size
        function resize() {
          canvas.width = window.innerWidth;
          canvas.height = window.innerHeight;
        }
        resize();
        window.addEventListener("resize", resize);

        // Binary characters
        const chars = "01";
        const fontSize = 14;
        const columns = Math.floor(canvas.width / fontSize);

        // Array to track y position of each column
        const drops = [];
        for (let i = 0; i < columns; i++) {
          drops[i] = Math.random() * -100;
        }

        // Speed variation for each column
        const speeds = [];
        for (let i = 0; i < columns; i++) {
          speeds[i] = 0.5 + Math.random() * 1.5;
        }

        function draw() {
          // Semi-transparent black to create fade effect
          ctx.fillStyle = "rgba(0, 0, 0, 0.05)";
          ctx.fillRect(0, 0, canvas.width, canvas.height);

          // Green text
          ctx.font = fontSize + 'px "JetBrains Mono", monospace';

          for (let i = 0; i < drops.length; i++) {
            // Random binary character
            const char = chars[Math.floor(Math.random() * chars.length)];

            // Calculate x position
            const x = i * fontSize;
            const y = drops[i] * fontSize;

            // Brightness based on position (newer = brighter)
            const brightness = Math.min(255, 100 + Math.random() * 155);
            ctx.fillStyle = `rgb(0, ${brightness}, 0)`;

            // Draw character
            ctx.fillText(char, x, y);

            // Add glow effect for some characters
            if (Math.random() > 0.98) {
              ctx.fillStyle = "rgba(0, 255, 0, 0.8)";
              ctx.fillText(char, x, y);
            }

            // Move drop down
            drops[i] += speeds[i];

            // Reset drop to top with random delay
            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
              drops[i] = 0;
              speeds[i] = 0.5 + Math.random() * 1.5;
            }
          }
        }

        // Animate. Driven by requestAnimationFrame so the browser suspends it
        // when the tab is hidden — the machine is busy running Playwright at
        // the same time, and a permanent 30fps canvas loop is not free.
        const FRAME_INTERVAL_MS = 33;
        let lastFrame = 0;
        let rafId = null;

        function isVisible() {
          return (
            !document.hidden &&
            window.getComputedStyle(canvas).display !== "none"
          );
        }

        function frame(timestamp) {
          rafId = requestAnimationFrame(frame);
          if (!isVisible()) return;
          if (timestamp - lastFrame < FRAME_INTERVAL_MS) return;
          lastFrame = timestamp;
          draw();
        }

        function start() {
          if (rafId === null) {
            lastFrame = 0;
            rafId = requestAnimationFrame(frame);
          }
        }

        function stop() {
          if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
          }
        }

        document.addEventListener("visibilitychange", () => {
          if (document.hidden) stop();
          else start();
        });

        start();
      }

      // Topics storage
      let topics = [];
      let isRunning = false;
      let statusInterval = null;
      let checklistRows = [];
      let checklistProcessedLogCount = 0;
      // Log cursors. The server returns only entries newer than lastLogSeq;
      // the two "processed" cursors de-duplicate within each consumer.
      let lastLogSeq = 0;
      let lastRenderedLogSeq = 0;
      let checklistProcessedLogSeq = 0;
      let activeContentPost = null;
      let activeWpPost = null;
      let currentPhase = "";
      const postTitleToIndex = {};
      const CHECKLIST_MAX_ROWS = 500;

      // Initialize
      function toggleTheme() {
        const body = document.body;
        const isLight = body.classList.toggle("light-theme");
        document.getElementById("themeIcon").className = isLight ? "fas fa-moon toggle-icon" : "fas fa-sun toggle-icon";
        document.getElementById("themeLabel").textContent = isLight ? "Dark" : "Light";
        localStorage.setItem("wp_theme", isLight ? "light" : "hacker");
      }

      function loadSavedTheme() {
        const saved = localStorage.getItem("wp_theme");
        if (saved === "light") {
          document.body.classList.add("light-theme");
          document.getElementById("themeIcon").className = "fas fa-moon toggle-icon";
          document.getElementById("themeLabel").textContent = "Dark";
        } else {
          document.getElementById("themeIcon").className = "fas fa-sun toggle-icon";
          document.getElementById("themeLabel").textContent = "Light";
        }
      }

      // ============================================================================
      // WAKE LOCK — giữ màn hình không tắt khi đang chạy automation.
      // Chỉ hoạt động khi tab đang active; nếu user chuyển tab thì browser sẽ
      // tự release, và khi quay lại tab này sẽ tự acquire lại.
      // ============================================================================
      let wakeLock = null;

      async function requestWakeLock() {
        if (!("wakeLock" in navigator)) {
          console.warn("Wake Lock API không được trình duyệt hỗ trợ");
          return false;
        }
        try {
          wakeLock = await navigator.wakeLock.request("screen");
          wakeLock.addEventListener("release", () => {
            // Browser có thể auto-release (ví dụ khi tab ẩn). Reset biến để
            // visibilitychange có thể xin lại.
            wakeLock = null;
          });
          return true;
        } catch (err) {
          console.warn("Không xin được wake lock:", err.message);
          return false;
        }
      }

      async function releaseWakeLock() {
        if (wakeLock) {
          try {
            await wakeLock.release();
          } catch (_) {}
          wakeLock = null;
        }
      }

      // Khi tab quay lại visible và automation đang chạy thì xin lại wake lock
      document.addEventListener("visibilitychange", async () => {
        if (document.visibilityState === "visible" && isRunning && !wakeLock) {
          await requestWakeLock();
        }
      });

      document.addEventListener("DOMContentLoaded", () => {
        loadSavedTheme();
        initMatrixRain();
        ensureDefaultScheduleDates();
        loadConfig();
        loadTopics();
        updateStats();
        loadPresetList();
        initTypingSound();
        resetChecklistState();
      });
