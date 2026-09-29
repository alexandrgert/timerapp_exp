import sys

from timerapp_ag.main import main


if __name__ == "__main__":
    raise SystemExit(main(startup_smoke_test="--startup-smoke-test" in sys.argv))
