import asyncio
import base64
import httpx

DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
DOCLING_API_KEY = "Db3S72tVSn2YeSw"

async def probe():
    async with httpx.AsyncClient(timeout=15.0) as client:
        b64_key = base64.b64encode(f"{DOCLING_API_KEY}:".encode()).decode()
        headers_variants = [
            ("Basic (key:)", {"Authorization": f"Basic {b64_key}"}),
            ("Basic (key:empty)", {"Authorization": f"Basic {base64.b64encode(f'{DOCLING_API_KEY}:'.encode()).decode()}"}),
            ("Bearer", {"Authorization": f"Bearer {DOCLING_API_KEY}"}),
            ("Authorization raw", {"Authorization": DOCLING_API_KEY}),
            ("Token", {"Authorization": f"Token {DOCLING_API_KEY}"}),
            ("SEDTAIGC-Key", {"SEDTAIGC-Key": DOCLING_API_KEY}),
            ("X-SEDTAIGC-Key", {"X-SEDTAIGC-Key": DOCLING_API_KEY}),
            ("X-Gateway-Key", {"X-Gateway-Key": DOCLING_API_KEY}),
            ("X-Proxy-Key", {"X-Proxy-Key": DOCLING_API_KEY}),
        ]

        print("=== Extended auth format probe ===")
        for name, hdr in headers_variants:
            try:
                r = await client.get(f"{DOCLING_URL}/health", headers=hdr)
                www = r.headers.get("www-authenticate", "")
                if r.status_code != 401:
                    print(f"  *** {name:30s} | {r.status_code} | {r.text[:200]}")
                else:
                    print(f"      {name:30s} | 401 | www-auth={www}")
            except Exception as e:
                print(f"      {name:30s} | ERROR: {e}")

        print("\n=== Path probe (without auth to discover routes) ===")
        paths_to_test = [
            "/",
            "/health",
            "/v1",
            "/v1/",
            "/docs",
            "/openapi.json",
            "/swagger.json",
            "/api-docs",
            "/v1/convert",
            "/v1/convert/file",
            "/v1/convert/file/async",
            "/v1/status",
            "/v1/result",
        ]
        for path in paths_to_test:
            try:
                r = await client.get(f"{DOCLING_URL}{path}")
                www = r.headers.get("www-authenticate", "")
                xkong = r.headers.get("x-kong-response-latency", "")
                marker = "***" if r.status_code not in (401, 404) else "   "
                print(f"  {marker} GET {path:35s} | {r.status_code} | kong-lat={xkong} | www-auth={www[:30]} | {r.text[:100]}")
            except Exception as e:
                print(f"      GET {path:35s} | ERROR: {e}")

asyncio.run(probe())
