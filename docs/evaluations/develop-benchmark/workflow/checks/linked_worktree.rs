use ignore::WalkBuilder;
use std::{
    fs,
    path::Path,
    process::{exit, Command},
};

fn git(cwd: &Path, args: &[&str]) {
    assert!(Command::new("git")
        .current_dir(cwd)
        .args(args)
        .status()
        .unwrap()
        .success());
}
fn names(path: &Path, require: bool, exclude: bool) -> Vec<String> {
    WalkBuilder::new(path)
        .require_git(require)
        .git_exclude(exclude)
        .build()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect()
}
fn main() {
    let root = Path::new("/tmp/ignore-probe");
    fs::create_dir(root).unwrap();
    git(root, &["init", "-q", "main"]);
    let main = root.join("main");
    git(
        &main,
        &[
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@invalid",
            "commit",
            "-qm",
            "seed",
            "--allow-empty",
        ],
    );
    git(&main, &["worktree", "add", "-q", "--detach", "../linked"]);
    fs::write(main.join(".git/info/exclude"), "private-file\n").unwrap();
    let linked = root.join("linked");
    for name in ["private-file", "visible-file"] {
        fs::write(linked.join(name), "").unwrap();
    }
    for (require, exclude, should_find) in [
        (true, true, false),
        (false, false, true),
        (false, true, false),
    ] {
        let result = names(&linked, require, exclude);
        if result.contains(&"private-file".into()) != should_find
            || !result.contains(&"visible-file".into())
        {
            eprintln!("require_git={require}, git_exclude={exclude}: {result:?}");
            exit(42);
        }
    }
}
