#!/usr/bin/env python3
import subprocess
import sys

def main():
    # Perform the curl request exactly as specified in the task.
    cmd = [
        "curl",
        "-s",
        "http://127.0.0.1:25112/api/search?query=robot&categories=repositories&per_page=2"
    ]

    try:
        result = subprocess.check_output(cmd, text=True)
        print(result.strip())
    except subprocess.CalledProcessError as e:
        print(f"curl failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("curl executable not found.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
