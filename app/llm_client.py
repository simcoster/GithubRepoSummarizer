import json
import logging

from openai import AsyncOpenAI

from app.config import DEFAULT_NEBIUS_API_BASE, DEFAULT_NEBIUS_MODEL
from app.models import SummarizeResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a software project analyst. You will receive:
- the repository tree structure (or a compact summary for large repos)
- contents of key files selected from the repository

IMPORTANT: Do not invent or assume file paths, technologies, or patterns not present in the provided files.

Your task is to analyze this and return a JSON object with exactly three fields:

1. "summary": 2-3 sentences describing what the project does, its purpose, and who it's for.
   - Be specific. Avoid vague phrases like "a tool for managing..." or "a library that helps...".
   - If the project is well-known, go BEYOND the README — describe real-world impact, use cases, or how it works at a high level.
   - Do NOT just restate the README opening line. The summary should add insight, not repeat what's already written.
   - Do not repeat the project name more than once.

2. "technologies": array of strings — programming languages, frameworks, libraries, and build tools used.
   - Order by significance (primary language first).
   - ONLY include technologies explicitly present in the provided files (dependency files, imports, config files). Do not infer or guess.
   - ONLY include external languages, frameworks, and tools — not subprojects or components of this repo itself.
   - Deduplicate carefully.
   - Exclude transitive/minor dependencies.
   - Maximum 10 items.
   - Do not deduce build tools from project structure patterns — only list them if explicitly specified in the provided config files.
   - An empty dependency group (e.g. `security = []`) means NO dependencies — do not infer what might belong there.

3. "structure": 2-3 sentences on how the project is organized.
   - Base your answer ONLY on the actual files and directories provided. Do NOT invent file paths.
   - Explain the PURPOSE of key directories, not just their names.
   - Focus on code organization: where core logic lives, how it's divided, where tests are.
   - Do NOT mention build tools or technologies here — those belong in the technologies field.
   - If you can identify an architectural pattern (plugin system, monorepo, library+CLI, etc.), name it — but only if you see clear evidence of it in the provided files.
   - Example of BAD structure: "The project has src/, tests/, and docs/ directories."
   - Example of GOOD structure: "Core logic lives in src/core/. Tests mirror the source layout in tests/. The public API is exposed through a single entry point."

Respond ONLY with valid JSON. No markdown, no code fences, no explanation outside the JSON.
"""

USER_PROMPT_TEMPLATE = """\
Repository: {owner}/{repo}

{context}
"""


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_NEBIUS_API_BASE,
        model: str = DEFAULT_NEBIUS_MODEL,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def summarize(
        self, owner: str, repo: str, context: str
    ) -> SummarizeResponse:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            owner=owner, repo=repo, context=context
        )
        max_json_retries = 3
        for attempt in range(1, max_json_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                logger.error("LLM API call failed: %s", e)
                raise LLMError(f"LLM API call failed: {e}") from e

            raw = response.choices[0].message.content
            try:
                if not raw:
                    raise ValueError("LLM returned an empty response")
                data = json.loads(raw)
                return SummarizeResponse(
                    summary=data.get("summary", ""),
                    technologies=data.get("technologies", []),
                    structure=data.get("structure", ""),
                )
            except Exception as e:
                if attempt == max_json_retries:
                    logger.error(
                        "Failed to parse/validate LLM response on final attempt: %s",
                        str(e),
                    )
                    raise LLMError(
                        f"LLM response parse/validation failed after {max_json_retries} attempts: {e}"
                    ) from e
                logger.warning(
                    "Failed to parse/validate LLM response on attempt %s/%s. Retrying.",
                    attempt,
                    max_json_retries,
                )
                continue

        raise LLMError("LLM returned invalid JSON")
