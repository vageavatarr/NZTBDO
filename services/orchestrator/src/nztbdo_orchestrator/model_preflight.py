from __future__ import annotations

import argparse
import json

from nztbdo_orchestrator.runtime_loop import RuntimeLoop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check runtime perception model readiness for a profile.")
    parser.add_argument("--profile", default="live_farm")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loop = RuntimeLoop(profile_name=args.profile)
    payload = {
        "profile": args.profile,
        "requested_backend": loop.perception.requested_backend,
        "active_backend": loop.perception.backend,
        "model_path": loop.perception.model_path,
        "model_exists": loop.perception.model_exists,
        "ultralytics_available": loop.perception.ultralytics_available,
        "init_reason": loop.perception.init_reason,
    }
    loop.stop()
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
