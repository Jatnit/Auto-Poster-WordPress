      // ============================================================================
      // PRESET MANAGEMENT
      // ============================================================================

      async function loadPresetList() {
        try {
          const response = await fetch("/api/presets");
          const result = await response.json();
          if (result.success) {
            const select = document.getElementById("presetSelect");
            select.innerHTML =
              '<option value="">-- Chọn site đã lưu --</option>';
            result.presets.forEach((name) => {
              const option = document.createElement("option");
              option.value = name;
              option.textContent = name;
              select.appendChild(option);
            });
          }
        } catch (e) {
          console.log("Could not load presets");
        }
      }

      async function loadPreset() {
        const select = document.getElementById("presetSelect");
        const name = select.value;
        if (!name) return;

        try {
          const response = await fetch(
            `/api/presets/${encodeURIComponent(name)}`,
          );
          const result = await response.json();
          if (result.success) {
            const data = result.data;
            document.getElementById("wpUsername").value =
              data.wp_username || "";
            document.getElementById("wpPassword").value =
              data.wp_password || "";
            document.getElementById("wpLoginUrl").value =
              data.wp_login_url || "";
            document.getElementById("wpAdminUrl").value =
              data.wp_admin_url || "";
            document.getElementById("categoryName").value =
              data.category_name || "Tin tức";
            document.getElementById("autoSetSeoKeyword").checked =
              data.auto_set_seo_keyword !== false;
            document.getElementById("autoInsertInlineImages").checked =
              data.auto_insert_inline_images !== false;
            document.getElementById("autoSetFeaturedImage").checked =
              data.auto_set_featured_image === true;
            document.getElementById("autoSelectCategory").checked =
              data.auto_select_category !== false;
            document.getElementById("autoAddTags").checked =
              data.auto_add_tags !== false;
            document.getElementById("contentMinValidWords").value =
              data.content_min_valid_words || 1401;
            if (data.gemini_prompt) {
              document.getElementById("geminiPrompt").value =
                data.gemini_prompt;
            }
            showToast(`Đã tải cấu hình: ${name}`, "success");
          }
        } catch (e) {
          showToast("Không thể tải cấu hình", "error");
        }
      }

      async function saveCurrentAsPreset() {
        const wpLoginUrl = document.getElementById("wpLoginUrl").value;
        if (!wpLoginUrl) {
          showToast("Vui lòng nhập WordPress Login URL trước", "warning");
          return;
        }

        // Extract domain for preset name
        let presetName = "";
        try {
          const url = new URL(wpLoginUrl);
          presetName = url.hostname.replace("www.", "");
        } catch {
          presetName = await showPromptDialog(
            "Nhập tên cho cấu hình:",
            "my-site",
            {
              title: "Lưu cấu hình",
              placeholder: "Tên cấu hình...",
            },
          );
        }

        if (!presetName) {
          presetName = await showPromptDialog(
            "Nhập tên cho cấu hình:",
            "my-site",
            {
              title: "Lưu cấu hình",
              placeholder: "Tên cấu hình...",
            },
          );
        }

        if (!presetName) return;

        const data = {
          wp_username: document.getElementById("wpUsername").value,
          wp_password: document.getElementById("wpPassword").value,
          wp_login_url: document.getElementById("wpLoginUrl").value,
          wp_admin_url: document.getElementById("wpAdminUrl").value,
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
          gemini_prompt: document.getElementById("geminiPrompt").value,
          content_min_valid_words:
            Math.max(
              1,
              parseInt(document.getElementById("contentMinValidWords").value) ||
                1401,
            ),
        };

        try {
          const response = await fetch(
            `/api/presets/${encodeURIComponent(presetName)}`,
            {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(data),
            },
          );

          const result = await response.json();
          if (result.success) {
            showToast(`Đã lưu: ${presetName}`, "success");
            loadPresetList();
            // Select the saved preset
            setTimeout(() => {
              document.getElementById("presetSelect").value = presetName;
            }, 100);
          } else {
            showToast("Không thể lưu cấu hình", "error");
          }
        } catch (e) {
          showToast("Lỗi kết nối", "error");
        }
      }

      async function deleteCurrentPreset() {
        const select = document.getElementById("presetSelect");
        const name = select.value;
        if (!name) {
          showToast("Vui lòng chọn preset để xóa", "warning");
          return;
        }

        const confirmed = await showConfirmDialog(
          `Bạn có chắc muốn xóa cấu hình "${name}"?`,
          {
            title: "Xóa cấu hình",
            type: "danger",
            confirmText: "Xóa",
            cancelText: "Hủy",
          },
        );

        if (!confirmed) return;

        try {
          const response = await fetch(
            `/api/presets/${encodeURIComponent(name)}`,
            {
              method: "DELETE",
            },
          );

          const result = await response.json();
          if (result.success) {
            showToast(`Đã xóa: ${name}`, "success");
            loadPresetList();
          } else {
            showToast("Không thể xóa", "error");
          }
        } catch (e) {
          showToast("Lỗi kết nối", "error");
        }
      }

      // Render content list as accordion
