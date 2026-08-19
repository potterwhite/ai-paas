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

"""Wiki lint engine — validates wiki structure and detects contradictions."""

import re
from pathlib import Path

import aiofiles
import yaml
from pydantic import BaseModel

from app.config import get_vault_path, get_wiki_path


class LintIssue(BaseModel):
    """A single lint issue."""
    severity: str       # error, warning, info
    category: str       # frontmatter, dead_link, orphan, contradiction
    file_path: str
    line_number: int | None = None
    message: str


class LintReport(BaseModel):
    """Complete lint report."""
    total_pages: int
    issues: list[LintIssue]
    error_count: int
    warning_count: int
    info_count: int


REQUIRED_FRONTMATTER = {"type", "title", "created", "updated", "tags", "status", "sources", "loa_min"}
VALID_TYPES = {"entity", "concept", "source", "synthesis", "question", "meta"}
VALID_STATUSES = {"seed", "developing", "mature", "evergreen"}


async def _read_file(path: Path) -> str:
    if not path.exists():
        return ""
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        return await f.read()


async def _collect_wiki_pages(wiki_path: Path) -> dict[str, str]:
    """Read all .md files under _wiki/ recursively."""
    pages = {}
    if not wiki_path.exists():
        return pages

    for md_file in wiki_path.rglob("*.md"):
        rel = str(md_file.relative_to(wiki_path.parent))  # relative to vault root
        content = await _read_file(md_file)
        if content:
            pages[rel] = content

    return pages


def _parse_frontmatter(content: str) -> dict | None:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def _extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wiki-links]] from content."""
    return re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', content)


def _check_frontmatter(path: str, content: str) -> list[LintIssue]:
    """Validate frontmatter required fields."""
    issues = []
    fm = _parse_frontmatter(content)

    if fm is None:
        # Check if it's index.md or hot.md (meta files, skip strict check)
        if "index.md" in path or "hot.md" in path or "log.md" in path:
            return issues
        issues.append(LintIssue(
            severity="error",
            category="frontmatter",
            file_path=path,
            message="Missing or malformed frontmatter",
        ))
        return issues

    # Skip strict field validation for meta files
    if not ("index.md" in path or "hot.md" in path or "log.md" in path):
        for field in REQUIRED_FRONTMATTER:
            if field not in fm:
                issues.append(LintIssue(
                    severity="error",
                    category="frontmatter",
                    file_path=path,
                    message=f"Missing required field: {field}",
                ))

    if fm.get("type") and fm["type"] not in VALID_TYPES:
        issues.append(LintIssue(
            severity="warning",
            category="frontmatter",
            file_path=path,
            message=f"Invalid type: {fm['type']}. Expected one of: {VALID_TYPES}",
        ))

    if fm.get("status") and fm["status"] not in VALID_STATUSES:
        issues.append(LintIssue(
            severity="warning",
            category="frontmatter",
            file_path=path,
            message=f"Invalid status: {fm['status']}. Expected one of: {VALID_STATUSES}",
        ))

    return issues


def _check_dead_links(all_pages: dict[str, str]) -> list[LintIssue]:
    """Find [[wiki-links]] that don't resolve to any existing page."""
    issues = []

    # Build set of all page names (without .md extension)
    page_names = set()
    for path in all_pages:
        name = Path(path).stem
        page_names.add(name)

    for path, content in all_pages.items():
        links = _extract_wikilinks(content)
        for link in links:
            # Skip external links or section links
            if "#" in link or "/" in link:
                continue
            # Check if link resolves
            if link not in page_names:
                issues.append(LintIssue(
                    severity="error",
                    category="dead_link",
                    file_path=path,
                    message=f"Dead link: [[{link}]] does not resolve to any wiki page",
                ))

    return issues


def _check_orphans(all_pages: dict[str, str]) -> list[LintIssue]:
    """Find pages not linked from index.md or any other page."""
    issues = []

    # Build set of all referenced page names
    referenced = set()
    for content in all_pages.values():
        links = _extract_wikilinks(content)
        for link in links:
            referenced.add(link)

    # Check each wiki page (exclude meta files)
    for path in all_pages:
        if "index.md" in path or "hot.md" in path or "log.md" in path:
            continue
        name = Path(path).stem
        if name not in referenced:
            issues.append(LintIssue(
                severity="warning",
                category="orphan",
                file_path=path,
                message=f"Orphan page: not linked from index.md or any other page",
            ))

    return issues


class WikiLint:
    """Lint engine for wiki pages."""

    async def lint(self) -> LintReport:
        """Main lint entry point."""
        vault_path = get_vault_path()
        wiki_path = get_wiki_path()

        # Collect all wiki pages
        all_pages = await _collect_wiki_pages(wiki_path)

        if not all_pages:
            return LintReport(
                total_pages=0,
                issues=[LintIssue(
                    severity="info",
                    category="frontmatter",
                    file_path="",
                    message="No wiki pages found. Run ingest first.",
                )],
                error_count=0,
                warning_count=0,
                info_count=1,
            )

        # Run programmatic checks
        all_issues: list[LintIssue] = []

        for path, content in all_pages.items():
            all_issues.extend(_check_frontmatter(path, content))

        all_issues.extend(_check_dead_links(all_pages))
        all_issues.extend(_check_orphans(all_pages))

        # Count by severity
        errors = sum(1 for i in all_issues if i.severity == "error")
        warnings = sum(1 for i in all_issues if i.severity == "warning")
        infos = sum(1 for i in all_issues if i.severity == "info")

        return LintReport(
            total_pages=len(all_pages),
            issues=all_issues,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
        )


wiki_lint = WikiLint()
