"""RAG service main entry point."""

from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

from app.config import settings, APIKeyInfo
from app.rag_engine import search_vault, index_vault, get_index_status
from app.vault_writer import write_to_vault
from app.wiki_ingest import wiki_ingest
from app.wiki_query import wiki_query
from app.wiki_lint import wiki_lint


async def verify_api_key(authorization: Optional[str] = Header(None)) -> APIKeyInfo:
    """Verify API key from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization format")

    token = authorization[7:]

    api_key_info = settings.get_api_key(token)
    if not api_key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key_info


class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    loa_required: Optional[int] = None


def get_current_loa(api_key: APIKeyInfo) -> int:
    """Get LOA level from API key."""
    return api_key.loa_level


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]


class WriteRequest(BaseModel):
    query: str
    ai_content: str
    mode: str = "new"
    target_path: Optional[str] = None


class WriteResponse(BaseModel):
    path: str
    success: bool


class IndexResponse(BaseModel):
    status: str
    documents_indexed: int


class IndexStatusResponse(BaseModel):
    indexed_documents: int
    status: str
    error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"RAG service starting on port {settings.RAG_PORT}")
    print(f"Vault path: {settings.VAULT_PATH}")
    print(f"ChromaDB path: {settings.CHROMA_DB_PATH}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"Wiki schema path: {settings.WIKI_SCHEMA_PATH}")
    print(f"Wiki output path: {settings.WIKI_OUTPUT_PATH}")
    yield
    print("RAG service shutting down")


app = FastAPI(
    title="ai-paas Vault RAG",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/v1/health")
async def health_check():
    """Health check endpoint."""
    index_status = get_index_status()
    return {
        "status": "healthy",
        "service": "vault-rag",
        "vault_path": settings.VAULT_PATH,
        "indexed_documents": index_status.get("indexed_documents", 0),
    }


@app.post("/v1/vault/query", response_model=QueryResponse)
async def query_vault(
    request: QueryRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Query Vault notes and generate answer via LLM."""
    user_loa = get_current_loa(api_key)
    results = search_vault(request.query, top_k=request.top_k, user_loa=user_loa)

    if not results:
        return QueryResponse(
            answer="未找到相关笔记。",
            sources=[],
        )

    context_parts = []
    sources = []
    for i, result in enumerate(results, 1):
        context_parts.append(f"[{i}] {result.title}\n{result.snippet}")
        sources.append({
            "path": result.path,
            "relevance": result.relevance,
            "snippet": result.snippet[:200],
        })

    context = "\n\n".join(context_parts)
    prompt = f"""请仔细阅读以下笔记内容，然后回答用户问题。

【重要指示】
1. 尽可能详细地提取和总结相关信息
2. 如果问的是进度/计划，列出具体的任务、项目、周次等
3. 如果问的是日期相关的（如某周、某月），找出对应的周报/月报文件
4. 格式要清晰，使用标题和列表

用户问题：{request.query}

相关笔记：
{context}

请基于以上笔记内容回答。如果笔记中提到了相关内容，请详细列出；只有确实找不到时才说"没找到"。"""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ROUTER_BASE_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {str(e)}")

    return QueryResponse(
        answer=answer,
        sources=sources,
    )


@app.post("/v1/vault/write", response_model=WriteResponse)
async def write_to_vault_endpoint(
    request: WriteRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Write AI content back to Vault."""
    if request.mode not in ("new", "append"):
        raise HTTPException(status_code=400, detail="mode must be 'new' or 'append'")

    user_loa = get_current_loa(api_key)
    search_results = search_vault(request.query, top_k=3, user_loa=user_loa)
    source_docs = [r.path for r in search_results]

    result = await write_to_vault(
        query=request.query,
        ai_content=request.ai_content,
        mode=request.mode,
        target_path=request.target_path,
        source_docs=source_docs,
    )

    return WriteResponse(**result)


@app.post("/v1/vault/index/rebuild", response_model=IndexResponse)
async def rebuild_index(
    force: bool = False,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Rebuild the Vault index."""
    result = await index_vault(force=force)

    return IndexResponse(
        status="completed",
        documents_indexed=result.get("indexed", 0),
    )


@app.get("/v1/vault/index/status", response_model=IndexStatusResponse)
async def get_index_status_endpoint(api_key: APIKeyInfo = Depends(verify_api_key)):
    """Get the current index status."""
    return get_index_status()


# ── Wiki models ──────────────────────────────────────────────────────────


class WikiIngestRequest(BaseModel):
    source_path: str


class WikiIngestResponse(BaseModel):
    source_path: str
    pages_written: list[str]
    index_updated: bool


class WikiBatchIngestRequest(BaseModel):
    source_paths: list[str]
    concurrency: int = 3


class WikiBatchIngestResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[WikiIngestResponse]
    errors: list[dict]


class WikiQueryRequest(BaseModel):
    question: str


class WikiQueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    wiki_pages_used: list[str]


class WikiLintResponse(BaseModel):
    total_pages: int
    issues: list[dict]
    error_count: int
    warning_count: int
    info_count: int


# ── Wiki endpoints ───────────────────────────────────────────────────────


@app.post("/v1/wiki/ingest", response_model=WikiIngestResponse)
async def wiki_ingest_endpoint(
    request: WikiIngestRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Ingest a source document into the wiki."""
    try:
        result = await wiki_ingest.ingest(request.source_path)
        return WikiIngestResponse(
            source_path=result.source_path,
            pages_written=result.pages_written,
            index_updated=result.index_updated,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wiki ingest failed: {str(e)}")


@app.post("/v1/wiki/ingest/batch", response_model=WikiBatchIngestResponse)
async def wiki_batch_ingest_endpoint(
    request: WikiBatchIngestRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Batch ingest multiple source documents into the wiki."""
    results = await wiki_ingest.ingest_batch(
        request.source_paths,
        concurrency=request.concurrency,
    )

    succeeded = [r for r in results if r.pages_written]
    failed = [r for r in results if not r.pages_written and "ERROR" in r.log_entry]

    return WikiBatchIngestResponse(
        total=len(results),
        succeeded=len(succeeded),
        failed=len(failed),
        results=[
            WikiIngestResponse(
                source_path=r.source_path,
                pages_written=r.pages_written,
                index_updated=r.index_updated,
            )
            for r in results
            if r.pages_written
        ],
        errors=[
            {"path": r.source_path, "error": r.log_entry}
            for r in results
            if not r.pages_written
        ],
    )


@app.post("/v1/wiki/query", response_model=WikiQueryResponse)
async def wiki_query_endpoint(
    request: WikiQueryRequest,
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Query the wiki for answers."""
    try:
        result = await wiki_query.query(request.question)
        return WikiQueryResponse(
            answer=result.answer,
            citations=[c.model_dump() for c in result.citations],
            wiki_pages_used=result.wiki_pages_used,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wiki query failed: {str(e)}")


@app.get("/v1/wiki/lint", response_model=WikiLintResponse)
async def wiki_lint_endpoint(
    api_key: APIKeyInfo = Depends(verify_api_key),
):
    """Run lint checks on the wiki."""
    try:
        report = await wiki_lint.lint()
        return WikiLintResponse(
            total_pages=report.total_pages,
            issues=[i.model_dump() for i in report.issues],
            error_count=report.error_count,
            warning_count=report.warning_count,
            info_count=report.info_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wiki lint failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.RAG_HOST, port=settings.RAG_PORT)