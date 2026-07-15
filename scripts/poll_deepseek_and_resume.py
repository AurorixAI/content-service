import time
import subprocess
import logging
from src.pipeline.deepseek_client import call_deepseek

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poll_deepseek")

def test_deepseek() -> bool:
    try:
        log.info("Testing Azure DeepSeek-V4-Pro endpoint...")
        res = call_deepseek("Привет! Ответь одним словом OK.")
        log.info("Response received: %s", res.strip())
        if "ok" in res.lower() or "привет" in res.lower() or len(res) > 0:
            return True
    except Exception as e:
        log.warning("Azure DeepSeek is still offline/timing out: %s", e)
    return False

def main():
    log.info("Starting automatic polling for Azure DeepSeek...")
    
    # Poll until success
    while True:
        if test_deepseek():
            log.info("Azure DeepSeek-V4-Pro is ONLINE! Resuming backfill task...")
            break
        log.info("Sleeping for 30 seconds before next check...")
        time.sleep(30)
        
    # Execute the backfill script
    cmd = ["python", "-u", "/app/scripts/backfill_latex_llm.py", "--class-level", "9", "--execute"]
    log.info("Running backfill command: %s", " ".join(cmd))
    
    # Run and stream output
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        print(line, end="")
    process.wait()
    
    log.info("Backfill process finished with code %d", process.returncode)

if __name__ == "__main__":
    main()
