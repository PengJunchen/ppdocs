import asyncio
import httpx
import json
import sys

DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
DOCLING_API_KEY = "Db3S72tVSn2YeSw"
MINERU_URL = "http://10.0.40.153:18089"

PDF_PATH = "PDFTest/DeepSeek_V4.pdf"


async def test_docling_health():
    print("=" * 60)
    print("Testing Docling API with X-Api-Key header")
    print("=" * 60)

    headers = {"X-Api-Key": DOCLING_API_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for path in ["/health", "/readiness", "/v1/convert/health"]:
            try:
                r = await client.get(f"{DOCLING_URL}{path}", headers=headers)
                print(f"\nGET {path}")
                print(f"  Status: {r.status_code}")
                print(f"  Headers: {dict(r.headers)}")
                print(f"  Body: {r.text[:500]}")
            except Exception as e:
                print(f"\nGET {path} -> ERROR: {e}")


async def test_docling_convert():
    print("\n" + "=" * 60)
    print("Testing Docling /v1/convert/file/async with X-Api-Key")
    print("=" * 60)

    headers = {"X-Api-Key": DOCLING_API_KEY}

    try:
        with open(PDF_PATH, "rb") as f:
            pdf_data = f.read()
        print(f"PDF loaded: {len(pdf_data)} bytes")
    except Exception as e:
        print(f"Failed to load PDF: {e}")
        return

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        try:
            resp = await client.post(
                f"{DOCLING_URL}/v1/convert/file/async",
                headers=headers,
                files={"files": ("DeepSeek_V4.pdf", pdf_data, "application/pdf")},
            )
            print(f"\nPOST /v1/convert/file/async")
            print(f"  Status: {resp.status_code}")
            print(f"  Body: {resp.text[:800]}")

            if resp.status_code == 200:
                job = resp.json()
                task_id = job.get("task_id", job.get("job_id", ""))
                print(f"  Task ID: {task_id}")

                if task_id:
                    print("\nPolling for result...")
                    elapsed = 0
                    interval = 3
                    while elapsed < 240:
                        await asyncio.sleep(interval)
                        elapsed += interval
                        try:
                            status_resp = await client.get(
                                f"{DOCLING_URL}/v1/status/poll/{task_id}",
                                headers=headers,
                                params={"wait": "5"},
                            )
                            print(f"  [{elapsed}s] Status: {status_resp.status_code} | {status_resp.text[:300]}")

                            if status_resp.status_code == 200:
                                status_data = status_resp.json()
                                task_status = status_data.get("task_status", status_data.get("status", ""))
                                if task_status in ("success", "completed", "done"):
                                    result_resp = await client.get(
                                        f"{DOCLING_URL}/v1/result/{task_id}",
                                        headers=headers,
                                    )
                                    print(f"\n  RESULT Status: {result_resp.status_code}")
                                    result_text = result_resp.text[:2000]
                                    print(f"  RESULT Body: {result_text}")
                                    break
                                elif task_status in ("failed", "error"):
                                    print(f"  Job FAILED: {json.dumps(status_data)[:500]}")
                                    break
                        except Exception as e:
                            print(f"  [{elapsed}s] Poll error: {e}")

                        interval = min(interval + 2, 15)
            elif resp.status_code == 401:
                print("\n  401 - Trying additional header formats...")

                for hdr_name, hdr_val in [
                    ("Authorization", f"Bearer {DOCLING_API_KEY}"),
                    ("X-Api-Key", DOCLING_API_KEY),
                    ("apikey", DOCLING_API_KEY),
                ]:
                    try:
                        r2 = await client.post(
                            f"{DOCLING_URL}/v1/convert/file/async",
                            headers={hdr_name: hdr_val},
                            files={"files": ("test.txt", b"hello", "text/plain")},
                        )
                        print(f"  Retry with {hdr_name}: {r2.status_code} | {r2.text[:300]}")
                    except Exception as e2:
                        print(f"  Retry with {hdr_name}: ERROR {e2}")
        except Exception as e:
            print(f"\nPOST error: {e}")


async def test_mineru():
    print("\n" + "=" * 60)
    print("Testing MinerU API")
    print("=" * 60)

    try:
        with open(PDF_PATH, "rb") as f:
            pdf_data = f.read()
    except Exception as e:
        print(f"Failed to load PDF: {e}")
        return

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        try:
            resp = await client.post(
                f"{MINERU_URL}/file_parse",
                files={"files": ("DeepSeek_V4.pdf", pdf_data, "application/pdf")},
                params={"is_ocr": "true"},
            )
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                keys = list(data.get("results", {}).keys())
                print(f"Result keys: {keys[:3]}")
            else:
                print(f"Body: {resp.text[:500]}")
        except Exception as e:
            print(f"Error: {e}")


async def main():
    await test_docling_health()
    await test_docling_convert()
    await test_mineru()
    print("\n" + "=" * 60)
    print("API probe complete")
    print("=" * 60)


asyncio.run(main())
