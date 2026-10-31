#!/bin/sh
set -eu
out=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(dirname -- "$out")
for target in i686-w64-windows-gnu x86_64-w64-windows-gnu; do
    for variant in baseline subject; do
        result=0
        (cd "$root/$variant" && clang --target="$target" -M -MG -nostdinc \
            -Ilibarchive -Icontrib/android/config '-DPLATFORM_CONFIG_H="windows_host.h"' \
            -DSIZEOF_INT=__SIZEOF_INT__ libarchive/archive_read_data_into_fd.c) \
            >"$out/$variant-$target.d" 2>"$out/$variant-$target.log" || result=$?
        printf '%s %s %s\n' "$target" "$variant" "$result"
        if [ "$variant" = baseline ]; then
            test "$result" -eq 0
        else
            test "$result" -ne 0
            grep -F 'too few arguments provided to function-like macro invocation' "$out/$variant-$target.log" >/dev/null
            grep -F "'fcntl' macro defined here" "$out/$variant-$target.log" >/dev/null || grep -F "macro 'fcntl' defined here" "$out/$variant-$target.log" >/dev/null
        fi
    done
done
