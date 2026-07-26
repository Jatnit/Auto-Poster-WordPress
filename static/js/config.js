      // ============================================================================
      // SECRET FIELDS
      // Secrets (WordPress password, Gemini API key) are never sent back by the
      // server. The input stays empty when a value is already stored; leaving it
      // empty on save means "keep the stored secret".
      // ============================================================================
      const SECRET_PLACEHOLDER = "(đã lưu — để trống nếu không đổi)";

      function applySecretFieldState(inputId, isSet) {
        const el = document.getElementById(inputId);
        if (!el) return;
        el.value = "";
        el.placeholder = isSet ? SECRET_PLACEHOLDER : "";
      }

      // Save configuration
      async function saveConfig() {
        const providerEl = document.getElementById("aiProviderSelect");
        const config = {
          ai_provider: providerEl ? providerEl.value : "gemini_web",
          gemini_prompt: document.getElementById("geminiPrompt").value,
          wp_username: document.getElementById("wpUsername").value,
          wp_password: document.getElementById("wpPassword").value,
          wp_login_url: document.getElementById("wpLoginUrl").value,
          wp_admin_url: document.getElementById("wpAdminUrl").value,
          schedule_start_date:
            document.getElementById("scheduleStartDate").value || "",
          schedule_end_date:
            document.getElementById("scheduleEndDate").value || "",
          category_name:
            document.getElementById("categoryName").value.trim() ||
            "Tin tức",
          auto_set_seo_keyword:
            document.getElementById("autoSetSeoKeyword").checked,
          auto_insert_inline_images:
            document.getElementById("autoInsertInlineImages").checked,
          auto_set_featured_image:
            document.getElementById("autoSetFeaturedImage").checked,
          auto_select_category:
            document.getElementById("autoSelectCategory").checked,
          auto_add_tags: document.getElementById("autoAddTags").checked,
          posts_per_day:
            parseInt(document.getElementById("postsPerDay").value) || 2,
          delay_between_requests:
            parseInt(document.getElementById("delayBetweenRequests").value) ||
            30,
          content_min_valid_words:
            Math.max(
              1,
              parseInt(document.getElementById("contentMinValidWords").value) ||
                1401,
            ),
          headless_mode: document.getElementById("headlessMode").checked,
        };

        try {
          const response = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config),
          });

          const result = await response.json();
          if (response.ok && result.success) {
            showToast("Cấu hình đã được lưu!", "success");
            // Never persist secrets in localStorage — any extension or XSS
            // on this origin can read it.
            const { wp_password, gemini_api_key, ...safeConfig } = config;
            localStorage.setItem(
              "wp_auto_config",
              JSON.stringify(safeConfig),
            );
            applySecretFieldState(
              "wpPassword",
              Boolean(wp_password) || Boolean(result.wp_password_set),
            );
          } else {
            showToast(result.message || "Không thể lưu cấu hình", "error");
          }
        } catch (e) {
          showToast("Lỗi khi lưu cấu hình", "error");
        }
      }

      // Load configuration
      async function loadConfig() {
        // Try loading from localStorage first
        const savedConfig = localStorage.getItem("wp_auto_config");
        if (savedConfig) {
          const config = JSON.parse(savedConfig);

          // AI Provider
          const providerEl = document.getElementById("aiProviderSelect");
          if (providerEl && config.ai_provider) {
            providerEl.value = config.ai_provider;
          }

          // Gemini Prompt
          if (config.gemini_prompt) {
            document.getElementById("geminiPrompt").value =
              config.gemini_prompt;
          }

          document.getElementById("wpUsername").value =
            config.wp_username || "";
          // Password intentionally not restored from localStorage.
          document.getElementById("wpLoginUrl").value =
            config.wp_login_url || "";
          document.getElementById("wpAdminUrl").value =
            config.wp_admin_url || "";
          document.getElementById("categoryName").value =
            config.category_name || "Tin tức";
          document.getElementById("autoSetSeoKeyword").checked =
            config.auto_set_seo_keyword !== false;
          document.getElementById("autoInsertInlineImages").checked =
            config.auto_insert_inline_images !== false;
          document.getElementById("autoSetFeaturedImage").checked =
            config.auto_set_featured_image === true;
          document.getElementById("autoSelectCategory").checked =
            config.auto_select_category !== false;
          document.getElementById("autoAddTags").checked =
            config.auto_add_tags !== false;
          document.getElementById("postsPerDay").value =
            config.posts_per_day || 2;
          document.getElementById("delayBetweenRequests").value =
            config.delay_between_requests || 30;
          document.getElementById("contentMinValidWords").value =
            config.content_min_valid_words || 1401;
          document.getElementById("headlessMode").checked =
            config.headless_mode || false;
          document.getElementById("scheduleStartDate").value =
            config.schedule_start_date || "";
          document.getElementById("scheduleEndDate").value =
            config.schedule_end_date || "";
          ensureDefaultScheduleDates();
          syncScheduleDaysFromDates();
        }

        // Also try to load from server
        try {
          const response = await fetch("/api/config");
          const config = await response.json();

          document.getElementById("wpUsername").value =
            config.wp_username || document.getElementById("wpUsername").value;
          // The server reports only whether a password is stored, never its value.
          applySecretFieldState("wpPassword", config.wp_password_set === true);
          document.getElementById("wpLoginUrl").value =
            config.wp_login_url || document.getElementById("wpLoginUrl").value;
          document.getElementById("wpAdminUrl").value =
            config.wp_admin_url || document.getElementById("wpAdminUrl").value;
          // AI Provider (server)
          const providerEl2 = document.getElementById("aiProviderSelect");
          if (providerEl2 && config.ai_provider) {
            providerEl2.value = config.ai_provider;
          }
          document.getElementById("categoryName").value =
            config.category_name || "Tin tức";
          document.getElementById("autoSetSeoKeyword").checked =
            config.auto_set_seo_keyword !== false;
          document.getElementById("autoInsertInlineImages").checked =
            config.auto_insert_inline_images !== false;
          document.getElementById("autoSetFeaturedImage").checked =
            config.auto_set_featured_image === true;
          document.getElementById("autoSelectCategory").checked =
            config.auto_select_category !== false;
          document.getElementById("autoAddTags").checked =
            config.auto_add_tags !== false;
          document.getElementById("postsPerDay").value =
            config.posts_per_day || document.getElementById("postsPerDay").value || 2;
          document.getElementById("delayBetweenRequests").value =
            config.delay_between_requests ||
            document.getElementById("delayBetweenRequests").value ||
            30;
          document.getElementById("contentMinValidWords").value =
            config.content_min_valid_words ||
            document.getElementById("contentMinValidWords").value ||
            1401;
          document.getElementById("headlessMode").checked =
            typeof config.headless_mode === "boolean"
              ? config.headless_mode
              : document.getElementById("headlessMode").checked;
          if (config.gemini_prompt) {
            document.getElementById("geminiPrompt").value = config.gemini_prompt;
          }
          if (config.schedule_start_date) {
            document.getElementById("scheduleStartDate").value =
              config.schedule_start_date;
          }
          if (config.schedule_end_date) {
            document.getElementById("scheduleEndDate").value =
              config.schedule_end_date;
          }
          ensureDefaultScheduleDates();
          syncScheduleDaysFromDates();
        } catch (e) {
          console.log("Could not load config from server");
        }

        // Load topics from localStorage safely
        loadTopics();
      }
