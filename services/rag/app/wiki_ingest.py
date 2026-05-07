"""Wiki ingest engine — transforms source documents into structured wiki pages."""

import asyncio
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiofiles
import httpx
from pydantic import BaseModel

from app.config import settings, get_vault_path, get_wiki_path
from app.wiki_schema import wiki_schema

CHARS_PER_TOKEN = 2.5
TZ = timezone(timedelta(hours=8))


class WikiPage(BaseModel):
    """A parsed wiki page from LLM output."""
    category: str       # entity, concept, source, synthesis, question
    filename: str       # e.g. "SomeEntity.md"
    content: str        # full markdown with frontmatter


class IngestResult(BaseModel):
    """Result of a single ingest operation."""
    source_path: str
    pages_written: list[str]
    index_updated: bool
    log_entry: str


def _estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


def _now_iso() -> str:
    return datetime.now(TZ).isoformat()


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


async def _read_file(path: Path) -> str:
    if not path.exists():
        return ""
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return await f.read()


async def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)


async def _append_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "a", encoding="utf-8") as f:
        await f.write(content)


def _chunk_source(content: str, max_tokens: int) -> list[str]:
    """Split source document into chunks that fit within max_tokens.

    Strategy: split on ## headings first, then ### headings,
    then hard-split at paragraph boundaries.
    """
    max_chars = int(max_tokens * CHARS_PER_TOKEN)

    if len(content) <= max_chars:
        return [content]

    chunks = []
    current = []
    current_len = 0

    # Try splitting on ## headings
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)

    for section in sections:
        section_len = len(section)
        if current_len + section_len > max_chars and current:
            chunks.append("".join(current))
            current = [section]
            current_len = section_len
        else:
            current.append(section)
            current_len += section_len

    if current:
        chunks.append("".join(current))

    # If any chunk is still too large, split on ### headings
    result = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            result.append(chunk)
            continue

        sub_sections = re.split(r'(?=^### )', chunk, flags=re.MULTILINE)
        sub_current = []
        sub_len = 0
        for sub in sub_sections:
            if sub_len + len(sub) > max_chars and sub_current:
                result.append("".join(sub_current))
                sub_current = [sub]
                sub_len = len(sub)
            else:
                sub_current.append(sub)
                sub_len += len(sub)
        if sub_current:
            result.append("".join(sub_current))

    # Add chunk markers
    total = len(result)
    if total > 1:
        result = [f"[Chunk {i+1}/{total}]\n\n{chunk}" for i, chunk in enumerate(result)]

    return result


def _parse_wiki_pages(llm_response: str) -> list[WikiPage]:
    """Parse LLM response into structured WikiPage objects.

    Expects pages in this format:
    ```wiki-page
    category: entity
    filename: Foo.md
    ---
    content here
    ```
    """
    pages = []

    # Try closed blocks first, then unclosed (LLM may omit closing ```)
    pattern_closed = r'```wiki-page\s*\n(.*?)```'
    pattern_unclosed = r'```wiki-page\s*\n(.*)'
    matches = re.findall(pattern_closed, llm_response, re.DOTALL)
    if not matches:
        matches = re.findall(pattern_unclosed, llm_response, re.DOTALL)

    if not matches:
        # Fallback: treat entire response as a single concept page
        return [WikiPage(
            category="concept",
            filename="auto-generated.md",
            content=llm_response.strip(),
        )]

    for block in matches:
        lines = block.strip().split("\n")
        category = "concept"
        filename = "page.md"

        # Parse header lines (category: and filename:)
        content_start = 0
        for i, line in enumerate(lines):
            if line.lower().startswith("category:"):
                category = line.split(":", 1)[1].strip()
            elif line.lower().startswith("filename:"):
                raw_fn = line.split(":", 1)[1].strip()
                # LLM may output full paths like "_wiki/source/Foo.md"
                filename = Path(raw_fn).name
            elif line.strip() == "---":
                content_start = i
                break
            else:
                content_start = i
                break

        body = "\n".join(lines[content_start:]).strip()

        # If body doesn't start with frontmatter, add it
        if not body.startswith("---"):
            now = _now_iso()
            body = f"""---
type: {category}
title: "{filename.replace('.md', '')}"
created: {now}
updated: {now}
tags: [wiki, ai-generated, {category}]
status: seed
sources: []
loa_min: 1
---

{body}"""

        pages.append(WikiPage(
            category=category,
            filename=filename,
            content=body,
        ))

    return pages


