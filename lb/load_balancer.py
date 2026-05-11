import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_balancer")

app = FastAPI(title="Load Balancer")

MASTER_URL = os.environ.get("MASTER_URL", "")


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3


@app.post("/query")
async def handle_query(request: QueryRequest):
    if not MASTER_URL:
        logger.error("MASTER_URL not configured")
        raise HTTPException(status_code=500, detail="MASTER_URL not configured")

    logger.info("Received query, forwarding to master at %s", MASTER_URL)
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(MASTER_URL, json=request.model_dump())
            resp.raise_for_status()
            logger.info("Master responded with status %d", resp.status_code)
            return resp.json()
        except httpx.TimeoutException:
            logger.error("Master timed out")
            raise HTTPException(status_code=504, detail="Master timed out")
        except Exception as e:
            logger.error("Master unreachable: %s", str(e))
            raise HTTPException(status_code=503, detail=f"Master unreachable: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok", "role": "load_balancer", "master_url": MASTER_URL}


@app.get("/master")
async def get_master():
    return {"master_url": MASTER_URL}
