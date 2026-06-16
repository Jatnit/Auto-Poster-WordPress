      // ============================================================================
      // CUSTOM MODAL DIALOG (Replace native confirm/prompt)
      // ============================================================================

      /**
       * Show custom confirm dialog
       * @param {string} message - Message to display
       * @param {object} options - {title, icon, type: 'warning'|'error'|'info'}
       * @returns {Promise<boolean>}
       */
      function showConfirmDialog(message, options = {}) {
        return new Promise((resolve) => {
          const modal = document.getElementById("customModal");
          const modalHeader = document.getElementById("modalHeader");
          const modalIcon = document.getElementById("modalIcon");
          const modalTitle = document.getElementById("modalTitle");
          const modalMessage = document.getElementById("modalMessage");
          const modalInput = document.getElementById("modalInput");
          const modalConfirm = document.getElementById("modalConfirm");
          const modalCancel = document.getElementById("modalCancel");

          // Reset modal
          modalHeader.className = "modal-header";
          modalInput.style.display = "none";
          modalConfirm.className = "modal-btn modal-btn-confirm";

          // Set content
          modalTitle.textContent = options.title || "Xác nhận";
          modalMessage.textContent = message;
          modalConfirm.textContent = options.confirmText || "Xác nhận";
          modalCancel.textContent = options.cancelText || "Hủy";

          // Set icon and style based on type
          if (options.type === "warning" || options.type === "danger") {
            modalHeader.classList.add("warning");
            modalIcon.className = "fas fa-exclamation-triangle";
            if (options.type === "danger") {
              modalConfirm.className = "modal-btn modal-btn-danger";
            }
          } else if (options.type === "error") {
            modalHeader.classList.add("error");
            modalIcon.className = "fas fa-times-circle";
          } else {
            modalIcon.className = "fas fa-question-circle";
          }

          // Show modal
          modal.classList.add("show");

          // Handle confirm
          const handleConfirm = () => {
            modal.classList.remove("show");
            cleanup();
            resolve(true);
          };

          // Handle cancel
          const handleCancel = () => {
            modal.classList.remove("show");
            cleanup();
            resolve(false);
          };

          // Handle ESC key
          const handleKeydown = (e) => {
            if (e.key === "Escape") handleCancel();
            if (e.key === "Enter") handleConfirm();
          };

          // Handle click outside
          const handleOverlayClick = (e) => {
            if (e.target === modal) handleCancel();
          };

          // Cleanup listeners
          const cleanup = () => {
            modalConfirm.removeEventListener("click", handleConfirm);
            modalCancel.removeEventListener("click", handleCancel);
            document.removeEventListener("keydown", handleKeydown);
            modal.removeEventListener("click", handleOverlayClick);
          };

          // Add listeners
          modalConfirm.addEventListener("click", handleConfirm);
          modalCancel.addEventListener("click", handleCancel);
          document.addEventListener("keydown", handleKeydown);
          modal.addEventListener("click", handleOverlayClick);
        });
      }

      /**
       * Show custom prompt dialog
       * @param {string} message - Message to display
       * @param {string} defaultValue - Default input value
       * @param {object} options - {title, placeholder}
       * @returns {Promise<string|null>}
       */
      function showPromptDialog(message, defaultValue = "", options = {}) {
        return new Promise((resolve) => {
          const modal = document.getElementById("customModal");
          const modalHeader = document.getElementById("modalHeader");
          const modalIcon = document.getElementById("modalIcon");
          const modalTitle = document.getElementById("modalTitle");
          const modalMessage = document.getElementById("modalMessage");
          const modalInput = document.getElementById("modalInput");
          const modalConfirm = document.getElementById("modalConfirm");
          const modalCancel = document.getElementById("modalCancel");

          // Reset modal
          modalHeader.className = "modal-header";
          modalConfirm.className = "modal-btn modal-btn-confirm";

          // Set content
          modalTitle.textContent = options.title || "Nhập thông tin";
          modalMessage.textContent = message;
          modalIcon.className = "fas fa-edit";
          modalConfirm.textContent = options.confirmText || "Xác nhận";
          modalCancel.textContent = options.cancelText || "Hủy";

          // Show and setup input
          modalInput.style.display = "block";
          modalInput.value = defaultValue;
          modalInput.placeholder = options.placeholder || "";

          // Show modal
          modal.classList.add("show");

          // Focus input after animation
          setTimeout(() => modalInput.focus(), 300);

          // Handle confirm
          const handleConfirm = () => {
            const value = modalInput.value.trim();
            modal.classList.remove("show");
            cleanup();
            resolve(value || null);
          };

          // Handle cancel
          const handleCancel = () => {
            modal.classList.remove("show");
            cleanup();
            resolve(null);
          };

          // Handle keydown
          const handleKeydown = (e) => {
            if (e.key === "Escape") handleCancel();
            if (e.key === "Enter") handleConfirm();
          };

          // Handle click outside
          const handleOverlayClick = (e) => {
            if (e.target === modal) handleCancel();
          };

          // Cleanup listeners
          const cleanup = () => {
            modalConfirm.removeEventListener("click", handleConfirm);
            modalCancel.removeEventListener("click", handleCancel);
            document.removeEventListener("keydown", handleKeydown);
            modal.removeEventListener("click", handleOverlayClick);
          };

          // Add listeners
          modalConfirm.addEventListener("click", handleConfirm);
          modalCancel.addEventListener("click", handleCancel);
          document.addEventListener("keydown", handleKeydown);
          modal.addEventListener("click", handleOverlayClick);
        });
      }
