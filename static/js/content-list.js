      let loadedContents = {};
      let contentListRenderSignature = "";
      let openedAccordionIndex = null;
      function hasLoadedContent(index) {
        return Object.prototype.hasOwnProperty.call(loadedContents, index);
      }

      function getContentListSignature(contentList = []) {
        return contentList
          .map((item) =>
            [
              item.post_index,
              item.title,
              item.keyword,
              item.word_count,
              item.status || "",
              item.error_reason || "",
              item.attempts || 1,
            ].join("|"),
          )
          .join("||");
      }

      function restoreOpenedAccordion(index, contentList = []) {
        if (index === null || index === undefined) return;
        if (index < 0 || index >= contentList.length) {
          openedAccordionIndex = null;
          return;
        }

        const body = document.getElementById(`accordion-body-${index}`);
        const btn = document.getElementById(`expand-btn-${index}`);
        if (!body || !btn) {
          openedAccordionIndex = null;
          return;
        }

        body.classList.add("open");
        btn.classList.add("active");
        btn.innerHTML = '<i class="fas fa-chevron-up"></i> Ẩn';

        if (hasLoadedContent(index)) {
          body.innerHTML =
            loadedContents[index] ||
            '<p style="color: var(--warning);">Nội dung trống</p>';
        }
      }

      function renderContentList(contentList) {
        const accordion = document.getElementById("contentAccordion");
        const emptyState = document.getElementById("contentListEmpty");
        const countBadge = document.getElementById("contentCount");

        if (!contentList || contentList.length === 0) {
          emptyState.style.display = "block";
          accordion.innerHTML = "";
          countBadge.textContent = "(0)";
          contentListRenderSignature = "";
          openedAccordionIndex = null;
          return;
        }

        const newSignature = getContentListSignature(contentList);
        const canSkipRerender =
          newSignature === contentListRenderSignature &&
          accordion.children.length === contentList.length &&
          contentList.length > 0;
        if (canSkipRerender) {
          return;
        }

        contentListRenderSignature = newSignature;
        const prevOpenedIndex = openedAccordionIndex;
        emptyState.style.display = "none";
        countBadge.textContent = `(${contentList.length})`;

        accordion.innerHTML = contentList
          .map(
            (item, index) => {
              const isFailed = item.status === "failed";
              const statusLabel = isFailed ? "Fail" : "OK";
              const failReason = item.error_reason || "";
              const attempts = item.attempts || 1;
              return `
          <div class="content-accordion-item" id="accordion-item-${index}">
            <div class="content-accordion-header" onclick="toggleContentAccordion(${index})">
              <div class="content-accordion-info">
                <div class="content-accordion-title">${index + 1}. ${item.title}</div>
                <div class="content-accordion-meta">
                  <span><i class="fas fa-key meta-icon"></i>${item.keyword}</span>
                  <span><i class="fas fa-file-lines meta-icon"></i>${item.word_count.toLocaleString()} từ</span>
                  <span><i class="fas fa-rotate-right meta-icon"></i>${attempts} lần</span>
                  <span class="content-status-tag ${isFailed ? "failed" : "success"}">${statusLabel}</span>
                </div>
                ${isFailed ? `<div class="content-fail-reason">Lỗi: ${escapeHtml(failReason)}</div>` : ""}
              </div>
              <div class="content-accordion-actions">
                <button class="btn btn-expand" id="expand-btn-${index}" onclick="event.stopPropagation(); toggleContentAccordion(${index})">
                  <i class="fas fa-chevron-down"></i>
                  Xem
                </button>
                <button class="btn btn-edit" onclick="event.stopPropagation(); openEditModal(${index})" title="Chỉnh sửa">
                  <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-secondary" onclick="event.stopPropagation(); copyContentByIndex(${index})" style="padding: 6px 10px; font-size: 0.75rem;" title="Copy HTML">
                  <i class="fas fa-copy"></i>
                </button>
                <button class="btn btn-rerender" onclick="event.stopPropagation(); requestRerenderByIndex(${index})" title="Rend lại nội dung này">
                  <i class="fas fa-rotate"></i>
                </button>
                <button class="btn btn-delete" onclick="event.stopPropagation(); deleteContentByIndex(${index})" title="Xóa">
                  <i class="fas fa-trash"></i>
                </button>
              </div>
            </div>
            <div class="content-accordion-body" id="accordion-body-${index}">
              <div class="loading-content" style="text-align: center; padding: 2rem; color: var(--text-muted);">
                <i class="fas fa-spinner fa-spin"></i> Đang tải nội dung...
              </div>
            </div>
          </div>
        `;
            },
          )
          .join("");

        restoreOpenedAccordion(prevOpenedIndex, contentList);
      }

      // Toggle accordion content
      async function toggleContentAccordion(index) {
        const body = document.getElementById(`accordion-body-${index}`);
        const btn = document.getElementById(`expand-btn-${index}`);

        if (body.classList.contains("open")) {
          body.classList.remove("open");
          btn.classList.remove("active");
          btn.innerHTML = '<i class="fas fa-chevron-down"></i> Xem';
          openedAccordionIndex = null;
          return;
        }

        // Close other open accordions
        document
          .querySelectorAll(".content-accordion-body.open")
          .forEach((el) => {
            el.classList.remove("open");
          });
        document.querySelectorAll(".btn-expand.active").forEach((el) => {
          el.classList.remove("active");
          el.innerHTML = '<i class="fas fa-chevron-down"></i> Xem';
        });

        // Open this one
        body.classList.add("open");
        btn.classList.add("active");
        btn.innerHTML = '<i class="fas fa-chevron-up"></i> Ẩn';
        openedAccordionIndex = index;

        // Load content if not loaded
        if (!hasLoadedContent(index)) {
          try {
            const response = await fetch(`/api/content/${index}`);
            const result = await response.json();
            if (result.success) {
              const contentHtml = result.data.content || "";
              loadedContents[index] = contentHtml;
              if (contentHtml.trim()) {
                body.innerHTML = contentHtml;
              } else if (result.data.status === "failed") {
                const reason = escapeHtml(result.data.error_reason || "Nội dung chưa đạt ngưỡng từ");
                body.innerHTML = `<p style="color: var(--error);">Content lỗi: ${reason}</p>`;
              } else {
                body.innerHTML = '<p style="color: var(--warning);">Chưa có nội dung để hiển thị</p>';
              }
            } else {
              body.innerHTML =
                '<p style="color: var(--error);">Không thể tải nội dung</p>';
            }
          } catch (e) {
            body.innerHTML = '<p style="color: var(--error);">Lỗi kết nối</p>';
          }
        } else {
          body.innerHTML = loadedContents[index] || '<p style="color: var(--warning);">Nội dung trống</p>';
        }
      }

      // Copy content by index
      async function copyContentByIndex(index) {
        if (hasLoadedContent(index)) {
          try {
            await navigator.clipboard.writeText(loadedContents[index] || "");
            showToast("Đã copy nội dung HTML!", "success");
          } catch (e) {
            showToast("Không thể copy", "error");
          }
          return;
        }

        // Load first then copy
        try {
          const response = await fetch(`/api/content/${index}`);
          const result = await response.json();
          if (result.success) {
            loadedContents[index] = result.data.content || "";
            await navigator.clipboard.writeText(result.data.content || "");
            showToast("Đã copy nội dung HTML!", "success");
          }
        } catch (e) {
          showToast("Không thể copy", "error");
        }
      }

      async function requestRerenderByIndex(index) {
        if (!isRunning) {
          showToast("Chỉ có thể yêu cầu rend lại khi automation đang chạy", "warning");
          return;
        }

        let skipPost = false;
        if (["creating_posts", "retry_post_queue"].includes(currentPhase)) {
          const confirmed = await showConfirmDialog(
            "Đang trong quá trình đăng bài. Bạn muốn bỏ qua bài này để không đăng, hay tiếp tục đăng bình thường?",
            {
              title: "Đăng bài đang chạy",
              type: "warning",
              confirmText: "Bỏ qua bài này",
              cancelText: "Tiếp tục đăng",
            },
          );

          if (!confirmed) {
            showToast("Tiếp tục đăng bài hiện tại", "info");
            return;
          }
          skipPost = true;
        } else if (!["generating_content", "retry_content_queue"].includes(currentPhase)) {
          showToast("Chỉ thêm vào hàng chờ khi đang ở pha tạo content", "warning");
          return;
        }

        try {
          const response = await fetch(`/api/content/${index}/rerender`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ skip_post: skipPost }),
          });
          const result = await response.json();

          if (result.success) {
            showToast(result.message || "Đã xử lý yêu cầu rend lại", "success");
            return;
          }
          if (result.requires_confirmation) {
            showToast(result.message || "Cần xác nhận trước khi bỏ qua bài đăng", "warning");
            return;
          }
          showToast(result.message || "Không thể yêu cầu rend lại", "error");
        } catch (e) {
          showToast("Lỗi kết nối khi yêu cầu rend lại", "error");
        }
      }

      // Clear content list
      function clearContentList() {
        loadedContents = {};
        contentListRenderSignature = "";
        openedAccordionIndex = null;
        document.getElementById("contentListEmpty").style.display = "block";
        document.getElementById("contentAccordion").innerHTML = "";
        document.getElementById("contentCount").textContent = "(0)";
      }

      // Edit modal functions
      let currentEditIndex = null;

      async function openEditModal(index) {
        currentEditIndex = index;

        // Load content if not loaded
        let title = "";
        if (!hasLoadedContent(index)) {
          try {
            const response = await fetch(`/api/content/${index}`);
            const result = await response.json();
            if (result.success) {
              loadedContents[index] = result.data.content || "";
              title = result.data.title;
            }
          } catch (e) {
            showToast("Không thể tải nội dung", "error");
            return;
          }
        }

        // Set title
        document.getElementById("editTitle").textContent = title;

        // Set content in textarea
        document.getElementById("editContentArea").value =
          loadedContents[index];

        // Update word count and preview
        updateEditPreview();

        // Show modal
        document.getElementById("editModal").style.display = "flex";
      }

      function closeEditModal() {
        document.getElementById("editModal").style.display = "none";
        document.getElementById("editPreview").innerHTML = "";
        currentEditIndex = null;
      }

      function updateEditPreview() {
        const content = document.getElementById("editContentArea").value;

        // Update preview
        document.getElementById("editPreview").innerHTML = content;

        // Update word count
        const textOnly = content
          .replace(/<[^>]*>/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        const wordCount = textOnly
          .split(" ")
          .filter((w) => w.length > 0).length;
        document.getElementById("editWordCount").textContent =
          wordCount.toLocaleString();
      }

      async function saveEditContent() {
        if (currentEditIndex === null) return;

        const newContent = document.getElementById("editContentArea").value;

        try {
          const response = await fetch(`/api/content/${currentEditIndex}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: newContent }),
          });

          const result = await response.json();
          if (result.success) {
            // Update local cache
            loadedContents[currentEditIndex] = newContent;

            // Update accordion body if open
            const body = document.getElementById(
              `accordion-body-${currentEditIndex}`,
            );
            if (body && body.classList.contains("open")) {
              body.innerHTML = newContent;
            }

            showToast("Đã lưu thay đổi!", "success");
            closeEditModal();

            // Force refresh content list
            const statusResponse = await fetch("/api/status");
            const status = await statusResponse.json();
            if (status.content_list) {
              // Force re-render by clearing first
              document.getElementById("contentAccordion").innerHTML = "";
              renderContentList(status.content_list);
            }
          } else {
            showToast("Không thể lưu", "error");
          }
        } catch (e) {
          showToast("Lỗi kết nối", "error");
        }
      }

      async function deleteContentByIndex(index) {
        const confirmed = await showConfirmDialog(
          "Bạn có chắc muốn xóa nội dung này?",
          {
            title: "Xóa nội dung",
            type: "danger",
            confirmText: "Xóa",
            cancelText: "Hủy",
          },
        );

        if (!confirmed) return;

        try {
          const response = await fetch(`/api/content/${index}`, {
            method: "DELETE",
          });

          const result = await response.json();
          if (result.success) {
            // Remove from local cache
            delete loadedContents[index];

            // Refresh content list
            const statusResponse = await fetch("/api/status");
            const status = await statusResponse.json();

            // Clear and re-render
            document.getElementById("contentAccordion").innerHTML = "";
            loadedContents = {}; // Reset cache as indices changed

            if (status.content_list && status.content_list.length > 0) {
              renderContentList(status.content_list);
            } else {
              document.getElementById("contentListEmpty").style.display =
                "block";
              document.getElementById("contentCount").textContent = "(0)";
            }

            showToast("Đã xóa nội dung!", "success");
          } else {
            showToast("Không thể xóa", "error");
          }
        } catch (e) {}
      }

      // Toast notification
      function showToast(message, type = "info") {
        const toast = document.getElementById("toast");
        const toastMessage = document.getElementById("toastMessage");

        toast.className = "toast " + type;
        toastMessage.textContent = message;
        toast.classList.add("show");

        setTimeout(() => {
          toast.classList.remove("show");
        }, 3000);
      }
