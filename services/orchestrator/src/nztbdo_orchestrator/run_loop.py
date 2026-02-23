from __future__ import annotations

from nztbdo_orchestrator.run_profile import run


def main() -> None:
    summary = run(profile="default", ticks=200, tick_sleep=0.05)
    print("run_loop summary")
    print(
        f"ticks={summary['ticks']} elapsed_sec={summary['elapsed_sec']} "
        f"tps={summary['tps']}"
    )
    print(f"states={summary['states']}")
    print(f"actions={summary['actions']}")
    print(f"summary_path={summary['summary_path']}")


if __name__ == "__main__":
    main()
