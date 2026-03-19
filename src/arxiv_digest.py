#!/usr/bin/env python3
"""arXiv AI Daily Digest — fetches new cs.AI submissions and summarizes them with Claude."""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import anthropic
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


# ---------------------------------------------------------------------------
# Config + logging setup
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def setup_logging(log_dir: Path, today: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"arxiv_digest_{today}.log"

    logger = logging.getLogger("arxiv_digest")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_papers(url: str, max_papers: int, logger: logging.Logger) -> list[dict]:
    """Scrape new submissions from an arXiv listing page."""
    logger.info(f"Fetching {url}")
    resp = requests.get(url, timeout=30, headers={"User-Agent": "arxiv-digest/1.0 (research tool)"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the "New Submissions" section anchor then locate the <dl> that follows
    new_sub_anchor = soup.find("a", {"name": "new"}) or soup.find(id="new")

    # Fallback: find the first <dl> on the page which contains new submissions
    if new_sub_anchor:
        dl = new_sub_anchor.find_next("dl")
    else:
        dl = soup.find("dl")

    if not dl:
        logger.error("Could not locate submission list <dl> element on page.")
        return []

    dt_tags = dl.find_all("dt")
    dd_tags = dl.find_all("dd")

    papers = []
    for dt, dd in zip(dt_tags, dd_tags):
        if len(papers) >= max_papers:
            break

        # --- arXiv ID and link ---
        abs_link = dt.find("a", title="Abstract")
        if abs_link is None:
            continue
        arxiv_id = abs_link.text.strip().lstrip("[").rstrip("]")  # e.g. "arXiv:2506.01234"
        arxiv_id = arxiv_id.replace("arXiv:", "").strip()
        paper_url = f"https://arxiv.org/abs/{arxiv_id}"

        # --- Title ---
        title_div = dd.find("div", class_="list-title")
        if title_div:
            title = title_div.text.replace("Title:", "").strip()
        else:
            title = "(No title)"

        # --- Authors ---
        authors_div = dd.find("div", class_="list-authors")
        if authors_div:
            authors = authors_div.text.replace("Authors:", "").strip()
        else:
            authors = "(No authors listed)"

        # --- Abstract ---
        abstract_tag = dd.find("p", class_="mathjax")
        if abstract_tag is None:
            abstract_tag = dd.find("span", class_="abstract-short")
        abstract = abstract_tag.text.strip() if abstract_tag else "(No abstract available)"

        papers.append({
            "id": arxiv_id,
            "url": paper_url,
            "title": title,
            "authors": authors,
            "abstract": abstract,
        })

    logger.info(f"Found {len(papers)} new submissions (cap: {max_papers})")
    return papers


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

BATCH_PROMPT_TEMPLATE = """\
You are a research assistant. For each paper below, produce a plain-English summary \
suitable for a moderately technical reader (e.g., a software engineer who follows AI news).

Return ONLY a valid JSON array with one object per paper, in the same order as the input. \
Each object must have exactly these three fields:
- "title": the original paper title (copy verbatim)
- "summary": 3-4 sentences explaining what the paper does and how
- "importance": 2 sentences explaining why this work matters or what problem it solves

Papers:
{papers_json}
"""


def summarize_batch(client: anthropic.Anthropic, papers: list[dict], model: str, logger: logging.Logger) -> list[dict]:
    """Call Claude to summarize a batch of papers. Returns enriched paper dicts."""
    input_items = [{"title": p["title"], "abstract": p["abstract"]} for p in papers]
    prompt = BATCH_PROMPT_TEMPLATE.format(papers_json=json.dumps(input_items, indent=2))

    try:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        summaries = json.loads(raw)
    except (json.JSONDecodeError, IndexError, anthropic.APIError) as exc:
        logger.warning(f"Batch summarization failed ({exc}); falling back to abstracts.")
        summaries = [{"title": p["title"], "summary": p["abstract"], "importance": ""} for p in papers]

    # Merge summary data back into paper dicts
    enriched = []
    for paper, summary in zip(papers, summaries):
        enriched.append({
            **paper,
            "summary": summary.get("summary", paper["abstract"]),
            "importance": summary.get("importance", ""),
        })
    return enriched


def summarize_all(papers: list[dict], config: dict, logger: logging.Logger) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    model = config["model"]
    batch_size = config["batch_size"]

    enriched = []
    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(papers) + batch_size - 1) // batch_size
        logger.info(f"Summarizing batch {batch_num}/{total_batches} ({len(batch)} papers)…")
        enriched.extend(summarize_batch(client, batch, model, logger))

    return enriched


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def write_digest(papers: list[dict], output_dir: Path, today: str, source_url: str, logger: logging.Logger) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"ai_digest_{today}.md"

    lines = [
        f"# AI Research Digest — {today}",
        f"Source: {source_url}",
        "",
        f"*{len(papers)} new submissions summarized*",
        "",
        "---",
        "",
    ]

    for i, paper in enumerate(papers, start=1):
        lines += [
            f"## {i}. {paper['title']}",
            f"**Link:** {paper['url']}",
            f"**Authors:** {paper['authors']}",
            "",
            f"**Summary:** {paper['summary']}",
            "",
        ]
        if paper.get("importance"):
            lines += [f"**Why it matters:** {paper['importance']}", ""]
        lines += ["---", ""]

    out_file.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Digest written to {out_file}")
    return out_file


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    today = date.today().isoformat()
    config = load_config()

    log_dir = PROJECT_ROOT / config["log_dir"]
    output_dir = PROJECT_ROOT / config["output_dir"]
    logger = setup_logging(log_dir, today)

    logger.info("=== arXiv AI Digest starting ===")

    papers = fetch_papers(config["arxiv_url"], config["max_papers"], logger)
    if not papers:
        logger.error("No papers found. Exiting.")
        sys.exit(1)

    enriched = summarize_all(papers, config, logger)

    out_file = write_digest(enriched, output_dir, today, config["arxiv_url"], logger)

    logger.info(f"=== Done. {len(enriched)} papers → {out_file} ===")


if __name__ == "__main__":
    main()
