import argparse

import uvicorn

from wordome.api import app
from wordome.demo import run_demo


def main():
    parser = argparse.ArgumentParser(description="Wordome")
    parser.add_argument("--mode", "-m", choices=["demo", "api"], default="api")
    args = parser.parse_args()
    if args.mode == "demo":
        run_demo()
    else:
        uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