def _build_ingest_prompt(schema: str, source_content: str, current_index: str, chunk_info: str = "") -> str:
    """Build the LLM prompt for ingest."""
    wiki_path = settings.WIKI_OUTPUT_PATH

    prompt = f"""{schema}

---

## 当前任务

请对以下源文档执行入库操作。

## 当前 wiki 目录索引

{current_index if current_index else "（索引为空，这是第一个入库的文档）"}

{chunk_info}

## 源文档内容

{source_content}

---

## 输出要求

请按照上述 schema 规范，为这篇源文档生成 wiki 页面。

每个页面用以下格式输出：

```wiki-page
category: entity|concept|source|synthesis|question
filename: 页面文件名.md
---
（完整的 wiki 页面内容，包含 frontmatter）
```

注意：
1. frontmatter 必须包含所有必填字段（type, title, created, updated, tags, status, sources, loa_min）
2. 每个页面必须有至少 2 个 [[双向链接]] created 和 updated 使用当前时间: {_now_iso()}
3. tags 必须包含 wiki 和 ai-generated
4. sources 必须包含源文档路径
"""
    return prompt


async def _call_llm(prompt: str, max_tokens: int = 1600) -> str:
    """Call LLM via router."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ROUTER_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.ROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.WIKI_LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def _update_index(new_pages: list[WikiPage]) -> None:
    """Programmatically update _wiki/index.md."""
    wiki_path = get_wiki_path()
    index_path = wiki_path / "index.md"
    content = await _read_file(index_path)

    if not content:
        # Create minimal index
        content = f"""---
type: meta
title: "Wiki 知识库索引"
updated: {_today()}
tags: [wiki, ai-generated, meta]
status: evergreen
loa_min: 1
---

# Wiki 知识库索引

> 最后更新: {_today()}

## 项目

## 领域

## 技术概念

## 最近文档

## 综合分析
"""

    # Build new entries
    category_map = {
        "entity": "项目",
        "concept": "技术概念",
        "source": "源文档",
        "synthesis": "综合分析",
        "question": "问答",
    }

    for page in new_pages:
        section_name = category_map.get(page.category, "最近文档")
        page_name = page.filename.replace(".md", "")
        page_path = f"_wiki/{page.category}/{page.filename}"
        entry = f"- [{page_name}]({page_path})"

        # Skip if already in index (dedup)
        if page_path in content:
            continue

        # Insert entry under the appropriate section heading
        pattern = rf"(## {section_name}\n)"
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + entry + "\n" + content[insert_pos:]

    # Update the date
    content = re.sub(
        r"updated: \d{4}-\d{2}-\d{2}",
        f"updated: {_today()}",
        content,
        count=1,
    )
    content = re.sub(
        r"最后更新: \d{4}-\d{2}-\d{2}",
        f"最后更新: {_today()}",
        content,
        count=1,
    )

    # Update page count (exclude meta files)
    page_count = sum(
        1 for _ in wiki_path.rglob("*.md")
        if _.name not in ("index.md", "hot.md", "log.md")
    )
    content = re.sub(
        r"总页面数: \d+",
        f"总页面数: {page_count}",
        content,
        count=1,
    )

    await _write_file(index_path, content)


async def _update_hot(new_pages: list[WikiPage]) -> None:
    """Programmatically update _wiki/hot.md."""
    wiki_path = get_wiki_path()
    hot_path = wiki_path / "hot.md"
    content = await _read_file(hot_path)

    if not content:
        content = f"""---
type: meta
title: "Hot Cache"
updated: {_today()}
tags: [wiki, ai-generated, meta]
status: evergreen
loa_min: 1
---

# Hot Cache — 最近活跃内容

> 滚动窗口: 最近 7 天

## 最近入库的文档

