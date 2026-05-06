"""Wiki query engine — answers questions using wiki pages."""

import json
import re
from pathlib import Path

import aiofiles
import httpx
from pydantic import BaseModel

from app.config import settings, get_vault_path, get_wiki_path
from app.wiki_schema import wiki_schema

CHARS_PER_TOKEN = 2.5


class Citation(BaseModel):
    """A source citation in the answer."""
    path: str
    snippet: str
    relevance: str  # "primary" or "supporting"


class WikiQueryResult(BaseModel):
    """Result of a wiki query."""
    answer: str
    citations: list[Citation]
    wiki_pages_used: list[str]


def _estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


async def _read_file(path) -> str:
    from pathlib import Path
    p = Path(path) if not isinstance(path, Path) else path
    if not p.exists():
        return ""
    async with aiofiles.open(p, "r", encoding="utf-8") as f:
        return await f.read()


async def _call_llm(prompt: str, max_tokens: int = 1600) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ROUTER_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def _select_pages(schema: str, question: str, index: str, hot: str) -> list[str]:
    """LLM call 1: Select which wiki pages to read."""
    prompt = f"""{schema}

---

## 当前任务

用户提问：{question}

## Wiki 目录索引

{index}

## 热缓存

{hot}

---

请根据用户问题，从上面的索引中选择最相关的 wiki 页面（最多 5 个）。

索引中的条目格式为 `[页面名](_wiki/分类/文件名.md)`，请提取完整的路径。

输出格式（纯 JSON 数组，不要其他内容）：
```json
["_wiki/entity/xxx.md", "_wiki/concept/yyy.md"]
```

如果索引中没有任何与问题相关的页面，输出空数组：
```json
[]
```
"""
    response = await _call_llm(prompt, max_tokens=500)

    # Parse JSON array from response
    json_match = re.search(r'\[.*?\]', response, re.DOTALL)
    if json_match:
        try:
            paths = json.loads(json_match.group())
            return [p for p in paths if isinstance(p, str)][:5]
        except json.JSONDecodeError:
            pass

    # Fallback: extract paths from markdown links [name](_wiki/...)
    paths = re.findall(r'\(_wiki/[^)]+\.md\)', response)
    if paths:
        return [p.strip("()") for p in paths][:5]

    # Fallback 2: extract any _wiki/ paths
    paths = re.findall(r'_wiki/\S+\.md', response)
    return paths[:5]


async def _generate_answer(
    schema: str,
    question: str,
    wiki_pages: dict[str, str],
    source_details: dict[str, str] | None = None,
) -> tuple[str, list[Citation]]:
    """LLM call 2: Generate answer from wiki pages."""
    pages_text = ""
    for path, content in wiki_pages.items():
        pages_text += f"\n\n--- 页面: {path} ---\n{content}"

    if source_details:
        pages_text += "\n\n--- 补充源文档 ---\n"
        for path, content in source_details.items():
            pages_text += f"\n--- {path} ---\n{content[:2000]}\n"

    prompt = f"""{schema}

---

## 当前任务

用户提问：{question}

## Wiki 页面内容

{pages_text}

---

请基于以上 wiki 页面内容回答用户问题。

要求：
1. 用中文回答（除非用户用英文提问）
2. 英文技术术语保持原文
3. 每个关键信息点必须附带来源：根据 [[页面名]]，...
4. 如果 wiki 中没有足够信息，明确说明"Wiki 中未找到关于 [主题] 的信息"
5. 回答末尾列出所有引用的来源
"""
    answer = await _call_llm(prompt, max_tokens=1600)

    # Extract citations from answer
    citations = []
    for path in wiki_pages:
        page_name = path.split("/")[-1].replace(".md", "")
        if f"[[{page_name}]]" in answer:
            citations.append(Citation(
                path=path,
                snippet=wiki_pages[path][:200],
                relevance="primary",
            ))

    return answer, citations


class WikiQuery:
    """Query engine for wiki."""

    async def query(self, question: str) -> WikiQueryResult:
        """Main query entry point."""
        vault_path = get_vault_path()
        wiki_path = get_wiki_path()

        # 1. Read schema
        schema = await wiki_schema.get_schema("query", token_budget=1500)

        # 2. Read index and hot
        index_content = await _read_file(wiki_path / "index.md")
        hot_content = await _read_file(wiki_path / "hot.md")

        # 3. LLM call 1: select pages
        page_paths = await _select_pages(schema, question, index_content, hot_content)

        # Validate paths exist on disk
        valid_paths = []
        for p in page_paths:
            full = vault_path / p
            if full.exists():
                valid_paths.append(p)
            else:
                # Try to find by filename in wiki directory
                fname = Path(p).name
                found = list(wiki_path.rglob(fname))
                if found:
                    valid_paths.append(str(found[0].relative_to(vault_path)))

        page_paths = valid_paths

        if not page_paths:
            return WikiQueryResult(
                answer="Wiki 中未找到相关内容。可能原因：1) 尚未 ingest 相关文档；2) 问题不在已入库的知识范围内。请先运行 `wiki-batch run` 将更多文档入库。",
                citations=[],
                wiki_pages_used=[],
            )

        # 4. Read selected pages
        wiki_pages = {}
        for path in page_paths:
            full_path = vault_path / path
            content = await _read_file(full_path)
            if content:
                wiki_pages[path] = content

        # 5. Check for thin pages and supplement with source docs
        source_details = {}
        for path, content in wiki_pages.items():
            if _estimate_tokens(content) < 200:
                # Try to find source_path in frontmatter
                source_match = re.search(r'sources:\s*\n\s*-\s*"([^"]+)"', content)
                if source_match:
                    source_path = source_match.group(1)
                    source_content = await _read_file(vault_path / source_path)
                    if source_content:
                        source_details[source_path] = source_content

        # 6. LLM call 2: generate answer
        answer, citations = await _generate_answer(
            schema, question, wiki_pages, source_details,
        )

        return WikiQueryResult(
            answer=answer,
            citations=citations,
            wiki_pages_used=list(wiki_pages.keys()),
        )


wiki_query = WikiQuery()
