#!/bin/sh
# Этап 3: граф настоящих пакетов NuGet (нужен интернет).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for config in config.yaml tests/configs/logging.yaml \
              tests/configs/logging_filter.yaml; do
    echo
    echo "===== $config ====="
    "$ROOT/run.sh" --config "$config"
    echo "(код выхода: $?)"
done
