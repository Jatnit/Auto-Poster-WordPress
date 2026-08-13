const SEO_MIN_WORDS = 600;
const SEO_MIN_DENSITY = 0.5;
const SEO_MAX_DENSITY = 2.5;
const SEO_MAX_URL_LENGTH = 75;

let seoLabTopicsState = [];
let seoLabStatusInterval = null;
let seoLabIsRunning = false;
let seoLoadedContents = {};
let seoSiteDomainLoaded = "";

function seoEscapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value || "";
  return div.innerHTML;
}

function normalizeSeoText(value) {
  return (value || "")
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function seoSlugify(value) {
  return normalizeSeoText(value)
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function showSeoToast(message, type = "info") {
  const toast = document.getElementById("toast");
  const toastMessage = document.getElementById("toastMessage");
  toast.className = `toast ${type}`;
  toastMessage.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3000);
}

function toggleSeoLabTheme() {
  const isLight = document.body.classList.toggle("light-theme");
  document.getElementById("themeIcon").className = isLight
    ? "fas fa-moon toggle-icon"
    : "fas fa-sun toggle-icon";
  document.getElementById("themeLabel").textContent = isLight ? "Dark" : "Light";
  localStorage.setItem("wp_theme", isLight ? "light" : "hacker");
}

function loadSeoLabTheme() {
  const saved = localStorage.getItem("wp_theme");
  if (saved === "light") {
    document.body.classList.add("light-theme");
    document.getElementById("themeIcon").className = "fas fa-moon toggle-icon";
    document.getElementById("themeLabel").textContent = "Dark";
  }
}

function renderSeoLabTopics() {
  const container = document.getElementById("seoLabTopics");
  document.getElementById("labTotalTopics").textContent = seoLabTopicsState.length;

  if (!seoLabTopicsState.length) {
    container.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-folder-open"></i>
        <p>Chưa có tiêu đề nào</p>
      </div>
    `;
    return;
  }

  container.innerHTML = seoLabTopicsState
    .map(
      (topic, index) => `
        <div class="topic-item fade-in">
          <span class="topic-number">${index + 1}</span>
          <div class="topic-content">
            <div class="topic-title">${seoEscapeHtml(topic.title)}</div>
            <div class="topic-keyword"><i class="fas fa-key"></i> ${seoEscapeHtml(topic.keyword)}</div>
            ${
              topic.tags
                ? `<div class="topic-tags" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;"><i class="fas fa-tags"></i> ${seoEscapeHtml(topic.tags)}</div>`
                : ""
            }
          </div>
          <button class="topic-delete" onclick="deleteSeoLabTopic(${index})">
            <i class="fas fa-times"></i>
          </button>
        </div>
      `,
    )
    .join("");
}

function loadSeoLabTopics() {
  try {
    seoLabTopicsState = JSON.parse(localStorage.getItem("wp_auto_topics") || "[]");
  } catch (_) {
    seoLabTopicsState = [];
  }
  renderSeoLabTopics();
}

async function saveSeoLabTopics() {
  localStorage.setItem("wp_auto_topics", JSON.stringify(seoLabTopicsState));
  await fetch("/api/topics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topics: seoLabTopicsState }),
  });
}

async function addSeoLabTitles() {
  const keyword = document.getElementById("labSharedKeyword").value.trim();
  const tags = document.getElementById("labSharedTags").value.trim();
  const titles = document
    .getElementById("labBulkTitles")
    .value.split("\n")
    .map((title) => title.trim())
    .filter(Boolean);

  if (!keyword) {
    showSeoToast("Vui lòng nhập Focus Keyword chung", "warning");
    return;
  }
  if (!titles.length) {
    showSeoToast("Vui lòng nhập ít nhất một tiêu đề", "warning");
    return;
  }

  let added = 0;
  for (const title of titles) {
    const duplicate = seoLabTopicsState.some(
      (topic) => normalizeSeoText(topic.title) === normalizeSeoText(title),
    );
    if (!duplicate) {
      seoLabTopicsState.push({ title, keyword, tags });
      added += 1;
    }
  }

  await saveSeoLabTopics();
  renderSeoLabTopics();
  document.getElementById("labBulkTitles").value = "";
  showSeoToast(`Đã thêm ${added} tiêu đề`, added ? "success" : "warning");
}

async function deleteSeoLabTopic(index) {
  seoLabTopicsState.splice(index, 1);
  await saveSeoLabTopics();
  renderSeoLabTopics();
}

async function clearSeoLabTopics() {
  seoLabTopicsState = [];
  await saveSeoLabTopics();
  renderSeoLabTopics();
  showSeoToast("Đã xóa list tiêu đề", "success");
}

async function startSeoLabAutomation() {
  if (!seoLabTopicsState.length) {
    showSeoToast("Cần thêm ít nhất một tiêu đề", "warning");
    return;
  }

  try {
    await saveSeoLabTopics();
    const response = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      showSeoToast(result.message || "Không thể bắt đầu", "error");
      return;
    }

    seoLabIsRunning = true;
    document.getElementById("statusDot").classList.add("running");
    document.getElementById("statusText").textContent = "Running";
    document.getElementById("labStartBtn").style.display = "none";
    document.getElementById("labStopBtn").style.display = "inline-flex";
    seoLoadedContents = {};
    seoLabStatusInterval = setInterval(updateSeoLabStatus, 1000);
    await updateSeoLabStatus();
    showSeoToast("Đã bắt đầu theo cấu hình hiện tại", "success");
  } catch (_) {
    showSeoToast("Lỗi kết nối server", "error");
  }
}

async function stopSeoLabAutomation() {
  try {
    await fetch("/api/stop", { method: "POST" });
  } catch (_) {}
  finishSeoLabRun("Stopped");
  showSeoToast("Đã dừng", "warning");
}

function finishSeoLabRun(label) {
  seoLabIsRunning = false;
  document.getElementById("statusDot").classList.remove("running");
  document.getElementById("statusText").textContent = label;
  document.getElementById("labStartBtn").style.display = "inline-flex";
  document.getElementById("labStopBtn").style.display = "none";
  if (seoLabStatusInterval) {
    clearInterval(seoLabStatusInterval);
    seoLabStatusInterval = null;
  }
}

async function updateSeoLabStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    const progress = Number(status.progress || 0);
    document.getElementById("labProgressBar").style.width = `${progress}%`;
    document.getElementById("labProgressValue").textContent = `${Math.round(progress)}%`;
    document.getElementById("labProgressPercent").textContent = `${Math.round(progress)}%`;
    document.getElementById("labCurrentTask").textContent = status.current_task || "Sẵn sàng";
    document.getElementById("labSuccessfulPosts").textContent = status.successful_posts || 0;
    document.getElementById("labFailedPosts").textContent = status.failed_posts || 0;
    renderSeoLabContentList(status.content_list || []);

    if (seoLabIsRunning && !status.is_running) {
      finishSeoLabRun("Completed");
      showSeoToast("Hoàn thành", "success");
    }
  } catch (_) {
    showSeoToast("Không thể cập nhật trạng thái", "error");
  }
}

function renderSeoLabContentList(contentList) {
  const container = document.getElementById("seoLabContentList");
  if (!contentList.length) {
    container.innerHTML = `
      <div class="content-preview-empty">
        <i class="fas fa-file-alt"></i>
        <p>Content đã tạo sẽ hiện ở đây</p>
      </div>
    `;
    return;
  }

  container.innerHTML = contentList
    .map((item, index) => {
      const failed = item.status === "failed";
      return `
        <div class="seo-lab-content-item">
          <div class="seo-lab-content-row">
            <div>
              <div class="seo-lab-content-title">${index + 1}. ${seoEscapeHtml(item.title)}</div>
              <div class="seo-lab-content-meta">
                <span><i class="fas fa-key"></i>${seoEscapeHtml(item.keyword)}</span>
                <span><i class="fas fa-file-lines"></i>${Number(item.word_count || 0).toLocaleString()} từ</span>
                <span class="content-status-tag ${failed ? "failed" : "success"}">${failed ? "Fail" : "OK"}</span>
              </div>
            </div>
            <button class="btn btn-primary" onclick="loadContentIntoSeoChecker(${index})">
              <i class="fas fa-clipboard-check"></i> Kiểm SEO
            </button>
          </div>
        </div>
      `;
    })
    .join("");
}

async function loadContentIntoSeoChecker(index) {
  try {
    const response = await fetch(`/api/content/${index}`);
    const result = await response.json();
    if (!result.success) {
      showSeoToast("Không tải được content", "error");
      return;
    }

    const data = result.data;
    const content = data.content || "";
    seoLoadedContents[index] = content;
    document.getElementById("seoFocusKeyword").value = data.keyword || "";
    document.getElementById("seoTitle").value = data.title || "";
    document.getElementById("seoUrl").value = buildSeoUrlGuess(data.title || "");
    document.getElementById("seoContentHtml").value = content;
    document.getElementById("seoMetaDescription").value = guessMetaDescription(content);
    runSeoChecks();
    showSeoToast(`Đã nạp bài #${index + 1} vào SEO checker`, "success");
  } catch (_) {
    showSeoToast("Lỗi kết nối khi tải content", "error");
  }
}

function buildSeoUrlGuess(title) {
  const slug = seoSlugify(title);
  if (!seoSiteDomainLoaded) return slug;
  return `${seoSiteDomainLoaded.replace(/\/$/, "")}/${slug}`;
}

function guessMetaDescription(html) {
  const text = getTextFromHtml(html).replace(/\s+/g, " ").trim();
  return text.slice(0, 160);
}

function getTextFromHtml(html) {
  const doc = new DOMParser().parseFromString(html || "", "text/html");
  return doc.body.textContent || "";
}

function getSeoHost(value) {
  const raw = (value || "").trim();
  if (!raw) return "";
  try {
    return new URL(raw.includes("://") ? raw : `https://${raw}`).hostname.replace(/^www\./, "");
  } catch (_) {
    return "";
  }
}

function getSeoWords(text) {
  return (text || "").split(/\s+/).filter(Boolean);
}

function countKeywordOccurrences(text, keyword) {
  const normalizedText = normalizeSeoText(text);
  const normalizedKeyword = normalizeSeoText(keyword);
  if (!normalizedText || !normalizedKeyword) return 0;
  return normalizedText.split(normalizedKeyword).length - 1;
}

function keywordInValue(value, keyword) {
  const normalizedValue = normalizeSeoText(value).replace(/[-_/]+/g, " ");
  const normalizedKeyword = normalizeSeoText(keyword);
  const slugKeyword = seoSlugify(keyword).replace(/-/g, " ");
  return Boolean(
    normalizedKeyword &&
      (normalizedValue.includes(normalizedKeyword) ||
        normalizedValue.includes(slugKeyword)),
  );
}

function getLinkStats(doc, siteDomain, pageUrl) {
  const pageHost = getSeoHost(pageUrl);
  const siteHost = getSeoHost(siteDomain) || pageHost;
  const links = Array.from(doc.querySelectorAll("a[href]"));
  const outbound = [];
  const internal = [];

  for (const link of links) {
    const href = (link.getAttribute("href") || "").trim();
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) {
      continue;
    }
    if (!/^https?:\/\//i.test(href)) {
      internal.push(link);
      continue;
    }
    const host = getSeoHost(href);
    if (siteHost && host === siteHost) internal.push(link);
    else outbound.push(link);
  }

  return {
    outbound,
    internal,
    outboundNoFollowCount: outbound.filter((link) =>
      (link.getAttribute("rel") || "").toLowerCase().split(/\s+/).includes("nofollow"),
    ).length,
  };
}

