import asyncio
import httpx

DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
DOCLING_API_KEY = "Db3S72tVSn2YeSw"

async def probe():
    headers_variants = [
        ("apikey", {"apikey": DOCLING_API_KEY}),
        ("X-Api-Key", {"X-Api-Key": DOCLING_API_KEY}),
        ("X-API-Key", {"X-API-Key": DOCLING_API_KEY}),
        ("api_key", {"api_key": DOCLING_API_KEY}),
        ("api-key", {"api-key": DOCLING_API_KEY}),
        ("Authorization-apikey", {"Authorization": DOCLING_API_KEY}),
        ("Kong-Key", {"kong-key": DOCLING_API_KEY}),
        ("X-Consumer-Key", {"X-Consumer-Key": DOCLING_API_KEY}),
    ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        print("=== Kong key-auth probe (all header variants) ===")
        for name, hdr in headers_variants:
            for path in ["/health", "/v1/convert/file/async"]:
                try:
                    if path == "/health":
                        r = await client.get(f"{DOCLING_URL}{path}", headers=hdr)
                    else:
                        r = await client.post(
                            f"{DOCLING_URL}{path}",
                            headers=hdr,
                            files={"files": ("test.txt", b"hello", "text/plain")},
                        )
                    www_auth = r.headers.get("www-authenticate", "")
                    print(f"  {name:25s} | {path:30s} | {r.status_code} | www-auth={www_auth} | {r.text[:150]}")
                except Exception as e:
                    print(f"  {name:25s} | {path:30s} | ERROR: {e}")

        print("\n=== Query parameter variants ===")
        for param in ["apikey", "api_key", "key", "token", "api-key"]:
            try:
                r = await client.get(f"{DOCLING_URL}/health?{param}={DOCLING_API_KEY}")
                www_auth = r.headers.get("www-authenticate", "")
                print(f"  ?{param:10s} | {r.status_code} | www-auth={www_auth} | {r.text[:150]}")
            except Exception as e:
                print(f"  ?{param:10s} | ERROR: {e}")

asyncio.run(probe())
