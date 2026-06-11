# 材料新闻每日更新与历史归档网站

一个面向汽车与新材料研发工程师的静态情报站，适合部署到 `GitHub Pages`。

项目重点不是泛新闻聚合，而是把公开材料资讯源中的候选新闻，整理成更适合研发团队快速浏览和后续跟踪的结构化内容，包括：

- 中文摘要
- 关键技术点
- 对汽车 / 新材料研发的潜在影响
- 对研发工作的启发
- 阅读优先级

## 适用场景

- 主机厂材料开发工程师日常行业扫描
- 新能源材料、轻量化、复合材料和半导体材料趋势跟踪
- 预研方向筛选
- 竞品材料路线与供应链动态观察
- 历史日期回看与技术主题检索

## 项目结构

```text
materials-news-daily/
├── index.html
├── style.css
├── app.js
├── data/
│   ├── index.json
│   ├── latest.json
│   └── archive/
│       ├── 2026-06-10.json
│       └── 2026-06-11.json
├── scripts/
│   ├── update_news.py
│   └── news_sources.json
├── .github/
│   └── workflows/
│       ├── daily-news.yml
│       └── deploy.yml
├── requirements.txt
└── README.md
```

## 网站功能

- 首页默认读取 `data/index.json`，自动展示最新日期归档
- 支持按日期切换历史新闻
- 支持关键词搜索标题、摘要、分类、技术要点和关键词
- 支持分类筛选
- 支持只看高优先级新闻
- 支持长期按日归档，不覆盖旧数据

## 数据结构

### `data/index.json`

```json
[
  {
    "date": "2026-06-11",
    "count": 4,
    "updated_at": "2026-06-11T23:10:24+09:00"
  }
]
```

### `data/archive/YYYY-MM-DD.json`

```json
{
  "date": "2026-06-11",
  "updated_at": "2026-06-11T23:10:24+09:00",
  "news_count": 4,
  "source_count": 4,
  "high_priority_count": 3,
  "categories": [
    "固态电池材料",
    "复合材料"
  ],
  "news": [
    {
      "title": "新闻标题",
      "source": "来源名称",
      "url": "https://example.com/news",
      "published_at": "2026-06-11",
      "category": "电池材料",
      "summary": "100-200字中文摘要",
      "technical_points": [
        "关键技术点1",
        "关键技术点2"
      ],
      "industry_impact": "对汽车或新材料研发的影响",
      "rd_inspiration": "对研发工作的启发",
      "priority": "高",
      "keywords": [
        "固态电池",
        "电解质",
        "车用材料"
      ]
    }
  ]
}
```

## 本地运行

### 1. 准备环境

项目脚本默认只使用 Python 标准库：

```bash
python3 --version
```

### 2. 配置 DeepSeek

请通过环境变量设置，不要把 Key 写进代码或提交到 GitHub：

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export DEEPSEEK_MODEL="deepseek-chat"
```

`DEEPSEEK_MODEL` 可不设置，默认使用 `deepseek-chat`。

### 3. 手动生成某天归档

```bash
python3 scripts/update_news.py --date 2026-06-11 --limit 5
```

参数说明：

- `--date`：指定归档日期，格式 `YYYY-MM-DD`
- `--limit`：当天目标新闻数，范围建议 `3-8`

如果不指定日期，则默认使用当前日期。

### 4. 本地预览网站

因为前端通过 `fetch` 读取 JSON，建议使用本地静态服务：

```bash
python3 -m http.server 8000
```

然后访问：

```text
http://localhost:8000
```

## 如何部署到 GitHub Pages

### 1. 推送仓库到 GitHub

把项目推送到你的 GitHub 仓库，例如默认分支 `main`。

### 2. 启用 Pages

进入仓库：

- `Settings`
- `Pages`
- `Build and deployment`
- `Source` 选择 `GitHub Actions`

仓库里已提供 [.github/workflows/deploy.yml](/Users/winky/Downloads/News-Brief-of-Automotive-New-Material-Industry-main/.github/workflows/deploy.yml:1)，推送后会自动部署整站。

## GitHub Secrets 配置

在仓库中进入：

- `Settings`
- `Secrets and variables`
- `Actions`

新增以下 Secrets：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`