function buildSeoChecks() {
  const keyword = document.getElementById("seoFocusKeyword").value.trim();
  const title = document.getElementById("seoTitle").value.trim();
  const description = document.getElementById("seoMetaDescription").value.trim();
  const url = document.getElementById("seoUrl").value.trim();
  const siteDomain = document.getElementById("seoSiteDomain").value.trim();
  const html = document.getElementById("seoContentHtml").value;
  const usedKeywords = document.getElementById("seoUsedKeywords").value;
  const contentAiDone = document.getElementById("seoContentAiDone").checked;

  const doc = new DOMParser().parseFromString(html || "", "text/html");
  const contentText = doc.body.textContent || "";
  const words = getSeoWords(contentText);
  const firstTenPercent = words.slice(0, Math.max(1, Math.ceil(words.length * 0.1))).join(" ");
  const occurrences = countKeywordOccurrences(contentText, keyword);
  const density = words.length ? (occurrences / words.length) * 100 : 0;
  const headings = Array.from(doc.querySelectorAll("h2, h3, h4"));
  const images = Array.from(doc.querySelectorAll("img"));
  const links = getLinkStats(doc, siteDomain, url);
  const alreadyUsed = keywordInValue(usedKeywords, keyword);

  return [
    {
      title: "Basic SEO",
      checks: [
        {
          pass: keywordInValue(title, keyword),
          label: "Focus Keyword có trong SEO Title.",
        },
        {
          pass: keywordInValue(description, keyword),
          label: "Focus Keyword có trong SEO Meta Description.",
        },
        {
          pass: keywordInValue(url, keyword),
          label: "Focus Keyword có trong URL.",
        },
        {
          pass: keywordInValue(firstTenPercent, keyword),
          label: "Focus Keyword xuất hiện trong 10% đầu nội dung.",
        },
        {
          pass: keywordInValue(contentText, keyword),
          label: "Focus Keyword được tìm thấy trong nội dung.",
        },
        {
          pass: words.length >= SEO_MIN_WORDS,
          label: `Content dài ${words.length.toLocaleString()} từ.`,
          detail: words.length >= SEO_MIN_WORDS ? "Good job!" : `Nên đạt ít nhất ${SEO_MIN_WORDS.toLocaleString()} từ.`,
        },
      ],
    },
    {
      title: "Additional",
      checks: [
        {
          pass: headings.some((heading) => keywordInValue(heading.textContent || "", keyword)),
          label: "Focus Keyword có trong subheading H2/H3/H4.",
          detail: `${headings.length} heading được kiểm tra.`,
        },
        {
          pass: images.some((image) => keywordInValue(image.getAttribute("alt") || "", keyword)),
          label: "Focus Keyword có trong alt ảnh.",
          detail: `${images.length} ảnh được kiểm tra.`,
        },
        {
          pass: density >= SEO_MIN_DENSITY && density <= SEO_MAX_DENSITY,
          label: `Keyword Density là ${density.toFixed(2)}%.`,
          detail: `${occurrences} lần xuất hiện; nên nằm khoảng ${SEO_MIN_DENSITY}% - ${SEO_MAX_DENSITY}%.`,
        },
        {
          pass: url.length > 0 && url.length <= SEO_MAX_URL_LENGTH,
          label: `URL dài ${url.length} ký tự.`,
          detail: `Nên ngắn hơn hoặc bằng ${SEO_MAX_URL_LENGTH} ký tự.`,
        },
        {
          pass: links.outbound.length > 0,
          label: "Có liên kết ra external resources.",
          detail: `Tìm thấy ${links.outbound.length} outbound link.`,
        },
        {
          pass: links.outbound.length > 0 && links.outboundNoFollowCount === links.outbound.length,
          label: "Outbound links đều có nofollow.",
          detail: `${links.outboundNoFollowCount}/${links.outbound.length} link có nofollow.`,
        },
        {
          pass: links.internal.length > 0,
          label: "Có liên kết đến tài nguyên nội bộ.",
          detail: `Tìm thấy ${links.internal.length} internal link.`,
        },
        {
          pass: keyword.length > 0 && !alreadyUsed,
          label: "Focus Keyword chưa bị dùng trước đó.",
          detail: alreadyUsed ? "Có dấu hiệu trùng trong ô keyword/URL đã dùng." : "",
        },
        {
          pass: contentAiDone,
          label: "Đã tối ưu bằng Content AI.",
          detail: "Tick thủ công sau khi bạn đã xử lý bước này.",
        },
      ],
    },
    {
      title: "Title Readability",
      checks: [
        {
          pass: normalizeSeoText(title).startsWith(normalizeSeoText(keyword)) && keyword.length > 0,
          label: "Focus Keyword nằm ở đầu SEO title.",
        },
        {
          pass: /\d/.test(title),
          label: "SEO title có sử dụng số.",
        },
      ],
    },
  ];
}

