"""
材料新闻每日更新脚本
--------------------
能力：
1. 从可维护的 RSS 新闻源配置抓取候选新闻
2. 按关键词与时间窗口过滤，并做标题 / 链接去重
3. 调用 DeepSeek 生成结构化中文摘要、技术要点、产业影响和研发启发
4. 以日期为单位写入 archive，不覆盖历史其他日期
5. 更新 data/index.json 与 data/latest.json

环境变量：
- DEEPSEEK_API_KEY
- DEEPSEEK_MODEL，可选，默认 deepseek-chat
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
SOURCES_PATH = Path(__file__).resolve().parent / "news_sources.json"

MAX_NEWS = 8
MIN_NEWS = 3
MAX_CANDIDATES = 16
FETCH_WINDOW_DAYS = 10
API_RETRIES = 2

CATEGORY_OPTIONS = [
    "汽车材料",
    "电池材料",
    "高分子材料",
    "金属材料",
    "复合材料",
    "半导体材料",
    "可持续材料",
    "轻量化材料",
    "固态电池材料",
    "回收材料",
]

GLOBAL_KEYWORDS = [
    "material",
    "materials",
    "battery",
    "solid-state",
    "solid state",
    "electrolyte",
    "anode",
    "cathode",
    "separator",
    "recycling",
    "polymer",
    "composite",
    "composites",
    "semiconductor",
    "lightweight",
    "alloy",
    "aluminum",
    "aluminium",
    "magnesium",
    "steel",
    "carbon fiber",
    "carbon fibre",
    "mxene",
    "perovskite",
    "vehicle",
    "automotive",
    "ev",
    "electric vehicle",
    "sustainable",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; MaterialsNewsDaily/1.0; "
    "+https://github.com/your-org/materials-news-daily)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成每日材料新闻归档")
    parser.add_argument(
        "--date",
        help="指定归档日期，格式 YYYY-MM-DD；默认使用当天日期",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="目标新闻条数，默认 5，范围 3-8",
    )
    return parser.parse_args()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def iso_now_jst() -> str:
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).isoformat(timespec="seconds")


def parse_target_date(raw: Optional[str]) -> date:
    if not raw:
        return datetime.now(timezone(timedelta(hours=9))).date()
    return datetime.strptime(raw, "%Y-%m-%d").date()


def load_sources() -> List[Dict[str, Any]]:
    with SOURCES_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("news_sources.json 必须是数组")
    return data


def fetch_url(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = unescape(clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def normalize_text(text: str) -> str:
    lowered = strip_html(text).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", lowered)


def parse_feed_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    text = value.strip()
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        pass

    patterns = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for pattern in patterns:
        try:
            parsed = datetime.strptime(text, pattern)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def child_text(element: ET.Element, *names: str) -> str:
    for name in names:
        node = element.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def namespaced_text(element: ET.Element, namespace: Dict[str, str], *names: str) -> str:
    for name in names:
        node = element.find(name, namespace)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def parse_rss_feed(xml_text: str, source: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: List[Dict[str, Any]] = []

    if root.tag.endswith("rss") or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None:
            return items
        for idx, item in enumerate(channel.findall("item"), start=1):
            title = child_text(item, "title")
            link = child_text(item, "link")
            summary = child_text(item, "description", "summary")
            published_raw = child_text(item, "pubDate", "published", "updated")
            published_dt = parse_feed_datetime(published_raw)
            items.append(
                {
                    "candidate_id": f"{source['id']}-{idx}",
                    "title": title,
                    "url": link,
                    "source": source["name"],
                    "published_at": published_dt.date().isoformat() if published_dt else "",
                    "summary_snippet": strip_html(summary),
                    "source_homepage": source.get("homepage", ""),
                    "source_focus": source.get("focus_keywords", []),
                }
            )
        return items

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    for idx, entry in enumerate(root.findall("atom:entry", namespace), start=1):
        title = namespaced_text(entry, namespace, "atom:title")
        summary = namespaced_text(entry, namespace, "atom:summary", "atom:content")
        published_raw = namespaced_text(entry, namespace, "atom:updated", "atom:published")
        published_dt = parse_feed_datetime(published_raw)
        link = ""
        for link_node in entry.findall("atom:link", namespace):
            href = link_node.attrib.get("href", "")
            rel = link_node.attrib.get("rel", "alternate")
            if href and rel in ("alternate", ""):
                link = href
                break
        items.append(
            {
                "candidate_id": f"{source['id']}-{idx}",
                "title": title,
                "url": link,
                "source": source["name"],
                "published_at": published_dt.date().isoformat() if published_dt else "",
                "summary_snippet": strip_html(summary),
                "source_homepage": source.get("homepage", ""),
                "source_focus": source.get("focus_keywords", []),
            }
        )
    return items


def is_recent_enough(candidate: Dict[str, Any], target: date) -> bool:
    published_at = candidate.get("published_at", "")
    if not published_at:
        return True
    try:
        published_date = datetime.strptime(published_at, "%Y-%m-%d").date()
    except ValueError:
        return True
    earliest = target - timedelta(days=FETCH_WINDOW_DAYS)
    return earliest <= published_date <= target


def candidate_score(candidate: Dict[str, Any]) -> int:
    text = " ".join(
        [
            candidate.get("title", ""),
            candidate.get("summary_snippet", ""),
            " ".join(candidate.get("source_focus", [])),
        ]
    ).lower()
    score = 0
    for keyword in GLOBAL_KEYWORDS:
        if keyword in text:
            score += 1
    return score


def is_relevant(candidate: Dict[str, Any]) -> bool:
    return candidate_score(candidate) >= 2


def dedupe_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_titles = set()
    seen_links = set()
    output = []
    for item in candidates:
        title_key = normalize_text(item.get("title", ""))
        link_key = item.get("url", "").strip().lower()
        if not title_key or not link_key:
            continue
        if title_key in seen_titles or link_key in seen_links:
            continue
        seen_titles.add(title_key)
        seen_links.add(link_key)
        output.append(item)
    return output


def fetch_candidates(target: date) -> List[Dict[str, Any]]:
    sources = load_sources()
    all_candidates: List[Dict[str, Any]] = []

    for source in sources:
        rss_url = source.get("rss_url", "")
        if not rss_url:
            continue
        try:
            xml_text = fetch_url(rss_url)
            parsed = parse_rss_feed(xml_text, source)
            all_candidates.extend(parsed)
            print(f"[INFO] 抓取来源成功: {source['name']} ({len(parsed)} 条)")
        except Exception as error:
            print(f"[WARN] 抓取来源失败: {source['name']} -> {error}")

    deduped = dedupe_candidates(all_candidates)
    filtered = [item for item in deduped if is_recent_enough(item, target) and is_relevant(item)]
    filtered.sort(
        key=lambda item: (
            candidate_score(item),
            item.get("published_at", ""),
        ),
        reverse=True,
    )
    return filtered[:MAX_CANDIDATES]


def build_prompt(target_date: str, candidates: List[Dict[str, Any]], limit: int) -> str:
    candidate_payload = [
        {
            "candidate_id": item["candidate_id"],
            "title": item["title"],
            "source": item["source"],
            "url": item["url"],
            "published_at": item["published_at"],
            "summary_snippet": item["summary_snippet"][:500],
            "source_focus": item.get("source_focus", []),
        }
        for item in candidates
    ]
    return (
        "你是一位服务于汽车主机厂新材料开发工程师的信息分析助手。"
        "请从提供的候选新闻中，挑选最值得工程研发团队阅读的 3 到 8 条，"
        "重点关注车用材料、新能源材料、轻量化材料、高分子材料、金属材料、"
        "复合材料、半导体材料、固态电池材料、回收材料、可持续材料。"
        "避免泛泛而谈，强调工程研发、量产导入、供应链、可靠性和验证价值。\n\n"
        f"目标归档日期：{target_date}\n"
        f"目标条数：{limit}\n"
        f"允许分类：{', '.join(CATEGORY_OPTIONS)}\n\n"
        "输出必须是严格 JSON，结构如下：\n"
        "{\n"
        '  "news": [\n'
        "    {\n"
        '      "candidate_id": "候选ID",\n'
        '      "category": "分类",\n'
        '      "summary": "100-200字中文摘要",\n'
        '      "technical_points": ["技术点1", "技术点2"],\n'
        '      "industry_impact": "对汽车或新材料研发的潜在影响",\n'
        '      "rd_inspiration": "对研发工作的启发",\n'
        '      "priority": "高|中|低",\n'
        '      "keywords": ["关键词1", "关键词2", "关键词3"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "重要要求：\n"
        "1. 只能从给定候选中选择，不要虚构候选ID。\n"
        "2. 不要改写标题、来源、链接、发布日期，这些字段由系统回填。\n"
        "3. technical_points 给 2-4 条，keywords 给 3-6 条。\n"
        "4. priority 以研发价值和时效性判断。\n"
        "5. summary、industry_impact、rd_inspiration 必须是中文。\n\n"
        "候选新闻如下：\n"
        f"{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}"
    )


def call_deepseek(prompt: str) -> str:
    if not API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你输出结构化 JSON，且只基于给定候选新闻做研判。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8")


def extract_json_block(raw: str) -> Dict[str, Any]:
    payload = raw.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        payload = payload[start : end + 1]
    parsed = json.loads(payload)
    if "choices" in parsed:
        content = parsed["choices"][0]["message"]["content"]
        return extract_json_block(content)
    return parsed


def normalize_list(value: Any, minimum: int = 0, maximum: int = 99) -> List[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = strip_html(str(item))
        if text:
            items.append(text)
    return items[:maximum] if len(items) >= minimum else items[:maximum]


def normalize_priority(value: Any) -> str:
    text = strip_html(str(value or "")).strip()
    return text if text in {"高", "中", "低"} else "中"


def heuristic_category(text: str) -> str:
    lower = text.lower()
    mapping = [
        ("固态", "固态电池材料"),
        ("solid state", "固态电池材料"),
        ("solid-state", "固态电池材料"),
        ("电池", "电池材料"),
        ("battery", "电池材料"),
        ("电解质", "电池材料"),
        ("electrolyte", "电池材料"),
        ("半导体", "半导体材料"),
        ("semiconductor", "半导体材料"),
        ("高分子", "高分子材料"),
        ("polymer", "高分子材料"),
        ("回收", "回收材料"),
        ("recycling", "回收材料"),
        ("recycled", "回收材料"),
        ("可持续", "可持续材料"),
        ("sustainable", "可持续材料"),
        ("sustainability", "可持续材料"),
        ("复合材料", "复合材料"),
        ("composite", "复合材料"),
        ("碳纤维", "复合材料"),
        ("carbon fiber", "复合材料"),
        ("carbon fibre", "复合材料"),
        ("铝", "金属材料"),
        ("aluminum", "金属材料"),
        ("aluminium", "金属材料"),
        ("镁", "金属材料"),
        ("magnesium", "金属材料"),
        ("钢", "金属材料"),
        ("steel", "金属材料"),
        ("轻量化", "轻量化材料"),
        ("lightweight", "轻量化材料"),
        ("车", "汽车材料"),
        ("vehicle", "汽车材料"),
        ("automotive", "汽车材料"),
    ]
    for keyword, category in mapping:
        if keyword in lower:
            return category
    return "汽车材料"


def heuristic_priority(text: str) -> str:
    lower = text.lower()
    if any(
        keyword in lower
        for keyword in [
            "固态",
            "solid-state",
            "solid state",
            "battery",
            "电池",
            "semiconductor",
            "半导体",
            "recycling",
            "回收",
        ]
    ):
        return "高"
    if any(
        keyword in lower
        for keyword in ["复合材料", "composite", "高分子", "polymer", "alloy", "lightweight", "轻量化"]
    ):
        return "中"
    return "低"


def heuristic_item(candidate: Dict[str, Any]) -> Dict[str, Any]:
    title = candidate["title"]
    snippet = candidate.get("summary_snippet", "")
    focus = " ".join(candidate.get("source_focus", []))
    text = f"{title} {snippet} {focus}"
    category = heuristic_category(text)
    technical_points = []
    for keyword in ["固态电池", "电解质", "高镍", "复合材料", "高分子", "轻量化", "回收", "半导体"]:
        if keyword.lower() in text.lower() or keyword in text:
            technical_points.append(f"涉及{keyword}相关材料或工艺进展")
    if not technical_points:
        technical_points = [
            "建议重点关注材料体系变化与验证路径",
            "建议核对量产导入、成本与可靠性信息",
        ]

    short_snippet = snippet[:130] if snippet else "候选新闻来自材料相关公开资讯源，建议结合原文核对关键技术细节。"
    keywords = [category, "车用材料", "研发跟踪"]
    if "battery" in text.lower() or "电池" in text:
        keywords.append("电池材料")
    if "semiconductor" in text.lower() or "半导体" in text:
        keywords.append("半导体")
    if "recycling" in text.lower() or "回收" in text:
        keywords.append("材料回收")
    return {
        "title": title,
        "source": candidate["source"],
        "url": candidate["url"],
        "published_at": candidate.get("published_at") or "",
        "category": category,
        "summary": f"{short_snippet} 该信息已按车用材料研发视角做初步筛选，适合继续查看原文验证技术边界与产业化节奏。",
        "technical_points": technical_points[:3],
        "industry_impact": "对主机厂材料开发而言，建议关注其对供应链成熟度、验证周期、成本结构和量产窗口的影响。",
        "rd_inspiration": "可作为材料选型、竞品跟踪和预研立项时的输入，重点评估与现有平台需求的耦合度。",
        "priority": heuristic_priority(text),
        "keywords": keywords[:6],
    }


def build_news_with_deepseek(candidates: List[Dict[str, Any]], target_date: str, limit: int) -> List[Dict[str, Any]]:
    prompt = build_prompt(target_date, candidates, limit)
    candidate_map = {item["candidate_id"]: item for item in candidates}

    for attempt in range(1, API_RETRIES + 1):
        try:
            raw = call_deepseek(prompt)
            parsed = extract_json_block(raw)
            items = parsed.get("news", [])
            news = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidate_id = str(item.get("candidate_id", "")).strip()
                candidate = candidate_map.get(candidate_id)
                if not candidate:
                    continue
                news.append(
                    {
                        "title": candidate["title"],
                        "source": candidate["source"],
                        "url": candidate["url"],
                        "published_at": candidate.get("published_at", ""),
                        "category": item.get("category") if item.get("category") in CATEGORY_OPTIONS else heuristic_category(candidate["title"]),
                        "summary": strip_html(str(item.get("summary", "")))[:240],
                        "technical_points": normalize_list(item.get("technical_points"), maximum=4)[:4],
                        "industry_impact": strip_html(str(item.get("industry_impact", "")))[:220],
                        "rd_inspiration": strip_html(str(item.get("rd_inspiration", "")))[:220],
                        "priority": normalize_priority(item.get("priority")),
                        "keywords": normalize_list(item.get("keywords"), maximum=6)[:6],
                    }
                )
            if len(news) >= MIN_NEWS:
                return news[:MAX_NEWS]
            raise ValueError("DeepSeek 返回新闻数量不足")
        except Exception as error:
            print(f"[WARN] DeepSeek 第 {attempt} 次处理失败: {error}")
            if attempt < API_RETRIES:
                time.sleep(3)
    return []


def build_news_fallback(candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    output = []
    for candidate in candidates[: max(MIN_NEWS, limit)]:
        output.append(heuristic_item(candidate))
    return output[:MAX_NEWS]


def build_demo_candidates(target: date) -> List[Dict[str, Any]]:
    demos = [
        {
            "candidate_id": "demo-1",
            "title": "示例：材料科学频道关注固态电解质界面稳定性与循环寿命改进",
            "url": "https://www.sciencedaily.com/rss/matter_energy/materials_science.xml",
            "source": "ScienceDaily Materials Science",
            "published_at": target.isoformat(),
            "summary_snippet": "公开材料资讯源近期持续关注固态电池电解质界面工程、循环衰减机理与实验室验证进展。",
            "source_focus": ["materials", "battery", "solid-state"],
        },
        {
            "candidate_id": "demo-2",
            "title": "示例：汽车与运输板块聚焦轻量化结构材料与电动车平台集成",
            "url": "https://www.sciencedaily.com/rss/matter_energy/automotive_and_transportation.xml",
            "source": "ScienceDaily Automotive & Transportation",
            "published_at": (target - timedelta(days=1)).isoformat(),
            "summary_snippet": "公开资讯源近期围绕轻量化结构、复合材料与新能源汽车平台设计发布多篇相关信息。",
            "source_focus": ["automotive", "lightweight", "composite"],
        },
        {
            "candidate_id": "demo-3",
            "title": "示例：技术媒体持续报道半导体材料与功率器件可靠性演进",
            "url": "https://techxplore.com/rss-feed/materials-news/",
            "source": "Tech Xplore Materials News",
            "published_at": (target - timedelta(days=2)).isoformat(),
            "summary_snippet": "技术资讯源近期集中报道宽禁带半导体、封装热管理与器件材料可靠性相关动态。",
            "source_focus": ["semiconductor", "materials", "thermal"],
        },
        {
            "candidate_id": "demo-4",
            "title": "示例：绿色出行媒体关注电池回收与可持续材料供应链",
            "url": "https://www.greencarcongress.com/index.xml",
            "source": "Green Car Congress",
            "published_at": (target - timedelta(days=3)).isoformat(),
            "summary_snippet": "电动化资讯源持续关注电池回收、关键金属再利用和低碳材料供应链趋势。",
            "source_focus": ["recycling", "battery", "sustainable"],
        },
    ]
    return demos


def build_archive(target: date, limit: int) -> Dict[str, Any]:
    candidates = fetch_candidates(target)
    if not candidates:
        print("[WARN] 未抓取到有效候选，使用内置示例候选")
        candidates = build_demo_candidates(target)

    news = build_news_with_deepseek(candidates, target.isoformat(), limit) if API_KEY else []
    if not news:
        news = build_news_fallback(candidates, limit)

    news = news[: max(MIN_NEWS, min(MAX_NEWS, limit))]
    categories = sorted({item["category"] for item in news})
    high_priority_count = sum(1 for item in news if item["priority"] == "高")
    return {
        "date": target.isoformat(),
        "updated_at": iso_now_jst(),
        "news_count": len(news),
        "source_count": len({item["source"] for item in news}),
        "high_priority_count": high_priority_count,
        "categories": categories,
        "news": news,
    }


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def update_index(archive: Dict[str, Any]) -> None:
    index_path = DATA_DIR / "index.json"
    latest_path = DATA_DIR / "latest.json"
    archive_path = ARCHIVE_DIR / f"{archive['date']}.json"

    write_json(archive_path, archive)
    archive_summary = {
        "date": archive["date"],
        "count": archive["news_count"],
        "updated_at": archive["updated_at"],
    }

    index = read_json(index_path, [])
    if not isinstance(index, list):
        index = []

    updated = False
    for item in index:
        if isinstance(item, dict) and item.get("date") == archive["date"]:
            item["count"] = archive["news_count"]
            item["updated_at"] = archive["updated_at"]
            updated = True
            break

    if not updated:
        index.append(archive_summary)

    index = [item for item in index if isinstance(item, dict) and item.get("date")]
    index.sort(key=lambda item: item["date"], reverse=True)
    write_json(index_path, index)
    if index:
        write_json(latest_path, index[0])


def main() -> int:
    ensure_dirs()
    args = parse_args()
    target = parse_target_date(args.date)
    limit = min(MAX_NEWS, max(MIN_NEWS, args.limit))

    print(f"[INFO] 归档日期: {target.isoformat()}")
    print(f"[INFO] 目标条数: {limit}")
    print(f"[INFO] DeepSeek Key 已配置: {'是' if API_KEY else '否'}")
    print(f"[INFO] DeepSeek Model: {DEEPSEEK_MODEL}")

    try:
        archive = build_archive(target, limit)
        update_index(archive)
        print(f"[DONE] 已生成 {archive['date']} 归档，共 {archive['news_count']} 条新闻")
        return 0
    except Exception as error:
        print(f"[ERROR] 生成失败: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
