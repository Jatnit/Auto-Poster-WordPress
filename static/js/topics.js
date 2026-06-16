      // Add topic
      function addTopic() {
        const titleInput = document.getElementById("newTitle");
        const keywordInput = document.getElementById("newKeyword");
        const tagsInput = document.getElementById("newTags");

        const title = titleInput.value.trim();
        const keyword = keywordInput.value.trim();
        const tags = tagsInput ? tagsInput.value.trim() : "";

        if (!title) {
          showToast("Vui lòng nhập tiêu đề", "warning");
          return;
        }

        topics.push({
          title: title,
          keyword: keyword || title,
          tags: tags,
        });

        titleInput.value = "";
        keywordInput.value = "";
        if (tagsInput) tagsInput.value = "";

        renderTopics();
        saveTopics();
        updateStats();
      }

      // Delete topic
      function deleteTopic(index) {
        topics.splice(index, 1);
        renderTopics();
        saveTopics();
        updateStats();
      }

      // Switch input mode between shared keyword and individual keyword
      function switchInputMode(mode) {
        const sharedMode = document.getElementById("sharedKeywordMode");
        const individualMode = document.getElementById("individualKeywordMode");
        const sharedBtn = document.getElementById("modeSharedKeyword");
        const individualBtn = document.getElementById("modeIndividualKeyword");

        if (mode === "shared") {
          sharedMode.style.display = "block";
          individualMode.style.display = "none";
          sharedBtn.classList.add("active");
          individualBtn.classList.remove("active");
        } else {
          sharedMode.style.display = "none";
          individualMode.style.display = "block";
          sharedBtn.classList.remove("active");
          individualBtn.classList.add("active");
        }
      }

      // Add multiple titles with shared keyword
      function addBulkTitles() {
        const sharedKeyword = document
          .getElementById("sharedKeyword")
          .value.trim();
        const sharedTags = document.getElementById("sharedTags")
          ? document.getElementById("sharedTags").value.trim()
          : "";
        const titlesText = document.getElementById("bulkTitles").value.trim();

        if (!sharedKeyword) {
          showToast("Vui lòng nhập từ khóa SEO chung!", "error");
          document.getElementById("sharedKeyword").focus();
          return;
        }

        if (!titlesText) {
          showToast("Vui lòng nhập ít nhất 1 tiêu đề!", "error");
          document.getElementById("bulkTitles").focus();
          return;
        }

        // Split by newlines and filter empty lines
        const titles = titlesText
          .split("\n")
          .map((t) => t.trim())
          .filter((t) => t.length > 0);

        if (titles.length === 0) {
          showToast("Không tìm thấy tiêu đề hợp lệ!", "error");
          return;
        }

        // Add each title with the shared keyword and tags
        let addedCount = 0;
        titles.forEach((title) => {
          // Check for duplicates
          const isDuplicate = topics.some(
            (t) => t.title.toLowerCase() === title.toLowerCase(),
          );
          if (!isDuplicate) {
            topics.push({
              title: title,
              keyword: sharedKeyword,
              tags: sharedTags,
            });
            addedCount++;
          }
        });

        if (addedCount > 0) {
          renderTopics();
          saveTopics();
          updateStats();
          const tagsInfo = sharedTags ? ` + tags` : "";
          showToast(
            `Đã thêm ${addedCount} tiêu đề với từ khóa "${sharedKeyword}"${tagsInfo}`,
            "success",
          );

          // Clear the textarea but keep the keyword and tags
          document.getElementById("bulkTitles").value = "";
        } else {
          showToast("Tất cả tiêu đề đã tồn tại!", "warning");
        }
      }

      // Clear all topics
      let isClearing = false;
      async function clearAllTopics() {
        // Prevent multiple calls
        if (isClearing) return;

        // Check if there are topics to clear
        if (topics.length === 0) {
          showToast("Không có chủ đề nào để xóa", "warning");
          return;
        }

        isClearing = true;

        // Use async modal instead of native confirm
        const confirmed = await showConfirmDialog(
          `Bạn có chắc muốn xóa tất cả ${topics.length} chủ đề?`,
          {
            title: "Xóa tất cả chủ đề",
            type: "danger",
            confirmText: "Xóa tất cả",
            cancelText: "Hủy",
          },
        );

        if (confirmed) {
          topics = [];
          renderTopics();
          saveTopics();
          updateStats();
          showToast("Đã xóa tất cả chủ đề", "success");
        }

        isClearing = false;
      }

      // Load sample topics
      function loadSampleTopics() {
        const sampleTopics = [
          {
            title: "Hướng dẫn tối ưu SEO cho website năm 2024",
            keyword: "tối ưu SEO website",
          },
          {
            title: "10 xu hướng thiết kế website hiện đại",
            keyword: "thiết kế website hiện đại",
          },
          {
            title: "Cách xây dựng chiến lược content marketing hiệu quả",
            keyword: "content marketing",
          },
          {
            title: "Bí quyết tăng tốc độ tải trang website",
            keyword: "tăng tốc độ website",
          },
          {
            title: "Hướng dẫn bảo mật website WordPress toàn diện",
            keyword: "bảo mật WordPress",
          },
        ];

        topics = [...topics, ...sampleTopics];
        renderTopics();
        saveTopics();
        updateStats();
        showToast("Đã thêm 5 chủ đề mẫu", "success");
      }

      // Render topics
      function renderTopics() {
        const container = document.getElementById("topicsContainer");

        if (topics.length === 0) {
          container.innerHTML = `
            <div class="empty-state">
              <i class="fas fa-folder-open"></i>
              <p>Chưa có chủ đề nào</p>
            </div>
          `;
          return;
        }

        container.innerHTML = topics
          .map(
            (topic, index) => `
                <div class="topic-item fade-in">
                    <span class="topic-number">${index + 1}</span>
                    <div class="topic-content">
                        <div class="topic-title">${escapeHtml(topic.title)}</div>
                        <div class="topic-keyword"><i class="fas fa-key"></i> ${escapeHtml(topic.keyword)}</div>
                        ${topic.tags ? `<div class="topic-tags" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;"><i class="fas fa-tags"></i> ${escapeHtml(topic.tags.substring(0, 60))}${topic.tags.length > 60 ? "..." : ""}</div>` : ""}
                    </div>
                    <button class="topic-delete" onclick="deleteTopic(${index})">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `,
          )
          .join("");
      }

      // Escape HTML to prevent XSS
      function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
      }

      // Save topics to localStorage and server
      async function saveTopics() {
        localStorage.setItem("wp_auto_topics", JSON.stringify(topics));

        try {
          await fetch("/api/topics", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ topics: topics }),
          });
        } catch (e) {
          console.log("Could not save topics to server");
        }
      }

      // Load topics
      function loadTopics() {
        const savedTopics = localStorage.getItem("wp_auto_topics");
        if (savedTopics) {
          topics = JSON.parse(savedTopics);
          renderTopics();
        }
      }

      function updateStats() {
        document.getElementById("totalTopics").textContent = topics.length;
        toggleDateDistribution();
      }
