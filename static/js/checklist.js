      // ============================================================================
      // TYPEWRITER EFFECT WITH HACKER SOUND
      // ============================================================================

      // Audio context for typing sounds
      let audioContext = null;
      let typingSoundEnabled = true;
      let lastLogCount = 0;

      function initTypingSound() {
        // Initialize audio context on first user interaction
        document.addEventListener(
          "click",
          () => {
            if (!audioContext) {
              audioContext = new (
                window.AudioContext || window.webkitAudioContext
              )();
            }
          },
          { once: true },
        );
      }

      // Play typing beep sound
      function playTypingSound() {
        if (!audioContext || !typingSoundEnabled) return;

        try {
          const oscillator = audioContext.createOscillator();
          const gainNode = audioContext.createGain();

          oscillator.connect(gainNode);
          gainNode.connect(audioContext.destination);

          // Hacker terminal beep - short high frequency
          oscillator.frequency.value = 800 + Math.random() * 400; // 800-1200 Hz
          oscillator.type = "square";

          // Very short beep
          gainNode.gain.setValueAtTime(0.03, audioContext.currentTime);
          gainNode.gain.exponentialRampToValueAtTime(
            0.001,
            audioContext.currentTime + 0.05,
          );

          oscillator.start(audioContext.currentTime);
          oscillator.stop(audioContext.currentTime + 0.05);
        } catch (e) {
          // Ignore audio errors
        }
      }

      // Typewriter effect for a single log entry
      function typewriterEffect(element, text, speed = 15) {
        return new Promise((resolve) => {
          let index = 0;
          element.textContent = "";
          element.style.borderRight = "2px solid var(--accent-primary)";

          const type = () => {
            if (index < text.length) {
              element.textContent += text.charAt(index);
              playTypingSound();
              index++;

              // Vary speed slightly for more natural effect
              const delay = speed + Math.random() * 10;
              setTimeout(type, delay);
            } else {
              // Remove cursor after typing
              setTimeout(() => {
                element.style.borderRight = "none";
                resolve();
              }, 200);
            }
          };

          type();
        });
      }

      // Track which logs have been typed
      let typedLogIndices = new Set();

      // Render logs with typewriter effect for new entries
      async function renderLogsWithTypewriter(logs, logsContainer) {
        if (!logs || logs.length === 0) return;

        // Check if we have new logs
        const newLogCount = logs.length;
        const hasNewLogs = newLogCount > lastLogCount;

        if (!hasNewLogs) {
          // No new logs, just update existing
          return;
        }

        // Get new logs only
        const newLogs = logs.slice(lastLogCount);
        lastLogCount = newLogCount;

        // Add new log entries with typewriter effect
        for (const log of newLogs) {
          const logEntry = document.createElement("div");
          logEntry.className = "log-entry";
          logEntry.innerHTML = `
            <span class="log-time">${log.time}</span>
            <span class="log-message ${log.type}" data-full-text="${escapeHtml(log.message)}"></span>
          `;
          logsContainer.appendChild(logEntry);

          // Apply typewriter effect to the message
          const messageSpan = logEntry.querySelector(".log-message");
          await typewriterEffect(messageSpan, log.message, 8);

          // Scroll to bottom
          logsContainer.scrollTop = logsContainer.scrollHeight;
        }
      }

      // Reset log tracking when starting new session
      function resetLogTracking() {
        lastLogCount = 0;
        typedLogIndices.clear();
      }

      function resetChecklistState() {
        checklistRows = [];
        checklistProcessedLogCount = 0;
        activeContentPost = null;
        activeWpPost = null;
        currentPhase = "";
        Object.keys(postTitleToIndex).forEach((k) => delete postTitleToIndex[k]);
        renderTaskChecklist();
      }

      function getTaskStatusText(status) {
        if (status === "success") return "Đã xong";
        if (status === "warning") return "Cảnh báo";
        if (status === "failed") return "Thất bại";
        if (status === "error") return "Thất bại";
        if (status === "running") return "Đang chạy";
        return "Chờ";
      }

      function getTaskStatusIcon(status) {
        if (status === "success") return "fas fa-check";
        if (status === "warning") return "fas fa-triangle-exclamation";
        if (status === "failed") return "fas fa-xmark";
        if (status === "error") return "fas fa-xmark";
        if (status === "running") return "fas fa-spinner fa-spin";
        return "far fa-circle";
      }

      function getTaskGroupLabel(group) {
        if (group === "content") return "Content";
        if (group === "post") return "Đăng bài";
        return "Hệ thống";
      }

      function extractPostContext(message) {
        const contentStart = message.match(/^\[CONTENT\]\[POST:(\d+)\]\s+Bắt đầu tạo nội dung:\s*(.+)$/i);
        if (contentStart) {
          const idx = parseInt(contentStart[1], 10);
          const title = (contentStart[2] || "").trim();
          if (title) postTitleToIndex[title.toLowerCase()] = idx;
          activeContentPost = { index: idx, title };
          return;
        }

        const contentRetry = message.match(/^\[CONTENT\]\[POST:(\d+)\]\s+Tạo lại nội dung thiếu:\s*(.+?)(?:\s+\(lần\s+\d+\/\d+\))?$/i);
        if (contentRetry) {
          const idx = parseInt(contentRetry[1], 10);
          const title = (contentRetry[2] || "").trim();
          if (title) postTitleToIndex[title.toLowerCase()] = idx;
          activeContentPost = { index: idx, title };
          return;
        }

        const queuedContentRetry = message.match(/^\[RETRY\]\[CONTENT\]\[POST:(\d+)\]\s+Bắt đầu xử lý lại theo hàng chờ/i);
        if (queuedContentRetry) {
          const idx = parseInt(queuedContentRetry[1], 10);
          activeContentPost = { index: idx, title: activeContentPost?.title || "" };
          return;
        }

        const wpStart = message.match(/^Đang tạo bài\s+(\d+):\s*(.+)$/i);
        if (wpStart) {
          const idx = parseInt(wpStart[1], 10);
          const title = (wpStart[2] || "").trim();
          if (title) postTitleToIndex[title.toLowerCase()] = idx;
          activeWpPost = { index: idx, title };
          return;
        }

        const queuedWpRetry = message.match(/^\[RETRY\]\[POST\]\[POST:(\d+)\]\s+Bắt đầu xử lý lại theo hàng chờ/i);
        if (queuedWpRetry) {
          const idx = parseInt(queuedWpRetry[1], 10);
          activeWpPost = { index: idx, title: activeWpPost?.title || "" };
        }
      }

      function resolvePostFromTitle(message) {
        const titleMatch = message.match(/Đã tạo nội dung cho:\s*(.+)$/i) ||
          message.match(/Đã tạo lại thành công cho tiêu đề:\s*(.+)$/i) ||
          message.match(/Không thể tạo lại nội dung cho tiêu đề:\s*(.+)$/i);
        if (!titleMatch) return null;
        const title = (titleMatch[1] || "").trim().toLowerCase();
        if (!title) return null;
        const idx = postTitleToIndex[title];
        if (typeof idx !== "number") return null;
        return { index: idx, title: titleMatch[1].trim() };
      }

      function pushChecklistRow(postCtx, stepName, status, detail, time, actionType = null, group = null) {
        const postLabel = postCtx && postCtx.index ? `Bài ${postCtx.index}` : "Hệ thống";
        const normalizedStatus = status === "failed" ? "error" : status;
        const rowGroup = group || actionType || "system";
        const lastRow = checklistRows[checklistRows.length - 1];
        if (
          lastRow &&
          lastRow.postIndex === (postCtx && postCtx.index ? postCtx.index : 0) &&
          lastRow.stepName === stepName &&
          lastRow.status === normalizedStatus &&
          lastRow.detail === detail
        ) {
          return;
        }

        checklistRows.push({
          postIndex: postCtx && postCtx.index ? postCtx.index : 0,
          postLabel,
          postTitle: postCtx && postCtx.title ? postCtx.title : "",
          stepName,
          status: normalizedStatus,
          detail,
          time,
          actionType,
          group: rowGroup,
        });
        if (checklistRows.length > CHECKLIST_MAX_ROWS) {
          checklistRows.splice(0, checklistRows.length - CHECKLIST_MAX_ROWS);
        }
      }

      function updateLastRunningRow(postIndex, stepName, status, detail, time) {
        for (let i = checklistRows.length - 1; i >= 0; i -= 1) {
          const row = checklistRows[i];
          if (
            row.status === "running" &&
            row.stepName === stepName &&
            row.postIndex === (postIndex || 0)
          ) {
            row.status = status;
            row.detail = detail;
            row.time = time;
            return true;
          }
        }
        return false;
      }

      function processChecklistLogs(logs = []) {
        if (!logs || logs.length === 0) return;
        const newLogs = logs.slice(checklistProcessedLogCount);
        if (newLogs.length === 0) return;

        for (const log of newLogs) {
          const message = log.message || "";
          const time = log.time || "--:--:--";
          extractPostContext(message);

          const postFromTitle = resolvePostFromTitle(message);
          const contentPost = postFromTitle || activeContentPost;
          const wpPost = activeWpPost;

          if (/Starting WordPress Auto Poster/i.test(message)) {
            pushChecklistRow(null, "Khởi tạo phiên", "running", message, time, null, "system");
            continue;
          }
          if (/Phase 1: Generating content/i.test(message)) {
            pushChecklistRow(null, "Pha tạo content", "running", message, time, null, "system");
            continue;
          }
          if (/Phase 2: WordPress Automation/i.test(message)) {
            pushChecklistRow(null, "Pha đăng WordPress", "running", message, time, null, "system");
            continue;
          }
          if (/SUMMARY:/i.test(message) || /completed!/i.test(message)) {
            pushChecklistRow(null, "Tổng kết phiên", "success", message, time, null, "system");
            continue;
          }

          const queuedManualRetryMatch = message.match(/Đã thêm vào hàng chờ rend lại content:\s*bài\s*(\d+)/i);
          if (queuedManualRetryMatch) {
            const idx = parseInt(queuedManualRetryMatch[1], 10);
            const ctx = Number.isFinite(idx) && idx > 0 ? { index: idx, title: contentPost?.title || "" } : contentPost;
            pushChecklistRow(ctx, "Xếp hàng chờ rend lại", "success", message, time, "content", "content");
            continue;
          }
          if (/^\[RETRY\]\[CONTENT\]\[POST:\d+\]\s+Bắt đầu xử lý lại theo hàng chờ/i.test(message)) {
            pushChecklistRow(contentPost, "Xử lý hàng chờ rend lại", "running", message, time, "content", "content");
            continue;
          }
          if (/^\[CONTENT\]\[POST:\d+\]\s+Bắt đầu tạo nội dung:/i.test(message)) {
            pushChecklistRow(contentPost, "Khởi tạo content", "running", message, time, "content", "content");
            continue;
          }
          if (/^\[CONTENT\]\[POST:\d+\]\s+Tạo lại nội dung thiếu:/i.test(message)) {
            pushChecklistRow(contentPost, "Rend lại content", "running", message, time, "content", "content");
            continue;
          }

          const invalidWordMatch = message.match(/Nội dung cho '(.+?)' không hợp lệ \((.+)\) \[(\d+)\/(\d+)\]/i);
          if (invalidWordMatch) {
            const attempt = parseInt(invalidWordMatch[3], 10) || 0;
            const total = parseInt(invalidWordMatch[4], 10) || 0;
            const isFinalAttempt = total > 0 && attempt >= total;
            pushChecklistRow(
              contentPost,
              "Kiểm tra ngưỡng từ",
              isFinalAttempt ? "error" : "warning",
              message,
              time,
              "content",
              "content",
            );
            continue;
          }

          if (/Đang nhập prompt/i.test(message)) {
            pushChecklistRow(contentPost, "Fill prompt Gemini", "running", message, time, "content", "content");
            continue;
          }
          if (/Đã gửi prompt/i.test(message) || /Đã nhập prompt qua fill\(\)/i.test(message)) {
            if (!updateLastRunningRow(contentPost?.index, "Fill prompt Gemini", "success", message, time)) {
              pushChecklistRow(contentPost, "Fill prompt Gemini", "success", message, time, "content", "content");
            }
            continue;
          }
          if (/Không tìm thấy ô nhập Gemini/i.test(message)) {
            if (!updateLastRunningRow(contentPost?.index, "Fill prompt Gemini", "error", message, time)) {
              pushChecklistRow(contentPost, "Fill prompt Gemini", "error", message, time, "content", "content");
            }
            continue;
          }

          if (/Đang trích xuất phản hồi/i.test(message)) {
            pushChecklistRow(contentPost, "Lưu content", "running", message, time, "content", "content");
            continue;
          }
          if (/Đã tạo nội dung cho:/i.test(message) || /Đã tạo lại thành công cho tiêu đề:/i.test(message)) {
            if (!updateLastRunningRow(contentPost?.index, "Lưu content", "success", message, time)) {
              pushChecklistRow(contentPost, "Lưu content", "success", message, time, "content", "content");
            }
            continue;
          }
          if (
            /Không thể trích xuất phản hồi Gemini/i.test(message) ||
            /Không thể tạo nội dung/i.test(message) ||
            /Không thể tạo lại nội dung cho tiêu đề:/i.test(message)
          ) {
            if (!updateLastRunningRow(contentPost?.index, "Lưu content", "error", message, time)) {
              pushChecklistRow(contentPost, "Lưu content", "error", message, time, "content", "content");
            }
            continue;
          }

          if (/Tạo lại nội dung thiếu:/i.test(message) || /Đã tạo lại thành công cho tiêu đề:/i.test(message)) {
            pushChecklistRow(contentPost, "Rend lại content", "running", message, time, "content", "content");
            continue;
          }

          if (/Logging into WordPress/i.test(message) || /Đang chờ đăng nhập/i.test(message)) {
            pushChecklistRow(wpPost, "Đăng nhập WordPress", "running", message, time, "post", "post");
            continue;
          }
          if (
            /Successfully logged into WordPress/i.test(message) ||
            /Already logged in!/i.test(message) ||
            /Login appears successful/i.test(message)
          ) {
            if (!updateLastRunningRow(wpPost?.index, "Đăng nhập WordPress", "success", message, time)) {
              pushChecklistRow(wpPost, "Đăng nhập WordPress", "success", message, time, "post", "post");
            }
            continue;
          }
          if (/Login failed/i.test(message) || /Missing login credentials/i.test(message) || /Failed to login\. Exiting/i.test(message)) {
            if (!updateLastRunningRow(wpPost?.index, "Đăng nhập WordPress", "error", message, time)) {
              pushChecklistRow(wpPost, "Đăng nhập WordPress", "error", message, time, "post", "post");
            }
            continue;
          }

          if (/Preparing to publish/i.test(message) || /Đang lưu bài viết/i.test(message)) {
            pushChecklistRow(wpPost, "Đăng bài WordPress", "running", message, time, "post", "post");
            continue;
          }
          if (/successfully!/i.test(message) || /Post saved/i.test(message)) {
            if (!updateLastRunningRow(wpPost?.index, "Đăng bài WordPress", "success", message, time)) {
              pushChecklistRow(wpPost, "Đăng bài WordPress", "success", message, time, "post", "post");
            }
            continue;
          }
          if (/Đánh dấu bỏ qua đăng bài\s+\d+/i.test(message) || /Skipping post \d+ theo yêu cầu người dùng/i.test(message)) {
            pushChecklistRow(wpPost, "Bỏ qua đăng bài", "warning", message, time, "post", "post");
            continue;
          }
          if (/Error creating post/i.test(message) || /Error publishing/i.test(message) || /Skipping post \d+ - no content/i.test(message) || /Bỏ qua bài \d+ sau/i.test(message)) {
            if (!updateLastRunningRow(wpPost?.index, "Đăng bài WordPress", "error", message, time)) {
              pushChecklistRow(wpPost, "Đăng bài WordPress", "error", message, time, "post", "post");
            }
          }
        }

        checklistProcessedLogCount = logs.length;
      }

      function syncChecklistFromContentStatus(contentList = []) {
        if (!Array.isArray(contentList) || contentList.length === 0) return;
        const time = new Date().toLocaleTimeString("en-GB");
        for (const item of contentList) {
          if (item.status !== "failed") continue;
          const postIndex = (parseInt(item.post_index, 10) || 0) + 1;
          const reason = item.error_reason || "Không đạt ngưỡng từ";
          const attempts = item.attempts || 1;
          const detail = `Content fail (${attempts} lần): ${reason}`;
          const exists = checklistRows.some(
            (row) =>
              row.group === "content" &&
              row.postIndex === postIndex &&
              row.stepName === "Kết quả content" &&
              row.status === "error" &&
              row.detail === detail,
          );
          if (exists) continue;
          pushChecklistRow(
            { index: postIndex, title: item.title || "" },
            "Kết quả content",
            "error",
            detail,
            time,
            "content",
            "content",
          );
        }
      }

      async function clearChecklistRows() {
        const confirmed = await showConfirmDialog(
          "Bạn muốn xóa toàn bộ các dòng checklist hiện tại?",
          {
            title: "Xóa checklist",
            type: "warning",
            confirmText: "Xóa",
            cancelText: "Hủy",
          },
        );
        if (!confirmed) return;
        checklistRows = [];
        renderTaskChecklist();
        showToast("Đã xóa checklist", "success");
      }

      function canQueueRetry(row) {
        if (!row || !row.actionType || !row.postIndex) return false;
        if (!isRunning) return false;
        if (row.status === "running") return false;
        if (row.actionType !== "content") return false;
        return ["generating_content", "retry_content_queue"].includes(currentPhase);
      }

      async function queueRetryAction(actionType, postIndex) {
        try {
          const response = await fetch("/api/retry-queue", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: actionType,
              post_index: postIndex,
            }),
          });
          const result = await response.json();
          if (result.success) {
            showToast(`Đã thêm vào hàng chờ thực hiện lại: bài ${postIndex}`, "warning");
          } else {
            showToast(result.message || "Không thể thêm vào hàng chờ", "error");
          }
        } catch (e) {
          showToast("Lỗi khi thêm vào hàng chờ thực hiện lại", "error");
        }
      }

      function renderTaskChecklist() {
        const tbody = document.getElementById("taskChecklistBody");
        const summary = document.getElementById("taskChecklistSummary");
        const groupFilterEl = document.getElementById("checklistGroupFilter");
        const statusFilterEl = document.getElementById("checklistStatusFilter");
        const onlyErrorsEl = document.getElementById("checklistOnlyErrors");
        const newestFirstEl = document.getElementById("checklistNewestFirst");
        if (!tbody) return;

        const groupFilter = groupFilterEl ? groupFilterEl.value : "all";
        const statusFilter = statusFilterEl ? statusFilterEl.value : "all";
        const onlyErrors = onlyErrorsEl ? onlyErrorsEl.checked : false;
        const newestFirst = newestFirstEl ? newestFirstEl.checked : true;

        const filteredRows = checklistRows.filter((row) => {
          const rowGroup = row.group || row.actionType || "system";
          if (groupFilter !== "all" && rowGroup !== groupFilter) return false;
          if (onlyErrors && row.status !== "error") return false;
          if (statusFilter !== "all" && row.status !== statusFilter) return false;
          return true;
        });

        const displayedRows = newestFirst ? [...filteredRows].reverse() : filteredRows;
        const runningCount = checklistRows.filter((r) => r.status === "running").length;
        const successCount = checklistRows.filter((r) => r.status === "success").length;
        const warningCount = checklistRows.filter((r) => r.status === "warning").length;
        const errorCount = checklistRows.filter((r) => r.status === "error").length;
        const phaseLabel = currentPhase || "idle";
        if (summary) {
          summary.textContent =
            `${displayedRows.length}/${checklistRows.length} dòng · ` +
            `Run ${runningCount} · OK ${successCount} · Warn ${warningCount} · Fail ${errorCount} · ${phaseLabel}`;
        }

        tbody.innerHTML = displayedRows
          .map((row, index) => {
            const allowRetry = canQueueRetry(row);
            const rowClass = row.status === "error"
              ? "row-error"
              : row.status === "warning"
                ? "row-warning"
                : row.status === "running"
                  ? "row-running"
                  : "";
            const rowGroup = row.group || row.actionType || "system";
            return `
            <tr class="${allowRetry ? "allow-retry" : ""} ${rowClass}">
              <td>${index + 1}</td>
              <td>
                <div>${escapeHtml(row.postLabel)}</div>
                <div class="task-detail">${escapeHtml(row.postTitle || "")}</div>
                <span class="task-group-tag ${rowGroup}">${escapeHtml(getTaskGroupLabel(rowGroup))}</span>
              </td>
              <td class="task-step-cell">
                <div class="task-step-content">
                  <div>${escapeHtml(row.stepName)}</div>
                  <div class="task-detail">[${escapeHtml(row.time)}] ${escapeHtml(row.detail || "")}</div>
                </div>
                ${allowRetry ? `<button class="retry-action-btn" onclick="queueRetryAction('${row.actionType}', ${row.postIndex})">Thực hiện lại</button>` : ""}
              </td>
              <td>
                <span class="task-status ${row.status}">
                  <i class="${getTaskStatusIcon(row.status)}"></i>
                  ${getTaskStatusText(row.status)}
                </span>
              </td>
            </tr>
          `;
          })
          .join("");
      }

      // Toggle typing sound on/off
      function toggleTypingSound() {
        typingSoundEnabled = !typingSoundEnabled;
        const icon = document.getElementById("soundIcon");
        const btn = document.getElementById("soundToggleBtn");

        if (typingSoundEnabled) {
          icon.className = "fas fa-volume-up";
          btn.style.color = "var(--accent-primary)";
          showToast("Âm thanh đã bật", "success");
        } else {
          icon.className = "fas fa-volume-mute";
          btn.style.color = "var(--text-muted)";
          showToast("Âm thanh đã tắt", "info");
        }
      }
