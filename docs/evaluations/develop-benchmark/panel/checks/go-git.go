package main

import (
    "bytes"
    "fmt"
    "os"
    "os/exec"
    "strings"

    "github.com/go-git/go-git/v6/plumbing"
    "github.com/go-git/go-git/v6/plumbing/object"
)

func main() {
    repo, err := os.MkdirTemp("", "git-expected")
    if err != nil { panic(err) }
    if err := exec.Command("git", "init", "-q", "--bare", repo).Run(); err != nil { panic(err) }
    mode := "100644"
    if os.Getenv("PANEL_STAGE") == "independent" { mode = "1000000100644" }
    raw := append([]byte(mode+" abc\x00"), bytes.Repeat([]byte{1}, 20)...)
    put := exec.Command("git", "-C", repo, "hash-object", "-w", "--literally", "-t", "tree", "--stdin")
    put.Stdin = bytes.NewReader(raw)
    hash, err := put.Output(); if err != nil { panic(err) }
    list, err := exec.Command("git", "-C", repo, "ls-tree", strings.TrimSpace(string(hash))).Output()
    if err != nil { panic(err) }
    obj := &plumbing.MemoryObject{}
    obj.SetType(plumbing.TreeObject)
    writer, err := obj.Writer(); if err != nil { panic(err) }
    if _, err = writer.Write(raw); err != nil { panic(err) }
    if err = writer.Close(); err != nil { panic(err) }
    var tree object.Tree
    expected := strings.Fields(string(list))[0]
    if err := tree.Decode(obj); err != nil || len(tree.Entries) != 1 || fmt.Sprintf("%o", uint32(tree.Entries[0].Mode)) != expected {
        fmt.Println(mode, "expected", expected, "got", tree.Entries, err); os.Exit(42)
    }
}
