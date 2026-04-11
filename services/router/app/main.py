#
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
"""ai-paas GPU Router — FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine

from app.config import settings
from app.models.base import init_db
from app.api.routes import chat, audio, tasks, queue, gpu, models, keys, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init DB, check backends
    try:
        engine = create_engine(settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite"))
        init_db(engine)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Warning: Database init failed: {e}")
    yield
    # Shutdown: cleanup


app = FastAPI(
    title="ai-paas GPU Router",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(chat.router, prefix="/v1", tags=["chat"])
app.include_router(audio.router, prefix="/v1/audio", tags=["audio"])
app.include_router(tasks.router, prefix="/v1", tags=["tasks"])
app.include_router(queue.router, prefix="/v1", tags=["queue"])
app.include_router(gpu.router, prefix="/v1", tags=["gpu"])
app.include_router(models.router, prefix="/v1", tags=["models"])
app.include_router(keys.router, prefix="/v1", tags=["keys"])
