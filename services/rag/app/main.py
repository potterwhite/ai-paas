"""RAG service main entry point."""

from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

from app.config import settings
from app.rag_engine import search_vault, index_vault
from app.vault_writer import write_to_vault


async def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify API key from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization format")

    token = authorization[7:]

    if token not in settings.API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    loa_required: Optional[int] = None


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"RAG service starting on port {settings.RAG_PORT}")
    print(f"Vault path: {settings.VAULT_PATH}")
    print(f"ChromaDB path: {settings.CHROMA_DB_PATH}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
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
    return {"status": "healthy", "service": "vault-rag"}


@app.post("/v1/vault/query", response_model=QueryResponse)
async def query_vault(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key),
):
    """Query Vault notes and generate answer via LLM."""
    results = search_vault(request.query, top_k=request.top_k)

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
    prompt = f"""基于以下笔记内容回答用户问题。

用户问题：{request.query}

相关笔记：
{context}

请根据以上笔记内容回答。如果笔记中没有相关信息，请如实说明。"""

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
                    "max_tokens": 1000,
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
    api_key: str = Depends(verify_api_key),
):
    """Write AI content back to Vault."""
    if request.mode not in ("new", "append"):
        raise HTTPException(status_code=400, detail="mode must be 'new' or 'append'")

    search_results = search_vault(request.query, top_k=3)
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
    api_key: str = Depends(verify_api_key),
):
    """Rebuild the Vault index."""
    result = await index_vault(force=force)

    return IndexResponse(
        status="completed",
        documents_indexed=result.get("indexed", 0),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.RAG_HOST, port=settings.RAG_PORT)