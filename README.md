# GitHub Repository Summarizer

A FastAPI service that takes a public GitHub repository URL and returns an LLM-generated summary of what the project does, what technologies it uses, and how it's structured.

## Setup & Run

### Prerequisites

- Python 3.10+
- A Nebius API key (sign up at [Nebius Token Factory](https://studio.nebius.com/))

### Installation

```bash
# Unzip the downloaded source code and navigate to it
cd GithubRepoSummarizer

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

Copy `.env.example` to `.env` and set your Nebius API key in that file:

```
NEBIUS_API_KEY=your-api-key-here
```

Additional environment variables (also set in `.env`):

| Variable | Default | Description |
|---|---|---|
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

# Windows PowerShell (Invoke-RestMethod)
$body = @{ github_url = "https://github.com/psf/requests" } | ConvertTo-Json -Compress
$response = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/summarize" -ContentType "application/json" -Body $body
$response | ConvertTo-Json -Depth 5

```

## Design Decisions

### Model Choice

**Qwen3-235B-A22B-Instruct-2507** — A strong instruction-following model on Nebius that works well with strict JSON output constraints and produces reliable project-level summaries from mixed repository context.

### Repository Processing Strategy

The core challenge is fitting the most informative parts of a repository into the LLM's context window. 
Total context is capped at ~80K characters to stay well within the model's token limit.

#### Directory tree
- A directory tree representation is always included: full tree for smaller repositories, summarized top-level breakdown for very large ones.
- If GitHub marks the recursive tree response as truncated, the service logs a warning and proceeds with the partial tree.

#### File selection and scoring
- Selected file contents are included using the scoring logic below.
- Individual files are truncated at 15K characters if needed.
- File fetching is done concurrently (with a semaphore) for speed.

**Skip rules**
- **Directories**: `node_modules/`, `.git/`, `vendor/`, `dist/`, `build/`, `__pycache__/`, virtual environments, IDE config folders, and other generated/dependency directories.
- **Binary files**: Images, fonts, archives, compiled objects, PDFs, media files — detected by file extension.
- **Lock files**: `package-lock.json`, `yarn.lock`, `poetry.lock`, `go.sum`, etc. — large and not informative for understanding a project.
- **Oversized files** (>500KB): Likely auto-generated, data dumps, or vendored code.

**Priority signals (combined scoring):**
1. **README files** — the single best source of project intent and description.
2. **Top-level high-priority project files** (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, etc.) — these receive the strongest non-README base score.
3. **Medium-priority project and infra files** (test/build configs, workflows, deployment files, and docs like `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`) — useful context when high-priority files are limited.
4. **Entry-point-like filenames** (`main`, `app`, `index`, `server`, `cli`, `__main__`, `mod`) — receive an additional score boost.
5. **Recognized config and source files** (by extension) — config formats (`.toml`, `.yaml`, `.json`, etc.) rank above general source code.
6. **Test source files** — source files whose names contain `test` get a bonus over other source files.
7. **Shallower and smaller files** — files closer to repo root and modest in size are favored; deeper and very large files are penalized.

