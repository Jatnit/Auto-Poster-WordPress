      async function startAutomation() {
        await saveConfig();
        await saveTopics();

        const startDateEl = document.getElementById("scheduleStartDate");
        const endDateEl = document.getElementById("scheduleEndDate");

        let body = {};

        if (startDateEl.value && endDateEl.value) {
          if (!validateDateDistribution()) {
            showToast("Số bài viết không khớp với số ngày. Kiểm tra lại!", "error");
            return;
          }
          body.schedule_start_date = startDateEl.value;
          body.schedule_end_date = endDateEl.value;
        }

        try {
          const response = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });

          const result = await response.json();

          if (result.success) {
            isRunning = true;
            // Xin wake lock để màn hình không ngủ khi tab active
            requestWakeLock();
            document.getElementById("startBtn").style.display = "none";
            document.getElementById("runningControls").style.display = "flex";
            document.getElementById("pauseBtn").style.display = "block";
            document.getElementById("resumeBtn").style.display = "none";
            document.getElementById("pauseBanner").style.display = "none";
            document.getElementById("statusDot").classList.add("running");
            document.getElementById("statusText").textContent = "Running";

            // Reset log tracking and clear logs container
            resetLogTracking();
            document.getElementById("logsContainer").innerHTML = "";
            resetChecklistState();

            // Clear content list
            clearContentList();

            // Start polling for status
            statusInterval = setInterval(updateStatus, 1000);
            showToast("Đã bắt đầu tự động đăng bài!", "success");
          } else {
            showToast(result.message || "Không thể bắt đầu", "error");
          }
        } catch (e) {
          showToast("Lỗi kết nối server", "error");
        }
      }

      // Stop automation
      async function stopAutomation() {
        try {
          await fetch("/api/stop", { method: "POST" });

          isRunning = false;
          releaseWakeLock();
          document.getElementById("startBtn").style.display = "block";
          document.getElementById("runningControls").style.display = "none";
          document.getElementById("pauseBanner").style.display = "none";
          document.getElementById("statusDot").classList.remove("running");
          document.getElementById("statusText").textContent = "Stopped";

          if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
          }

          showToast("Đã kết thúc!", "warning");
        } catch (e) {
          showToast("Lỗi khi dừng", "error");
        }
      }

      // Pause automation
      async function pauseAutomation() {
        try {
          const response = await fetch("/api/pause", { method: "POST" });
          const result = await response.json();

          if (result.success) {
            document.getElementById("pauseBtn").style.display = "none";
            document.getElementById("resumeBtn").style.display = "block";
            document.getElementById("pauseBanner").style.display = "flex";
            document.getElementById("pauseReason").textContent =
              "Đã tạm dừng bởi người dùng";
            document.getElementById("statusText").textContent = "Paused";
            showToast("Đã tạm dừng", "warning");
          }
        } catch (e) {
          showToast("Lỗi khi tạm dừng", "error");
        }
      }

      // Resume automation
      async function resumeAutomation() {
        try {
          const response = await fetch("/api/resume", { method: "POST" });
          const result = await response.json();

          if (result.success) {
            document.getElementById("pauseBtn").style.display = "block";
            document.getElementById("resumeBtn").style.display = "none";
            document.getElementById("pauseBanner").style.display = "none";
            document.getElementById("statusText").textContent = "Running";
            showToast("Tiếp tục thực thi", "success");
          }
        } catch (e) {
          showToast("Lỗi khi tiếp tục", "error");
        }
      }

      // Update status
      async function updateStatus() {
        try {
          const response = await fetch("/api/status");
          const status = await response.json();
          currentPhase = status.current_phase || "";

          // Update progress
          document.getElementById("progressBar").style.width =
            status.progress + "%";
          document.getElementById("progressValue").textContent =
            Math.round(status.progress) + "%";
          document.getElementById("progressPercent").textContent =
            Math.round(status.progress) + "%";
          document.getElementById("currentTask").textContent =
            status.current_task || "Sẵn sàng";
          document.getElementById("successfulPosts").textContent =
            status.successful_posts || 0;
          document.getElementById("failedPosts").textContent =
            status.failed_posts || 0;

          // Update logs with typewriter effect
          const logsContainer = document.getElementById("logsContainer");
          if (status.logs && status.logs.length > 0) {
            renderLogsWithTypewriter(status.logs, logsContainer);
          }
          processChecklistLogs(status.logs || []);
          syncChecklistFromContentStatus(status.content_list || []);
          renderTaskChecklist();

          // Update content list
          if (status.content_list && status.content_list.length > 0) {
            renderContentList(status.content_list);
          }

          // Handle pause state from server (e.g., auto-paused on error)
          if (status.is_paused && isRunning) {
            document.getElementById("pauseBtn").style.display = "none";
            document.getElementById("resumeBtn").style.display = "block";
            document.getElementById("pauseBanner").style.display = "flex";
            document.getElementById("pauseReason").textContent =
              status.pause_reason || "Đã tạm dừng";
            document.getElementById("statusText").textContent = "Paused";
          }

          // Check if finished
          if (!status.is_running && isRunning) {
            isRunning = false;
            releaseWakeLock();
            document.getElementById("startBtn").style.display = "block";
            document.getElementById("runningControls").style.display = "none";
            document.getElementById("pauseBanner").style.display = "none";
            document.getElementById("statusDot").classList.remove("running");
            document.getElementById("statusText").textContent = "Completed";

            if (statusInterval) {
              clearInterval(statusInterval);
              statusInterval = null;
            }

            showToast("Hoàn thành!", "success");
          }
        } catch (e) {
          console.log("Could not fetch status");
        }
      }

      // Handle Enter key on topic inputs
      document.getElementById("newTitle").addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          document.getElementById("newKeyword").focus();
        }
      });

      document
        .getElementById("newKeyword")
        .addEventListener("keypress", (e) => {
          if (e.key === "Enter") {
            addTopic();
          }
        });
