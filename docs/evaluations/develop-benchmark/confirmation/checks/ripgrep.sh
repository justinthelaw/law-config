set -eu
if [ "$PANEL_STAGE" = build ]; then
  cargo build --locked --offline --release -p globset
  cat >target/panel-basename.rs <<'RUST'
use globset::{Candidate,GlobBuilder,GlobSet,GlobSetBuilder};
use std::hint::black_box;

#[no_mangle]
#[inline(never)]
pub fn probe_matches(set:&GlobSet, candidate:&Candidate<'_>) -> usize {
    let mut matches=0;
    for _ in 0..128 { matches+=usize::from(black_box(set).is_match_candidate(black_box(candidate))); }
    matches
}
fn main(){
    let mut builder=GlobSetBuilder::new();
    builder.add(GlobBuilder::new("**/*.py[cod]").literal_separator(true).build().unwrap());
    let set=builder.build().unwrap();
    assert!(set.is_match("pkg/script.pyc"));
    assert!(!set.is_match("pkg/script.pyz"));
    let parts=match std::env::args().nth(1).as_deref(){Some("long")=>760,_=>1};
    let path="dir/".repeat(parts)+"script.pyc";
    assert_eq!(probe_matches(&set,&Candidate::new(&path)),128);
}
RUST
  set -- target/release/deps/libglobset-*.rlib
  [ "$#" = 1 ]
  rustc --edition=2021 -C opt-level=3 -C debuginfo=1 -L dependency=target/release/deps --extern "globset=$1" target/panel-basename.rs -o target/panel-basename
elif [ "$PANEL_STAGE" = preserve ]; then
  target/panel-basename short
else
  for kind in short long; do
    valgrind --error-exitcode=3 --tool=callgrind --toggle-collect=probe_matches --collect-atstart=no --callgrind-out-file="/tmp/callgrind-$kind" target/panel-basename "$kind" >/tmp/profile-report 2>&1 || { cat /tmp/profile-report; exit 3; }
    count=$(awk '/^totals:/{print $2}' "/tmp/callgrind-$kind")
    [ -n "$count" ] && [ "$count" -gt 0 ] || { cat /tmp/profile-report; exit 4; }
    printf '%s %s\n' "$kind" "$count"
    if [ "$kind" = short ]; then short=$count; else long=$count; fi
  done
  [ "$long" -le "$((short*2))" ] || exit 42
fi
