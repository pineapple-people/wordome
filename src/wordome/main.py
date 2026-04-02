import argparse

import uvicorn

from wordome.api import app
from wordome.demo import run_demo


def main():
    parser = argparse.ArgumentParser(description="Wordome")
    parser.add_argument("--mode", "-m", choices=["demo", "api"], default="demo")
    args = parser.parse_args()
    if args.mode == "api":
        uvicorn.run(app, host="127.0.0.1", port=8000)
    else:
        run_demo()

if __name__ == "__main__":
    main()
