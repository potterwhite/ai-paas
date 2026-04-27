"""Core RAG engine with ChromaDB."""

import os
from pathlib import Path
from typing import Optional

import aiofiles
import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel

from app.config import settings, get_vault_path, get_chroma_path
from app.embedding import get_embedding, get_embeddings


class Document(BaseModel):
    """Document model for RAG."""
    id: str
    path: str
    content: str
    title: str
    tags: list[str] = []
    mtime: float = 0.0


class SearchResult(BaseModel):
    """Search result model."""
    path: str
    title: str
    content: str
    relevance: float
    snippet: str


class RAGEngine:
    """RAG engine for Vault notes."""

    def __init__(self):
        self.client: Optional[chromadb.PersistentClient] = None
        self.collection = None

    def _init_chroma(self):
        """Initialize ChromaDB client."""
        if self.client is None:
            chroma_path = get_chroma_path()
            chroma_path.mkdir(parents=True, exist_ok=True)
            
            self.client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                )
            )
            self.collection = self.client.get_or_create_collection(
                name=settings.COLLECTION_NAME,
                metadata={"description": "Obsidian Vault notes"}
            )

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
        """Extract YAML frontmatter from markdown content."""
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        frontmatter_raw = parts[1]
        body = parts[2].strip()

        frontmatter = {}
        for line in frontmatter_raw.strip().split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key in ("tags", "aliases"):
                frontmatter[key] = [t.strip().strip("-").strip() for t in value.split(",")]
            elif key in ("title",):
                frontmatter[key] = value
            else:
                frontmatter[key] = value

        return frontmatter, body

    def _extract_title(self, content: str, filename: str) -> str:
        """Extract title from content or filename."""
        frontmatter, body = self._extract_frontmatter(content)

        if "title" in frontmatter:
            return frontmatter["title"]

        lines = body.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()

        return filename.replace(".md", "")

    async def index_vault(self, force: bool = False) -> dict:
        """Index all markdown files in the Vault."""
        self._init_chroma()

        vault_path = get_vault_path()
        if not vault_path.exists():
            raise FileNotFoundError(f"Vault path not found: {vault_path}")

        md_files = list(vault_path.rglob("*.md"))
        total_files = len(md_files)
        
        existing_ids = set(self.collection.get(include=[])["ids"]) if not force else set()

        documents = []
        ids = []
        metadatas = []

        for md_file in md_files:
            rel_path = str(md_file.relative_to(vault_path))
            
            if not force and rel_path in existing_ids:
                continue

            try:
                async with aiofiles.open(md_file, "r", encoding="utf-8") as f:
                    content = await f.read()
            except Exception as e:
                print(f"Error reading {md_file}: {e}")
                continue

            frontmatter, body = self._extract_frontmatter(content)
            title = self._extract_title(content, md_file.name)
            tags = frontmatter.get("tags", [])
            mtime = md_file.stat().st_mtime

            documents.append(body)
            ids.append(rel_path)
            metadatas.append({
                "path": rel_path,
                "title": title,
                "tags": ",".join(tags) if tags else "",
                "mtime": mtime,
            })

        if documents:
            embeddings = get_embeddings(documents)
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

        return {
            "total_files": total_files,
            "indexed": len(documents),
            "collection_count": self.collection.count(),
        }

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search Vault notes by query."""
        self._init_chroma()

        query_embedding = get_embedding(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                document = results["documents"][0][i]
                distance = results["distances"][0][i]

                relevance = 1 - distance

                snippet = document[:500] + "..." if len(document) > 500 else document

                search_results.append(SearchResult(
                    path=metadata["path"],
                    title=metadata["title"],
                    content=document,
                    relevance=round(relevance, 3),
                    snippet=snippet,
                ))

        return search_results


rag_engine = RAGEngine()


def get_index_status() -> dict:
    """Get the current index status."""
    try:
        rag_engine._init_chroma()
        count = rag_engine.collection.count() if rag_engine.collection else 0
        return {
            "indexed_documents": count,
            "status": "ready",
        }
    except Exception as e:
        return {
            "indexed_documents": 0,
            "status": "error",
            "error": str(e),
        }


async def index_vault(force: bool = False) -> dict:
    """Index the Vault (exported function)."""
    return await rag_engine.index_vault(force=force)


def search_vault(query: str, top_k: int = 5) -> list[SearchResult]:
    """Search the Vault (exported function)."""
    return rag_engine.search(query, top_k=top_k)