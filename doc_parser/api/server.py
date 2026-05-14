import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Doc Parser API Server")
    parser.add_argument("--host", default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--log-level", default=None, help="Log level")
    parser.add_argument("--config", default=None, help="Path to config.json")
    args = parser.parse_args()

    from doc_parser.config import load_config
    cfg = load_config(args.config)

    server_cfg = cfg.get("server", {})
    host = args.host or server_cfg.get("host", "0.0.0.0")
    port = args.port or server_cfg.get("port", 8000)
    log_level = args.log_level or cfg.get("logging", {}).get("level", "info").lower()

    if args.config:
        os.environ.setdefault("DOCPARSER_CONFIG_PATH", args.config)

    os.environ.setdefault("DOCPARSER_MINERU_URL", cfg.get("pipeline", {}).get("mineru_url", "http://10.0.40.153:18089"))

    uvicorn.run(
        "doc_parser.api.app:create_app",
        host=host,
        port=port,
        factory=True,
        reload=args.reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
