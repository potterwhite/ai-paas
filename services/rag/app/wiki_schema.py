# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Wiki schema loader and token-budget manager."""

from pathlib import Path

import aiofiles

from app.config import settings, get_vault_path

# Conservative estimate: ~2.5 chars per token for mixed Chinese/English markdown
CHARS_PER_TOKEN = 2.5


class WikiSchema:
    """Loads and trims _schema/ instruction files."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    async def _read_file(self, rel_path: str) -> str:
        """Read a file from the vault. Returns empty string if missing."""
        full = get_vault_path() / rel_path
        if not full.exists():
            return ""
        async with aiofiles.open(full, "r", encoding="utf-8") as f:
            return await f.read()

    def _schema_path(self, filename: str) -> str:
        """Build relative path to a schema file."""
        return f"{settings.WIKI_SCHEMA_PATH}/{filename}"

    async def get_schema(self, operation: str, token_budget: int = 2000) -> str:
        """Return trimmed schema text for the given operation.

        Args:
            operation: one of "ingest", "query", "lint"
            token_budget: max tokens to allocate for schema

        Returns:
            Schema markdown string, trimmed to fit budget
        """
        filename = f"{operation}.md"
        cache_key = f"{filename}:{token_budget}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        content = await self._read_file(self._schema_path(filename))
        if not content:
            return ""

        trimmed = self.trim_to_budget(content, token_budget)
        self._cache[cache_key] = trimmed
        return trimmed

    async def get_template(self, template_name: str) -> str:
        """Read a page template from _schema/templates/."""
        rel_path = f"{settings.WIKI_SCHEMA_PATH}/templates/{template_name}"
        return await self._read_file(rel_path)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for mixed Chinese/English markdown."""
        return int(len(text) / CHARS_PER_TOKEN)

    def trim_to_budget(self, text: str, max_tokens: int) -> str:
        """Trim text to fit within token budget, preserving section boundaries.

        Cuts at ## headings rather than mid-sentence so the LLM always
        receives complete instruction sections.
        """
        max_chars = int(max_tokens * CHARS_PER_TOKEN)

        if len(text) <= max_chars:
            return text

        lines = text.split("\n")
        result = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > max_chars:
                # If we're at a section boundary, stop here
                if line.startswith("## "):
                    break
                # Otherwise include this line (it's part of the current section)
                result.append(line)
                current_len += line_len
                break
            result.append(line)
            current_len += line_len

        return "\n".join(result)


wiki_schema = WikiSchema()
