#!/bin/sh
# Этап 2: прямые зависимости пакетов из настоящего репозитория NuGet.
# Нужен доступ в интернет.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for config in config.yaml tests/configs/logging.yaml \
              tests/configs/url_mode.yaml \
              tests/configs/no_such_package.yaml \
              tests/configs/bad_host.yaml tests/configs/not_nuget.yaml \
              tests/configs/test_mode.yaml; do
    echo
    echo "===== $config ====="
    "$ROOT/run.sh" --config "$config"
    echo "(код выхода: $?)"
done
