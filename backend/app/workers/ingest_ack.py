"""
Stub consumer entrypoint for post-enqueue processing (Step Functions / ECS worker).

v1: log receipt only. Downstream can mark inspections, trigger frame extraction, etc.
"""

import argparse
import json
import logging

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="IIE ingest job stub")
    parser.add_argument("payload", nargs="?", help="JSON job body (for local testing)")
    args = parser.parse_args()
    if args.payload:
        log.info("ingest_ack stub received: %s", json.loads(args.payload))
    else:
        log.info("ingest_ack stub: no payload (run with JSON arg for smoke test)")


if __name__ == "__main__":
    main()
