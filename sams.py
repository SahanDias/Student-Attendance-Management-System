#!/usr/bin/env python3
# OWNER: M1 (Lead / Integration)
# Entry point required by the brief:
#     $ python sams.py 10.07.2019.png info.xml
# Add --gui to launch the PyQt5 window (M8) instead of the CLI run.

import argparse
import os
import sys

import yaml

from core.pipeline import AttendancePipeline
from db.dao import AttendanceDAO
from utils.logger import StageLogger


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def print_table(records):
    print("\n" + "=" * 62)
    print(f"{'#':<4}{'INDEX':<9}{'NAME':<22}{'INK%':>7}{'STATUS':>10}{'CONF':>8}")
    print("-" * 62)
    for i, r in enumerate(records, 1):
        print(f"{i:<4}{r.index_no:<9}{r.name[:20]:<22}"
              f"{r.ink_ratio * 100:>6.2f}%{r.status:>10}{r.confidence:>8.2f}")
    print("=" * 62)
    present = sum(1 for r in records if r.status == "PRESENT")
    review = sum(1 for r in records if r.status == "REVIEW")
    print(f"Present: {present}   Absent: {len(records) - present - review}"
          f"   Needs review: {review}   Total: {len(records)}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SAMS - process a signing sheet into attendance records")
    ap.add_argument("image", nargs="?", help="signing sheet photo")
    ap.add_argument("xml", nargs="?", help="info.xml with student records")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--no-save", action="store_true", help="skip DB write")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--gui", action="store_true", help="launch the PyQt5 UI")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.gui:
        from ui.main_window import launch
        return launch(cfg, args.image, args.xml)

    if not args.image or not args.xml:
        ap.error("image and xml are required (or use --gui)")

    logger = StageLogger(verbose=not args.quiet)
    try:
        result = AttendancePipeline(cfg, logger).run(args.image, args.xml)
    except Exception as exc:                       # noqa: BLE001 - CLI boundary
        logger.error(str(exc))
        return 1

    print_table(result.records)

    if not args.no_save:
        with AttendanceDAO(cfg.get("db_path", "attendance.db")) as dao:
            session_id = dao.save_sheet(result)
        print(f"saved to {cfg.get('db_path', 'attendance.db')} (session {session_id})")
    print(f"stage images: {os.path.join(cfg.get('output_dir', 'output'), os.path.splitext(result.sheet_file)[0])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
