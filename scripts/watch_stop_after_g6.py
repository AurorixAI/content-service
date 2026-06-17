"""Kill post-processing when G6 enrichment finishes (before G7 starts)."""
import os
import signal
import time

LOG = "/tmp/postproc.log"
MARKER = "Post-processing G7"


def find_postproc_pid() -> int | None:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode()
            if "run_post_processing_all" in cmd and "watch_stop" not in cmd:
                return int(pid)
        except OSError:
            pass
    return None


def main() -> None:
    seen = 0
    if os.path.exists(LOG):
        with open(LOG) as f:
            seen = sum(1 for _ in f)

    print(f"Watching {LOG} — stop before G7 (marker: {MARKER!r})")
    while True:
        if not os.path.exists(LOG):
            time.sleep(10)
            continue
        with open(LOG) as f:
            lines = f.readlines()
        for line in lines[seen:]:
            if MARKER in line:
                pid = find_postproc_pid()
                if pid:
                    print(f"G6 done — killing post-processing PID {pid}")
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(2)
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                print("Stopped. G7 will NOT start.")
                return
        seen = len(lines)
        time.sleep(15)


if __name__ == "__main__":
    main()
