import httpx
import asyncio

url = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
key = "Db3S72tVSn2YeSw"

async def probe():
    async with httpx.AsyncClient(timeout=15.0) as c:
        headers_list = [
            ("X-Api-Key", {"X-Api-Key": key}),
            ("Api-Key", {"Api-Key": key}),
            ("API-KEY", {"API-KEY": key}),
            ("x-api-key", {"x-api-key": key}),
            ("api_key", {"api_key": key}),
            ("Appkey", {"Appkey": key}),
            ("appKey", {"appKey": key}),
            ("X-App-Key", {"X-App-Key": key}),
            ("X-Auth-Token", {"X-Auth-Token": key}),
            ("token", {"token": key}),
            ("Authorization-Bearer", {"Authorization-Bearer": key}),
            ("Bearer+query", {}),
        ]
        for hdr_name, hdr in headers_list:
            try:
                r = await c.get(f"{url}/health", headers=hdr)
                print(f"GET /health | {hdr_name} | {r.status_code} | {r.text[:200]}")
            except Exception as e:
                print(f"GET /health | {hdr_name} | error={e}")

        print("\n--- Query param test ---")
        for param in ["api_key", "apikey", "key", "token", "app_key"]:
            try:
                r = await c.get(f"{url}/health?{param}={key}")
                print(f"GET /health?{param}=... | {r.status_code} | {r.text[:200]}")
            except Exception as e:
                print(f"GET /health?{param}=... | error={e}")

asyncio.run(probe())
