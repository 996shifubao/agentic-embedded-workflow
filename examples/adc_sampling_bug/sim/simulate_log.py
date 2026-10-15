#!/usr/bin/env python3
"""SIMULATION FIXTURE - not real hardware output.

Emits the serial log that the fixture firmware would produce, as a function of
the SAMPLE_OFFSET_US / SETTLING_US constants. Lets the orchestrator close its
software loop offline while the hardware layer stays manual.
"""

import argparse
import re
import sys


def define(text, name):
    m = re.search(r"#define\s+%s\s+(\S+)" % re.escape(name), text)
    if not m:
        raise SystemExit("error: define %s not found" % name)
    return float(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    a = ap.parse_args()
    text = open(a.src, "r", encoding="utf-8").read()

    fsw = int(define(text, "PWM_FREQ_HZ"))
    offset = define(text, "SAMPLE_OFFSET_US")
    settling = define(text, "SETTLING_US")
    settled = offset >= settling

    out = [
        "[000.001] BOOT h743-motor fw=0.9.4 (simulated)",
        "[000.003] PWM init tim1 fsw=%dHz deadtime=350ns mode=center-aligned" % fsw,
        "[000.010] calib zero_offset_calibrated=true zero_offset=2047.5",
        "[000.020] duty=0.50 sample_offset_us=%.1f adc_raw=%d adc_settled=%s"
        % (offset, 2049 if settled else 2088, str(settled).lower()),
    ]
    if settled:
        out += [
            "[000.030] stat adc_rms=3 samples=64",
            "[000.031] update_rate_hz=1000 latency_us=210 jitter_us=35",
            "[000.032] OK run_complete=true",
        ]
    else:
        out += [
            "[000.021] WARN sample window inside switching ringing",
            "[000.022] ERR_ADC_TRIG spurious trigger detected",
            "[000.023] duty=0.50 sample_offset_us=%.1f adc_raw=2091 adc_settled=false" % offset,
            "[000.024] ERR_ADC_TRIG spurious trigger detected",
            "[000.030] stat adc_rms=23 samples=64",
            "[000.031] stat speed_rpm=0 current_ma=0",
        ]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
