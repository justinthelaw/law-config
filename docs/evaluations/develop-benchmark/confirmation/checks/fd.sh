set -eu
fd=/work/target/debug/fd
stage=$(mktemp -d)
cd "$stage"
printf '%s\n' ignoredprobe >.ignore
touch .hiddenprobe ignoredprobe visibleprobe
if [ "$PANEL_STAGE" = preserve ]; then
  actual=$("$fd" --color never --hidden probe | sort)
  printf '%s\n' "$actual"
  printf '%s\n' "$actual" | grep -q hiddenprobe && ! printf '%s\n' "$actual" | grep -q ignoredprobe || exit 42
else
  a=$("$fd" --color never -u --ignore probe | sort)
  b=$("$fd" --color never -u --no-hidden probe | sort)
  printf '%s\n--\n%s\n' "$a" "$b"
  printf '%s\n' "$a" | grep -q hiddenprobe && ! printf '%s\n' "$a" | grep -q ignoredprobe || exit 42
  printf '%s\n' "$b" | grep -q ignoredprobe && ! printf '%s\n' "$b" | grep -q hiddenprobe || exit 42
fi
