#!/bin/sh
# Этап 3: построение графа на разных тестовых репозиториях.
# Работает без интернета.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for name in chain_depth2 chain_full diamond cycle self_loop filter \
            depth_trap from_c unknown_package bad_name undeclared; do
    config="tests/configs/stage3/$name.yaml"
    echo
    echo "===== $name: $(head -1 "$ROOT/$config" | cut -c3-) ====="
    "$ROOT/run.sh" --config "$config"
    echo "(код выхода: $?)"
done
