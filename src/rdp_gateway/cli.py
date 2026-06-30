from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config
from .server import RdpGatewayServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experimental local RDP gateway shim")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to TOML config file. Defaults to ./config.toml.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        logging.basicConfig(
            level=getattr(logging, config.logging.level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        asyncio.run(RdpGatewayServer(config).serve_forever())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logging.error("failed to start gateway: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
