import asyncio
import httpx
import time

LB = "http://127.0.0.1:8000"


async def main():
    print("Starting async test...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Client created")
        r = await client.get(f"{LB}/health")
        print(f"LB: {r.json()}")

        # Test 5 sequential async requests
        for i in range(5):
            start = time.time()
            resp = await client.post(f"{LB}/query", json={"query": f"test {i}", "top_k": 1})
            lat = (time.time() - start) * 1000
            print(f"  {i+1}: {resp.status_code} in {lat:.0f}ms -> {resp.json().get('worker_id') if resp.status_code == 200 else 'FAIL'}")

    print("Done")


asyncio.run(main())