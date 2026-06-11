const CATEGORY_OPTIONS = [
  "全部",
  "汽车材料",
  "电池材料",
  "高分子材料",
  "金属材料",
  "复合材料",
  "半导体材料",
  "可持续材料",
  "轻量化材料",
  "固态电池材料",
  "回收材料"
];

const state = {
  index: [],
  archive: null,
  currentDate: "",
  activeCategory: "全部",
  query: "",
  highOnly: false
};

const el = {};

document.addEventListener("DOMContentLoaded", async () => {
  cacheElements();
  bindEvents();
  await loadIndexAndLatest();
});

function cacheElements() {
  el.currentDate = document.getElementById("current-date");
  el.updatedAt = document.getElementById("updated-at");
  el.statusText = document.getElementById("status-text");
  el.summaryNote = document.getElementById("summary-note");
  el.resultNote = document.getElementById("result-note");
  el.metricTotal = document.getElementById("metric-total");
  el.metricHigh = document.getElementById("metric-high");
  el.metricCategories = document.getElementById("metric-categories");
  el.metricSources = document.getElementById("metric-sources");
  el.searchInput = document.getElementById("search-input");
  el.datePicker = document.getElementById("date-picker");
  el.highOnly = document.getElementById("high-only");
  el.categoryFilter = document.getElementById("category-filter");
  el.newsList = document.getElementById("news-list");
  el.archiveList = document.getElementById("archive-list");
  el.categoryBreakdown = document.getElementById("category-breakdown");
}

function bindEvents() {
  el.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim().toLowerCase();
    renderNews();
  });

  el.datePicker.addEventListener("change", async (event) => {
    const value = event.target.value;
    if (!value) {
      return;
    }
    await loadArchive(value);
  });

  el.highOnly.addEventListener("change", (event) => {
    state.highOnly = event.target.checked;
    renderNews();
  });
}

async function loadIndexAndLatest() {
  setStatus("正在加载归档索引...");
  try {
    const response = await fetch("data/index.json");
    if (!response.ok) {
      throw new Error(`index.json 加载失败: ${response.status}`);
    }
    const index = await response.json();
    state.index = Array.isArray(index) ? index : [];

    renderCategoryFilter();
    renderArchiveList();

    if (!state.index.length) {
      setStatus("暂无归档数据");
      renderEmptyArchive("当前还没有生成任何归档，请先运行更新脚本。");
      return;
    }

    const latestDate = state.index[0].date;
    el.datePicker.value = latestDate;
    await loadArchive(latestDate);
  } catch (error) {
    console.error(error);
    setStatus("索引加载失败");
    renderError(el.newsList, "无法读取归档索引，请检查 data/index.json。");
    renderError(el.archiveList, "无法显示历史归档。");
    renderError(el.categoryBreakdown, "无法显示分类分布。");
  }
}

async function loadArchive(date) {
  setStatus(`正在加载 ${date} 归档...`);
  try {
    const response = await fetch(`data/archive/${date}.json`);
    if (!response.ok) {
      throw new Error(`archive load failed: ${response.status}`);
    }
    state.archive = await response.json();
    state.currentDate = date;
    el.datePicker.value = date;
    renderAll();
    setStatus("归档加载完成");
  } catch (error) {
    console.error(error);
    setStatus("归档加载失败");
    renderError(el.newsList, `未找到 ${date} 的归档数据。`);
  }
}

function renderAll() {
  renderMeta();
  renderMetrics();
  renderArchiveList();
  renderCategoryBreakdown();
  renderNews();
}

function renderMeta() {
  const archive = state.archive || {};
  el.currentDate.textContent = archive.date || "-";
  el.updatedAt.textContent = archive.updated_at || "-";
  const categories = Array.isArray(archive.categories) ? archive.categories : [];
  el.summaryNote.textContent = `${archive.news_count || 0} 条新闻，覆盖 ${categories.length} 个材料分类。`;
}

function renderMetrics() {
  const archive = state.archive || {};
  el.metricTotal.textContent = archive.news_count || 0;
  el.metricHigh.textContent = archive.high_priority_count || countHighPriority(archive.news || []);
  el.metricCategories.textContent = (archive.categories || []).length || 0;
  el.metricSources.textContent = archive.source_count || countUniqueSources(archive.news || []);
}

function renderCategoryFilter() {
  clear(el.categoryFilter);
  CATEGORY_OPTIONS.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    if (category === state.activeCategory) {
      button.classList.add("active");
    }
    button.textContent = category;
    button.addEventListener("click", () => {
      state.activeCategory = category;
      renderCategoryFilter();
      renderNews();
    });
    el.categoryFilter.appendChild(button);
  });
}

