#!/bin/sh
# kullanim: research/queue.sh jobs.txt  (her satir: run_bt.py argumanlari); 4 paralel
cd "$(dirname "$0")/.."
export PYTHONPATH=src
cat "$1" | xargs -P "${P:-4}" -L 1 sh -c '.venv-ft/bin/python research/run_bt.py "$@" >> research/logs/queue.log 2>&1' _
