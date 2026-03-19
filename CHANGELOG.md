# Changelog

## [1.0.0] — 2026-03-19

### Added
- Initial release
- Scrapes `cs.AI` new submissions from arXiv listing page
- Batched summarization via Claude API (configurable batch size)
- Plain-English summary + "why it matters" explanation per paper
- Daily Markdown digest output (`output/ai_digest_YYYY-MM-DD.md`)
- Dated log files (`log/arxiv_digest_YYYY-MM-DD.log`)
- YAML configuration (`config/settings.yaml`)
- Fallback to raw abstract on Claude API or JSON parse failure
