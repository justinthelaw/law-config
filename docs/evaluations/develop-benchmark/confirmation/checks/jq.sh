set -eu
case "$PANEL_STAGE" in
preserve) row=$(./jq -nr '"2024-06-15" | strptime("%Y-%m-%d") | .[2]'); expected=15 ;;
contract) row=$(./jq -nr '"2024-06" | strptime("%Y-%m") | .[2]'); expected=1 ;;
esac
printf '%s\n' "$row"
[ "$row" = "$expected" ] || exit 42
