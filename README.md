# GitHub Repository Summarizer

A FastAPI service that takes a public GitHub repository URL and returns an LLM-generated summary of what the project does, what technologies it uses, and how it's structured.

## Setup & Run

### Prerequisites

- Python 3.10+
- A Nebius API key (sign up at [Nebius Token Factory](https://studio.nebius.com/))

### Installation

```bash
# Clone the repository and navigate to it
cd NebiusHomeAssigment

# Create a virtual environment
python -m venv .venv

# Activate it
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Set the required environment variable:

```bash
# Linux/macOS
export NEBIUS_API_KEY="your-api-key-here"

# Windows (PowerShell)
$env:NEBIUS_API_KEY = "your-api-key-here"
```

Optional environment variables:

| Variable | Default | Description |
|---|---|---|
| `NEBIUS_API_KEY` | *(required)* | Your Nebius Token Factory API key |
| `NEBIUS_API_BASE` | `https://api.tokenfactory.nebius.com/v1/` | Base URL for the LLM API |
| `NEBIUS_MODEL` | `Qwen/Qwen3-235B-A22B-Instruct-2507` | Model to use |
| `GITHUB_TOKEN` | *(none)* | Optional GitHub token to increase API rate limits |

### Running the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Linux/macOS
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'

# Windows PowerShell (use curl.exe, not Invoke-WebRequest aliases)
curl.exe -X POST http://localhost:8000/summarize `
  -H "Content-Type: application/json" `
  -d "{\"github_url\":\"https://github.com/psf/requests\"}"
```

## Design Decisions

### Model Choice

**Qwen3-235B-A22B-Instruct-2507** — A strong instruction-following model on Nebius that works well with strict JSON output constraints and produces reliable project-level summaries from mixed repository context.

### Repository Processing Strategy

The core challenge is fitting the most informative parts of a repository into the LLM's context window. Here's the approach:

**What gets skipped:**
- **Directories**: `node_modules/`, `.git/`, `vendor/`, `dist/`, `build/`, `__pycache__/`, virtual environments, IDE config folders, and other generated/dependency directories.
- **Binary files**: Images, fonts, archives, compiled objects, PDFs, media files — detected by file extension.
- **Lock files**: `package-lock.json`, `yarn.lock`, `poetry.lock`, `go.sum`, etc. — large and not informative for understanding a project.
- **Oversized files** (>500KB): Likely auto-generated, data dumps, or vendored code.

**What gets prioritized (in order):**
1. **README files** — the single best source of project intent and description.
2. **Entry points** (`main.py`, `index.js`, `app.py`, `server.go`, etc.) — reveal the application's structure and purpose.
3. **Package manifests** (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc.) — enumerate dependencies and project metadata.
4. **Config files** (`Dockerfile`, `docker-compose.yml`, CI configs) — reveal deployment and infrastructure choices.
5. **Top-level source files** — shallower files in the tree tend to be more architecturally significant.
6. **Other source files** — deeper files fill in details about implementation.

**Context management:**
- A directory tree representation is always included: full tree for smaller repositories, summarized top-level breakdown for very large ones.
- If GitHub marks the recursive tree response as truncated, the service logs a warning and proceeds with the partial tree.
- Files are scored by a priority function and fetched in priority order.
- Individual files are truncated at 15K characters if needed.
- Total context is capped at ~80K characters to stay well within the model's token limit.
- File fetching is done concurrently (with a semaphore) for speed.
