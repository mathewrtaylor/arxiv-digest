# arXiv AI Daily Digest

Fetches new AI research papers from Cornell's arXiv (`cs.AI` category), summarizes them in plain English using the Claude API, and saves a daily Markdown digest.

## Setup

```bash
cd /home/mathew/Documents/claude/arxiv-digest
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
python3 src/arxiv_digest.py
```

Output files:
- `output/ai_digest_YYYY-MM-DD.md` — the daily digest
- `log/arxiv_digest_YYYY-MM-DD.log` — run log

## Configuration

Edit `config/settings.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `arxiv_url` | `https://arxiv.org/list/cs.AI/new` | arXiv listing page |
| `output_dir` | `output` | Directory for digest files |
| `log_dir` | `log` | Directory for log files |
| `model` | `claude-sonnet-4-6` | Claude model to use |
| `batch_size` | `5` | Papers per API call |
| `max_papers` | `50` | Maximum papers to process |

## Cron Job

Run daily at 8:00 AM:

```bash
# crontab -e
0 8 * * * cd /home/mathew/Documents/claude/arxiv-digest && python3 src/arxiv_digest.py >> log/cron.log 2>&1
```

Make sure `ANTHROPIC_API_KEY` is exported in `~/.bashrc` (or `~/.profile` for cron):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Credits

Created by [Claude Sonnet 4.6](https://www.anthropic.com/claude) (Anthropic).
Orchestrated by [mathewrtaylor](https://github.com/mathewrtaylor).