function renderSeoChecks(groups) {
  const container = document.getElementById("seoCheckResults");
  let total = 0;
  let passed = 0;

  container.innerHTML = groups
    .map((group) => {
      const groupPassed = group.checks.filter((check) => check.pass).length;
      total += group.checks.length;
      passed += groupPassed;
      const allGood = groupPassed === group.checks.length;
      return `
        <section class="seo-check-group">
          <div class="seo-check-group-header">
            <span class="seo-check-group-title">${group.title}</span>
            <span class="seo-check-group-status">${allGood ? "All Good" : `${groupPassed}/${group.checks.length}`}</span>
          </div>
          <div class="seo-check-list">
            ${group.checks
              .map(
                (check) => `
                  <div class="seo-check-row ${check.pass ? "pass" : "fail"}">
                    <span class="seo-check-icon">
                      <i class="fas ${check.pass ? "fa-check" : "fa-xmark"}"></i>
                    </span>
                    <span>
                      ${seoEscapeHtml(check.label)}
                      ${check.detail ? `<div class="seo-check-detail">${seoEscapeHtml(check.detail)}</div>` : ""}
                    </span>
                  </div>
                `,
              )
              .join("")}
          </div>
        </section>
      `;
    })
    .join("");

  const percent = total ? Math.round((passed / total) * 100) : 0;
  document.getElementById("seoScoreText").textContent = `${passed} / ${total}`;
  document.getElementById("seoScoreFill").style.width = `${percent}%`;
}

function runSeoChecks() {
  renderSeoChecks(buildSeoChecks());
}

async function loadSeoLabConfig() {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    const adminUrl = config.wp_admin_url || "";
    const loginUrl = config.wp_login_url || "";
    const host = getSeoHost(adminUrl) || getSeoHost(loginUrl);
    if (host) {
      seoSiteDomainLoaded = `https://${host}`;
      document.getElementById("seoSiteDomain").value = seoSiteDomainLoaded;
    }
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", async () => {
  loadSeoLabTheme();
  loadSeoLabTopics();
  await loadSeoLabConfig();
  await updateSeoLabStatus();
  document.querySelectorAll(".seo-check-input").forEach((input) => {
    input.addEventListener("input", runSeoChecks);
    input.addEventListener("change", runSeoChecks);
  });
  runSeoChecks();
});