## 待处理
"""

    # Add new entries under "最近入库的文档"
    for page in new_pages:
        page_name = page.filename.replace(".md", "")
        page_path = f"_wiki/{page.category}/{page.filename}"
        entry = f"- [{page_name}]({page_path}) — {_today()}"

        # Skip if already in hot cache (dedup)
        if page_path in content:
            continue

        # Find the section and insert after the heading
        pattern = r"(## 最近入库的文档\n)"
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + entry + "\n" + content[insert_pos:]

    # Update date
    content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {_today()}", content, count=1)

    await _write_file(hot_path, content)


async def _append_log(source_path: str, pages: list[WikiPage]) -> str:
    """Append to _wiki/log.md."""
    wiki_path = get_wiki_path()
    log_path = wiki_path / "log.md"

    pages_str = ", ".join(f"[[{p.filename.replace('.md', '')}]]" for p in pages)
    entry = f"""## [{_now_iso()}] ingest | {Path(source_path).stem}
- 源文档: `{source_path}`
- 生成: {pages_str}
- 跳过: 无
"""

    if not await _read_file(log_path):
        await _write_file(log_path, f"# Wiki 操作日志\n\n> 追加写入，不修改已有记录\n\n{entry}")
    else:
        await _append_file(log_path, f"\n{entry}")

    return entry.strip()


class WikiIngest:
    """Ingest engine for wiki pages."""

    async def ingest(self, source_path: str) -> IngestResult:
        """Main ingest entry point.

        1. Read source document
        2. Read _schema/ingest.md
        3. Read _wiki/index.md
        4. If source too large, chunk it
        5. For each chunk, call LLM
        6. Parse wiki pages from LLM response
        7. Write wiki pages to _wiki/<category>/
        8. Update index.md, hot.md, log.md
        """
        vault_path = get_vault_path()
        wiki_path = get_wiki_path()

        # 1. Read source document
        source_full = vault_path / source_path
        source_content = await _read_file(source_full)
        if not source_content:
            raise FileNotFoundError(f"Source document not found: {source_path}")

        # 2. Read schema
        schema = await wiki_schema.get_schema("ingest", token_budget=2000)

        # 3. Read current index
        index_content = await _read_file(wiki_path / "index.md")

        # 4. Chunk if needed
        source_tokens = _estimate_tokens(source_content)
        available_tokens = 9600 - 200 - 2000 - 1500 - 1600  # overhead+schema+index+response
        chunks = _chunk_source(source_content, settings.WIKI_MAX_CHUNK_TOKENS)

        all_pages: list[WikiPage] = []

        # 5. Process each chunk
        for i, chunk in enumerate(chunks):
            chunk_info = f"[处理分块 {i+1}/{len(chunks)}]" if len(chunks) > 1 else ""
            prompt = _build_ingest_prompt(schema, chunk, index_content, chunk_info)

            try:
                response = await _call_llm(prompt, max_tokens=1600)
            except Exception as e:
                if i == 0:
                    raise
                # If later chunks fail, continue with what we have
                break

            pages = _parse_wiki_pages(response)
            all_pages.extend(pages)

        if not all_pages:
            raise RuntimeError("LLM returned no wiki pages")

        # 7. Write wiki pages (handle filename collisions)
        written_paths = []
        for page in all_pages:
            page_path = wiki_path / page.category / page.filename
            if page_path.exists():
                stem = page_path.stem
                suffix = page_path.suffix
                counter = 2
                while page_path.exists():
                    page_path = wiki_path / page.category / f"{stem}-{counter}{suffix}"
                    counter += 1
            await _write_file(page_path, page.content)
            written_paths.append(str(page_path.relative_to(vault_path)))

        # 8. Update index, hot, log
        await _update_index(all_pages)
        await _update_hot(all_pages)
        log_entry = await _append_log(source_path, all_pages)

        return IngestResult(
            source_path=source_path,
            pages_written=written_paths,
            index_updated=True,
            log_entry=log_entry,
        )

    async def ingest_batch(
        self,
        source_paths: list[str],
        concurrency: int = 3,
    ) -> list[IngestResult]:
        """Batch ingest multiple source documents with bounded concurrency."""
        semaphore = asyncio.Semaphore(concurrency)
        results: list[IngestResult] = []

        async def _ingest_one(path: str) -> IngestResult:
            async with semaphore:
                return await self.ingest(path)

        tasks = [_ingest_one(p) for p in source_paths]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(completed):
            if isinstance(result, Exception):
                # Create error result
                results.append(IngestResult(
                    source_path=source_paths[i],
                    pages_written=[],
                    index_updated=False,
                    log_entry=f"ERROR: {str(result)}",
                ))
            else:
                results.append(result)

        return results


wiki_ingest = WikiIngest()
