# run_multi_subscribers.py
import sys, subprocess, time, argparse

def main():
    ap = argparse.ArgumentParser(description="Run multiple subscriber clients")
    ap.add_argument("-n", "--num", type=int, default=2,
                    help="number of subscriber instances to start (default: 2)")
    args = ap.parse_args()

    py = sys.executable
    procs = [subprocess.Popen([py, "group_1_subscriber.py"]) for _ in range(args.num)]
    print(f"Started {args.num} subscribers. Press Ctrl+C to stop.")

    try:
        while any(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        for p in procs:
            if p.poll() is None:
                p.terminate()

if __name__ == "__main__":
    main()

