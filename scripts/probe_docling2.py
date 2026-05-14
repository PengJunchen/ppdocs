import asyncio
import httpx

DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
API_KEY = "Db3S72tVSn2YeSw"

async def probe_auth():
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Try different auth methods for /health
        auth_methods = [
            ("Bearer", {"Authorization": f"Bearer {API_KEY}"}),
            ("X-API-Key", {"X-API-Key": API_KEY}),
            ("api-key", {"api-key": API_KEY}),
            ("apikey", {"apikey": API_KEY}),
            ("x-api-key-lower", {"x-api-key": API_KEY}),
            ("query param", {}),
        ]

        for name, headers in auth_methods:
            try:
                if name == "query param":
                    resp = await client.get(f"{DOCLING_URL}/health?api_key={API_KEY}")
                else:
                    resp = await client.get(f"{DOCLING_URL}/health", headers=headers)
                print(f"GET /health [{name}] -> {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"GET /health [{name}] -> ERROR: {e}")

        # Now try POST with the working auth method on various endpoints
        for auth_name, auth_headers in [
            ("X-API-Key", {"X-API-Key": API_KEY}),
            ("Bearer", {"Authorization": f"Bearer {API_KEY}"}),
        ]:
            for path in ["/convert", "/parse", "/file_parse", "/health"]:
                url = f"{DOCLING_URL}{path}"
                try:
                    resp = await client.post(
                        url,
                        headers=auth_headers,
                        files={"file": ("test.pdf", b"dummy", "application/pdf")},
                    )
                    print(f"POST {path} [{auth_name}] -> {resp.status_code} {resp.text[:200]}")
                except Exception as e:
                    print(f"POST {path} [{auth_name}] -> ERROR: {e}")

asyncio.run(probe_auth())
