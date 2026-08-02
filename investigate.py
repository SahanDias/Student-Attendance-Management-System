#!/usr/bin/env python3
# OWNER: M10 (Signature Verification)
# Entry point required by the brief:
#     $ python investigate.py 001
# Compares the signature captured on the sheet with the student's enrolled
# specimens in data/signatures/<index>/ and reports a match or a mismatch.

import argparse
import os
import sys

import cv2
import yaml

from core.signature import SignatureVerifier
from db.dao import AttendanceDAO


def load_config(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SAMS - signature verification")
    ap.add_argument("index", help="student index, e.g. 001")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--refs", default="data/signatures")
    ap.add_argument("--figure", action="store_true",
                    help="write a side-by-side comparison image for the report")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    verifier = SignatureVerifier(cfg.get("signature", {}))

    with AttendanceDAO(cfg.get("db_path", "attendance.db")) as dao:
        history = dao.student_history(args.index)
        name = dao.student(args.index).get("name", "")

    crops = [h for h in history if h.get("status") == "PRESENT"]
    if not crops:
        print(f"no PRESENT records with a saved crop for {args.index}")
        return 1

    print(f"\nSignature investigation - {args.index} {name}")
    print(f"threshold = {verifier.match_threshold}\n")

    flagged = 0
    for h in history:
        crop_path = h.get("crop_path") or ""
        if not crop_path or not os.path.exists(crop_path):
            continue
        report = verifier.verify(crop_path, args.index, args.refs)
        if report["status"] in ("NO_REFERENCE", "NO_CANDIDATE"):
            print(f"  {h['session_date']:<12} {report['status']}")
            continue
        best = report["best"]
        flag = "" if report["status"] == "MATCH" else "   <-- MISMATCH"
        flagged += report["status"] != "MATCH"
        print(f"  {h['session_date']:<12} combined={best['combined']:.3f}"
              f"  (ssim={best['ssim']:.3f} hu={best['hu']:.3f} orb={best['orb']:.3f})"
              f"  {report['status']}{flag}")

        if args.figure:
            ref = os.path.join(args.refs, args.index, best["reference"])
            fig = verifier.side_by_side(cv2.imread(crop_path, 0), cv2.imread(ref, 0))
            out = os.path.join("output", "signatures")
            os.makedirs(out, exist_ok=True)
            p = os.path.join(out, f"{args.index}_{h['session_date']}.png")
            cv2.imwrite(p, fig)
            print("      figure:", p)

    print(f"\n{flagged} session(s) flagged for manual review.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
