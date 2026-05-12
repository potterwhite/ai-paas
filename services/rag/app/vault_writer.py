"""Vault writer - write AI responses back to Obsidian Vault."""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import aiofiles

from app.config import get_vault_path


class VaultWriter:
    """Write AI-generated content back to Vault."""

    def __init__(self):
        self._tz = timezone(timedelta(hours=8))

    def _format_datetime(self, dt: Optional[datetime] = None) -> str:
        """Format datetime for frontmatter."""
        if dt is None:
            dt = datetime.now(self._tz)
        return dt.isoformat()

    def _generate_filename(self, query: str) -> str:
        """Generate filename from query."""
        safe_query = "".join(c if c.isalnum() or c in " -_" else "_" for c in query)
        safe_query = safe_query.strip()[:30]
        date_str = datetime.now(self._tz).strftime("%Y-%m-%d")
        return f"{date_str}_分析_{safe_query}.md"

    def _format_wiki_link(self, path: str) -> str:
        """Convert file path to Obsidian wiki link."""
        filename = Path(path).stem
        return f"[[{filename}]]"

    def _build_new_content(
        self,
        query: str,
        ai_content: str,
        source_docs: list[str],
    ) -> str:
        """Build new note content with frontmatter."""
        frontmatter_lines = [
            "---",
            "ai-generated: true",
            f'source-query: "{query}"',
            f"created: {self._format_datetime()}",
            "source-docs:",
        ]

        for doc in source_docs:
            frontmatter_lines.append(f"  - \"{doc}\"")

        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        title = f"AI 分析：{query}"
        body = [
            f"# {title}",
            "",
            "## 问题",
            query,
            "",
            "## 回答",
            ai_content,
            "",
            "## 参考文档",
        ]

        for doc in source_docs:
            body.append(f"- {self._format_wiki_link(doc)}")

        content = "\n".join(frontmatter_lines + body)
        return content

    def _build_append_content(
        self,
        existing_content: str,
        ai_content: str,
    ) -> str:
        """Build content for append mode."""
        timestamp = self._format_datetime()
        appended = [
            "",
            "---",
            "",
            f"## AI 分析 ({timestamp})",
            "",
            ai_content,
            "",
            "---",
        ]
        return existing_content + "\n".join(appended)

    async def write(
        self,
        query: str,
        ai_content: str,
        mode: str = "new",
        target_path: Optional[str] = None,
        source_docs: Optional[list[str]] = None,
    ) -> dict:
        """
        Write AI content to Vault.

        Args:
            query: Original user query
            ai_content: AI-generated content
            mode: "new" or "append"
            target_path: Target file path (for append mode or custom new)
            source_docs: List of source document paths

        Returns:
            dict with path and success status
        """
        vault_path = get_vault_path()
        source_docs = source_docs or []

        if mode == "append":
            if not target_path:
                raise ValueError("target_path required for append mode")

            file_path = vault_path / target_path
            if not file_path.exists():
                raise FileNotFoundError(f"Target file not found: {target_path}")

            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                existing_content = await f.read()

            new_content = self._build_append_content(existing_content, ai_content)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            return {
                "path": str(file_path.relative_to(vault_path)),
                "success": True,
            }

        else:
            if target_path:
                file_path = vault_path / target_path
            else:
                filename = self._generate_filename(query)
                file_path = vault_path / "Inbox" / "AI" / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)

            new_content = self._build_new_content(query, ai_content, source_docs)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            return {
                "path": str(file_path.relative_to(vault_path)),
                "success": True,
            }


vault_writer = VaultWriter()


async def write_to_vault(
    query: str,
    ai_content: str,
    mode: str = "new",
    target_path: Optional[str] = None,
    source_docs: Optional[list[str]] = None,
) -> dict:
    """Write to Vault (exported function)."""
    return await vault_writer.write(
        query=query,
        ai_content=ai_content,
        mode=mode,
        target_path=target_path,
        source_docs=source_docs,
    )