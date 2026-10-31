set -eu
mkdir -p crates/ignore/examples
cat > crates/ignore/examples/panel_preserve.rs <<'RS'
use ignore::WalkBuilder;
use std::{fs, path::Path};
fn main() {
    let p = Path::new("/tmp/ordinary-ignore");
    fs::create_dir_all(p).unwrap();
    fs::write(p.join(".ignore"), "private\n").unwrap();
    for file in ["visible", "private"] { fs::write(p.join(file), "").unwrap(); }
    let files: Vec<_> = WalkBuilder::new(p).require_git(false).build()
        .map(|e| e.unwrap().file_name().to_owned()).collect();
    if !files.iter().any(|x| x == "visible") || files.iter().any(|x| x == "private") {
        std::process::exit(42);
    }
}
RS
cargo build --offline --locked -q -p ignore --example panel_preserve
./target/debug/examples/panel_preserve
