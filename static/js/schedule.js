      function toggleDateDistribution() {
        const hasTopics = topics.length > 0;
        document.getElementById("dateDisabledOverlay").style.display = hasTopics ? "none" : "block";
        document.getElementById("dateInputSection").style.display = hasTopics ? "block" : "none";
        if (hasTopics) {
          ensureDefaultScheduleDates();
          validateDateDistribution();
        }
      }

      function formatDateLocal(dateObj) {
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
      }

      function parseDateInput(value) {
        if (!value) return null;
        const parts = value.split("-").map((p) => parseInt(p, 10));
        if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return null;
        return new Date(parts[0], parts[1] - 1, parts[2]);
      }

      function ensureDefaultScheduleDates() {
        const startDateEl = document.getElementById("scheduleStartDate");
        const endDateEl = document.getElementById("scheduleEndDate");
        const daysInputEl = document.getElementById("scheduleDaysCount");

        if (!startDateEl.value) {
          startDateEl.value = formatDateLocal(new Date());
        }

        const safeDays = Math.max(1, parseInt(daysInputEl.value, 10) || 1);
        daysInputEl.value = safeDays;

        if (!endDateEl.value) {
          setScheduleRangeDays(safeDays);
        } else {
          syncScheduleDaysFromDates();
        }
      }

      function setScheduleRangeDays(totalDays) {
        const startDateEl = document.getElementById("scheduleStartDate");
        const endDateEl = document.getElementById("scheduleEndDate");
        const daysInputEl = document.getElementById("scheduleDaysCount");
        const start = parseDateInput(startDateEl.value);
        if (!start) return;

        const safeDays = Math.max(1, parseInt(totalDays, 10) || 1);
        const end = new Date(start);
        end.setDate(start.getDate() + safeDays - 1);

        endDateEl.value = formatDateLocal(end);
        daysInputEl.value = safeDays;
      }

      function syncScheduleDaysFromDates() {
        const startDateEl = document.getElementById("scheduleStartDate");
        const endDateEl = document.getElementById("scheduleEndDate");
        const daysInputEl = document.getElementById("scheduleDaysCount");

        const start = parseDateInput(startDateEl.value);
        const end = parseDateInput(endDateEl.value);
        if (!start || !end) return;

        const diffDays = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;
        daysInputEl.value = Math.max(1, diffDays);
      }

      function adjustScheduleDays(delta) {
        ensureDefaultScheduleDates();
        const daysInputEl = document.getElementById("scheduleDaysCount");
        const nextDays = Math.max(1, (parseInt(daysInputEl.value, 10) || 1) + delta);
        setScheduleRangeDays(nextDays);
        validateDateDistribution();
      }

      function setScheduleDaysFromInput() {
        ensureDefaultScheduleDates();
        const daysInputEl = document.getElementById("scheduleDaysCount");
        setScheduleRangeDays(Math.max(1, parseInt(daysInputEl.value, 10) || 1));
        validateDateDistribution();
      }

      function onScheduleDateChanged(changedField) {
        ensureDefaultScheduleDates();

        if (changedField === "start") {
          const daysInputEl = document.getElementById("scheduleDaysCount");
          const currentDays = Math.max(1, parseInt(daysInputEl.value, 10) || 1);
          setScheduleRangeDays(currentDays);
        } else {
          syncScheduleDaysFromDates();
        }

        validateDateDistribution();
      }

      function refreshScheduleStartToday() {
        ensureDefaultScheduleDates();
        const startDateEl = document.getElementById("scheduleStartDate");
        startDateEl.value = formatDateLocal(new Date());
        onScheduleDateChanged("start");
        showToast("Đã cập nhật ngày bắt đầu = hôm nay", "success");
      }

      function validateDateDistribution() {
        const startDateEl = document.getElementById("scheduleStartDate");
        const endDateEl = document.getElementById("scheduleEndDate");
        const msgEl = document.getElementById("dateValidationMsg");
        const summaryEl = document.getElementById("dateSummary");

        const startDate = startDateEl.value;
        const endDate = endDateEl.value;

        if (!startDate || !endDate) {
          msgEl.style.display = "none";
          summaryEl.style.display = "none";
          return false;
        }

        const start = parseDateInput(startDate);
        const end = parseDateInput(endDate);

        if (!start || !end) {
          msgEl.style.display = "none";
          summaryEl.style.display = "none";
          return false;
        }

        if (end < start) {
          msgEl.style.display = "block";
          msgEl.style.background = "rgba(255,0,0,0.15)";
          msgEl.style.color = "var(--error)";
          msgEl.style.border = "1px solid rgba(255,0,0,0.3)";
          msgEl.innerHTML = `<i class="fas fa-circle-xmark"></i> Ngày kết thúc phải sau ngày bắt đầu`;
          summaryEl.style.display = "none";
          return false;
        }

        const totalDays = Math.ceil((end - start) / (1000 * 60 * 60 * 24)) + 1;
        const totalPosts = topics.length;

        if (totalPosts < 1) {
          msgEl.style.display = "block";
          msgEl.style.background = "rgba(255,0,0,0.15)";
          msgEl.style.color = "var(--error)";
          msgEl.style.border = "1px solid rgba(255,0,0,0.3)";
          msgEl.innerHTML = `<i class="fas fa-circle-xmark"></i> Cần ít nhất 1 bài viết`;
          summaryEl.style.display = "none";
          return false;
        }

        if (totalPosts < totalDays) {
          msgEl.style.display = "block";
          msgEl.style.background = "rgba(255,255,0,0.1)";
          msgEl.style.color = "var(--warning)";
          msgEl.style.border = "1px solid rgba(255,255,0,0.3)";
          msgEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Số bài (${totalPosts}) ít hơn số ngày (${totalDays}). Sẽ có ngày không có bài. Hãy giảm ngày hoặc thêm bài.`;
          summaryEl.style.display = "none";
          return false;
        }

        const postsPerDay = Math.floor(totalPosts / totalDays);
        const extraPosts = totalPosts % totalDays;

        let distributionText = "";
        if (extraPosts === 0) {
          distributionText = `${postsPerDay} bài/ngày (đều)`;
        } else {
          distributionText = `${extraPosts} ngày: ${postsPerDay + 1} bài, ${totalDays - extraPosts} ngày: ${postsPerDay} bài`;
        }

        msgEl.style.display = "block";
        msgEl.style.background = "rgba(0,255,0,0.1)";
        msgEl.style.color = "var(--success)";
        msgEl.style.border = "1px solid rgba(0,255,0,0.3)";
        msgEl.innerHTML = `<i class="fas fa-check-circle"></i> Hợp lệ: ${totalPosts} bài trong ${totalDays} ngày — ${distributionText}`;

        summaryEl.style.display = "block";
        document.getElementById("summaryTotalPosts").textContent = totalPosts;
        document.getElementById("summaryTotalDays").textContent = totalDays;
        document.getElementById("summaryPostsPerDay").textContent = 
          extraPosts === 0 ? postsPerDay : `${postsPerDay}-${postsPerDay + 1}`;
        document.getElementById("scheduleDaysCount").value = totalDays;

        document.getElementById("postsPerDay").value = postsPerDay;

        return true;
      }
