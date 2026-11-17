#!/bin/sh
# kullanim: research/queue.sh jobs.txt  (her satir: run_bt_engine.py argumanlari); 4 paralel
cd "$(dirname "$0")/.."
export PYTHONPATH=src
cat "$1" | xargs -P "${P:-4}" -L 1 sh -c '.venv/bin/python research/run_bt_engine.py "$@" >> research/logs/queue.log 2>&1' _