建议：

- `DEEPSEEK_API_KEY`：填真实 API Key
- `DEEPSEEK_MODEL`：可填 `deepseek-chat`

如果你不设置 `DEEPSEEK_MODEL`，脚本本地会有默认值；但为了 GitHub Actions 行为明确，建议仍然配置。

## 每日自动更新

工作流文件是 [daily-news.yml](/Users/winky/Downloads/News-Brief-of-Automotive-New-Material-Industry-main/.github/workflows/daily-news.yml:1)。

当前使用：

```yaml
schedule:
  - cron: "0 22 * * *"
```

这个时间对应：

- `UTC 22:00`
- `Asia/Tokyo` 次日早上 `07:00`

也支持手动触发：

```yaml
workflow_dispatch:
```

工作流会自动：

1. 安装依赖
2. 运行 `python scripts/update_news.py`
3. 更新 `data/archive/YYYY-MM-DD.json`
4. 更新 `data/index.json`
5. 自动提交并推送最新数据

## 如何添加或维护新闻源

新闻源配置文件是 [scripts/news_sources.json](/Users/winky/Downloads/News-Brief-of-Automotive-New-Material-Industry-main/scripts/news_sources.json:1)。

每个新闻源建议包含：

- `id`
- `name`
- `rss_url`
- `homepage`
- `focus_keywords`

示例：

```json
{
  "id": "techxplore-materials",
  "name": "Tech Xplore Materials News",
  "rss_url": "https://techxplore.com/rss-feed/materials-news/",
  "homepage": "https://techxplore.com/materials-news/",
  "focus_keywords": ["materials", "semiconductor", "battery"]
}
```

后续扩展建议：

- 增加更多汽车材料、金属材料、聚合物或回收类 RSS 源
- 按来源设置权重
- 为不同来源增加专属关键词

## 新闻如何归档

脚本每次运行时：

- 只写入目标日期对应的 `data/archive/YYYY-MM-DD.json`
- 不删除其他日期归档
- 同时更新 `data/index.json`
- 同时更新 `data/latest.json`

如果某天已存在归档，再次运行会覆盖那一天的文件，但不会影响其他日期。

## 如何回看历史新闻

前端会：

1. 先读取 `data/index.json`
2. 自动找到最新日期
3. 加载对应 `data/archive/YYYY-MM-DD.json`
4. 在页面右侧展示历史日期列表
5. 点击任意日期即可切换当天全部新闻

你也可以用顶部日期选择器直接跳转。

## DeepSeek 调用策略

脚本不会让模型编造链接。

实现方式是：

1. 先从 RSS 抓取真实候选新闻
2. 把候选标题、来源、原文链接、发布时间传给 DeepSeek
3. 只让模型输出结构化摘要、分类、技术要点和影响判断
4. 最终标题、链接、来源字段仍以原始候选数据回填

这样可以尽量降低“链接瞎编”风险。

## 失败兜底

如果出现以下情况：

- RSS 抓取失败
- DeepSeek 调用失败
- 返回 JSON 结构不符合预期

脚本不会让站点崩掉，而是回退到内置示例候选，至少保持页面结构可浏览。

## 注意事项

- 不要把 `DEEPSEEK_API_KEY` 提交到 GitHub
- 建议优先使用 RSS 或公开新闻源，减少抓取不稳定性
- DeepSeek 生成内容仍建议人工抽查，尤其是关键技术判断和研发启发部分
- 如果你要用于正式团队内部分享，建议在脚本里再加一层来源白名单和标题相似度去重

## 继续增强的方向

- 为新闻增加“与车用场景相关性评分”
- 增加“本周热点主题”与“近 30 天高频关键词”
- 增加按来源筛选
- 增加归档页分页与年度归档导航
- 接入更多行业媒体或企业 newsroom
