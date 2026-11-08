#!/bin/sh
# Этап 1: запуск с правильными настройками и со всеми видами ошибок.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
for name in url_mode test_mode all_wrong missing_and_unknown \
            url_mode_bad test_mode_bad syntax_error not_mapping \
            no_such_file; do
    echo
    echo "===== $name.yaml ====="
    "$ROOT/run.sh" --config "tests/configs/$name.yaml"
    echo "(код выхода: $?)"
done