function renderArchiveList() {
  clear(el.archiveList);
  if (!state.index.length) {
    renderEmptyInto(el.archiveList, "暂无历史归档。");
    return;
  }

  state.index.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "archive-button";
    if (item.date === state.currentDate) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <strong>${item.date}</strong>
      <span>${item.count || 0} 条新闻 · ${formatDateTime(item.updated_at)}</span>
    `;
    button.addEventListener("click", async () => {
      await loadArchive(item.date);
    });
    el.archiveList.appendChild(button);
  });
}

function renderCategoryBreakdown() {
  clear(el.categoryBreakdown);
  const news = (state.archive && Array.isArray(state.archive.news)) ? state.archive.news : [];
  if (!news.length) {
    renderEmptyInto(el.categoryBreakdown, "暂无分类分布数据。");
    return;
  }

  const counts = new Map();
  news.forEach((item) => {
    counts.set(item.category, (counts.get(item.category) || 0) + 1);
  });

  const rows = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  const maxCount = rows[0][1];

  rows.forEach(([category, count]) => {
    const card = document.createElement("div");
    card.className = "breakdown-card";
    card.innerHTML = `
      <div class="news-topline">
        <strong>${escapeHtml(category)}</strong>
        <span class="news-source">${count} 条</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width: ${Math.max(12, (count / maxCount) * 100)}%"></div>
      </div>
    `;
    el.categoryBreakdown.appendChild(card);
  });
}

function renderNews() {
  clear(el.newsList);
  const archive = state.archive || {};
  const news = Array.isArray(archive.news) ? archive.news : [];
  const filtered = news.filter(matchesFilters);
  el.resultNote.textContent = `当前显示 ${filtered.length} / ${news.length || 0} 条新闻。`;

  if (!news.length) {
    renderEmptyInto(el.newsList, "该日期暂无新闻数据。");
    return;
  }

  if (!filtered.length) {
    renderEmptyInto(el.newsList, "当前筛选条件下没有结果，请调整关键词或筛选条件。");
    return;
  }

  filtered.forEach((item) => {
    el.newsList.appendChild(createNewsCard(item));
  });
}

function matchesFilters(item) {
  const matchesCategory = state.activeCategory === "全部" || item.category === state.activeCategory;
  const matchesPriority = !state.highOnly || item.priority === "高";
  const haystack = [
    item.title,
    item.source,
    item.category,
    item.summary,
    item.industry_impact,
    item.rd_inspiration,
    ...(Array.isArray(item.technical_points) ? item.technical_points : []),
    ...(Array.isArray(item.keywords) ? item.keywords : [])
  ]
    .join(" ")
    .toLowerCase();
  const matchesQuery = !state.query || haystack.includes(state.query);
  return matchesCategory && matchesPriority && matchesQuery;
}

function createNewsCard(item) {
  const card = document.createElement("article");
  card.className = `news-card ${item.priority === "高" ? "priority-high" : ""}`;

  const priorityClass = item.priority === "高" ? "high" : item.priority === "中" ? "medium" : "low";
  const technicalPoints = Array.isArray(item.technical_points) ? item.technical_points : [];
  const keywords = Array.isArray(item.keywords) ? item.keywords : [];

  card.innerHTML = `
    <div class="news-topline">
      <div class="news-meta">
        <span class="priority-badge ${priorityClass}">${escapeHtml(item.priority || "中")}优先级</span>
        <span class="category-badge">${escapeHtml(item.category || "未分类")}</span>
      </div>
      <span class="news-source">${escapeHtml(item.source || "未知来源")} · ${escapeHtml(item.published_at || "-")}</span>
    </div>

    <h3 class="news-title">
      <a href="${escapeAttribute(item.url || "#")}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(item.title || "未命名新闻")}
      </a>
    </h3>

    <p class="news-summary">${escapeHtml(item.summary || "暂无摘要。")}</p>

    <div class="news-body">
      <section class="news-block">
        <strong>关键技术点</strong>
        ${renderBulletList(technicalPoints, "暂无技术要点。")}
      </section>
      <section class="news-block">
        <strong>潜在产业影响</strong>
        <p>${escapeHtml(item.industry_impact || "暂无产业影响分析。")}</p>
      </section>
      <section class="news-block">
        <strong>对研发工作的启发</strong>
        <p>${escapeHtml(item.rd_inspiration || "暂无研发启发。")}</p>
      </section>
    </div>

    <div class="news-tags">
      ${keywords.map((keyword) => `<span class="keyword-tag">${escapeHtml(keyword)}</span>`).join("")}
    </div>

    <div class="news-links">
      <span class="news-source">原文来源：${escapeHtml(item.source || "未知来源")}</span>
      <a class="news-link" href="${escapeAttribute(item.url || "#")}" target="_blank" rel="noopener noreferrer">打开原文</a>
    </div>
  `;
  return card;
}

function renderBulletList(items, fallback) {
  if (!items.length) {
    return `<p>${escapeHtml(fallback)}</p>`;
  }
  return `<ul class="bullet-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function setStatus(message) {
  el.statusText.textContent = message;
}

function renderEmptyArchive(message) {
  renderEmptyInto(el.newsList, message);
  renderEmptyInto(el.archiveList, "暂无历史归档。");
  renderEmptyInto(el.categoryBreakdown, "暂无分类分布。");
}

function renderEmptyInto(node, message) {
  clear(node);
  const box = document.createElement("div");
  box.className = "empty-state";
  box.textContent = message;
  node.appendChild(box);
}

function renderError(node, message) {
  clear(node);
  const box = document.createElement("div");
  box.className = "error-state";
  box.textContent = message;
  node.appendChild(box);
}

function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function countHighPriority(news) {
  return news.filter((item) => item.priority === "高").length;
}

function countUniqueSources(news) {
  return new Set(news.map((item) => item.source)).size;
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}
