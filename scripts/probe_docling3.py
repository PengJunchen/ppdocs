import asyncio
import httpx

DOCLING_BASE = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC"
API_KEY = "Db3S72tVSn2YeSw"

async def probe():
    async with httpx.AsyncClient(timeout=15.0) as client:
        headers = {"Authorization": f"Bearer {API_KEY}"}

        paths = [
            "/docling/health",
            "/docling/v1/convert/file/async",
            "/docling/docs",
            "/docling/openapi.json",
            "/SEDTAIGC/docling/health",
            "/health",
            "/docling",
        ]

        for path in paths:
            url = f"http://uatapi.shanghai-electric.com/apigatewaytest{path}"
            try:
                resp = await client.get(url, headers=headers)
                print(f"GET {path} -> {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"GET {path} -> ERROR: {e}")

        # Also try the full URL as-is but with /health
        url = f"{DOCLING_BASE}/docling/health"
        try:
            resp = await client.get(url, headers=headers)
            print(f"GET full/docling/health -> {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"ERROR: {e}")

        url = f"{DOCLING_BASE}/docling/v1/convert/file/async"
        try:
            resp = await client.post(
                url,
                headers=headers,
                files={"file": ("test.pdf", b"dummy", "application/pdf")},
            )
            print(f"POST docling/v1/convert/file/async -> {resp.status_code} {resp.text[:300]}")
        except Exception as e:
            print(f"POST ERROR: {e}")

asyncio.run(probe())
