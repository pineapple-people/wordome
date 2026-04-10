import argparse

import uvicorn

from wordome.api import app
from wordome.demo3 import run_demo3


def main():
    parser = argparse.ArgumentParser(description="Wordome")
    parser.add_argument("--mode", "-m", choices=["demo", "api"], default="api")
    args = parser.parse_args()
    if args.mode == "demo":
        run_demo3()
    else:
        uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
