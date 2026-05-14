import asyncio
import httpx

DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
API_KEY = "Db3S72tVSn2YeSw"

async def probe():
    headers = {"Authorization": f"Bearer {API_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try root
        for path in ["/", "/health", "/docs", "/api", "/convert", "/parse", "/v1/convert", "/v1/parse"]:
            url = f"{DOCLING_URL}{path}"
            try:
                resp = await client.get(url, headers=headers)
                print(f"GET {path} -> {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"GET {path} -> ERROR: {e}")

        # Try POST with file
        for path in ["/", "/convert", "/parse", "/v1/convert", "/v1/parse", "/file_parse"]:
            url = f"{DOCLING_URL}{path}"
            try:
                resp = await client.post(url, headers=headers, files={"file": ("test.pdf", b"dummy", "application/pdf")})
                print(f"POST {path} (file) -> {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"POST {path} (file) -> ERROR: {e}")

            try:
                resp = await client.post(url, headers=headers, files={"files": ("test.pdf", b"dummy", "application/pdf")})
                print(f"POST {path} (files) -> {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"POST {path} (files) -> ERROR: {e}")

asyncio.run(probe())
