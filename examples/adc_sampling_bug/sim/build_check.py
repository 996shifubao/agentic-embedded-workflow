#!/usr/bin/env python3
"""SIMULATION FIXTURE - not a real compiler.

Checks that the fixture source parses and declares the required constants.
Deliberately passes even when the sampling bug is present: that is the point
(compile green != behaviour correct).
"""

import argparse
import re
import sys

REQUIRED = ["PWM_FREQ_HZ", "SAMPLE_OFFSET_US", "SETTLING_US", "ADC_RMS_LIMIT"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    a = ap.parse_args()
    try:
        text = open(a.src, "r", encoding="utf-8").read()
    except OSError as e:
        print("error: cannot read %s: %s" % (a.src, e))
        return 1
    missing = [n for n in REQUIRED if not re.search(r"#define\s+%s\s+\S+" % n, text)]
    for name in missing:
        print("error: missing define %s" % name)
    if text.count("{") != text.count("}"):
        print("error: unbalanced braces")
    print("build_check: %s (%d bytes, %d defines)" % (a.src, len(text), len(REQUIRED) - len(missing)))
    return 1 if missing or text.count("{") != text.count("}") else 0


if __name__ == "__main__":
    sys.exit(main())
