#!/bin/bash
# interoception.sh - 内受容感覚（時刻・曜日）
# UserPromptSubmitフックで毎ターン実行される

CURRENT_TIME=$(date '+%H:%M:%S')
CURRENT_DOW=$(date '+%a')

# stdin 消費（hookの仕様上必要）
cat > /dev/null

echo "[interoception] time=${CURRENT_TIME} day=${CURRENT_DOW}"

exit 0
