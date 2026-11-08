#!/bin/sh
# Запуск инструмента из любой папки.
# При первом запуске создаётся окружение .venv и ставится PyYAML.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || exit 1
    .venv/bin/pip install -q -r requirements.txt || exit 1
fi
PYTHONPATH=src exec .venv/bin/python -m depviz "$@"
