// Exercise the exported decoder against Git's interpretation of literal tree objects.
package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"

	"github.com/go-git/go-git/v6/plumbing"
	"github.com/go-git/go-git/v6/plumbing/filemode"
	"github.com/go-git/go-git/v6/plumbing/object"
)

func main() {
	for _, text := range []string{"00000000000100644", "37777777777", "40000000000", "10068", ""} {
		expected, parseErr := strconv.ParseUint(text, 8, 32)
		actual, err := filemode.FromBytes([]byte(text))
		if (err != nil) != (parseErr != nil) || (err == nil && uint64(actual) != expected) ||
			(err != nil && actual != filemode.Empty) {
			fmt.Println("public byte parser:", text, actual, err)
			os.Exit(42)
		}
	}
	for raw, want := range map[filemode.FileMode]filemode.FileMode{
		0o100011: filemode.Regular, 0o100100: filemode.Executable,
		0o040011: filemode.Dir, 0o120011: filemode.Symlink, 0: filemode.Submodule,
	} {
		value, ok := any(raw).(interface{ Canonical() filemode.FileMode })
		if !ok || value.Canonical() != want {
			fmt.Printf("canonical mode: %o, expected %o\n", raw, want)
			os.Exit(42)
		}
	}
	dir, err := os.MkdirTemp("", "git-oracle")
	if err != nil {
		panic(err)
	}
	if err := exec.Command("git", "init", "-q", "--bare", dir).Run(); err != nil {
		panic(err)
	}
	for _, mode := range []string{"100644", "100011", "100755", "40000", "120000", "160000",
		"00000000000100644", strings.Repeat("0", 5000) + "100755", "10068"} {
		raw := append([]byte(mode+" x\x00"), bytes.Repeat([]byte{1}, 20)...)
		obj := &plumbing.MemoryObject{}
		obj.SetType(plumbing.TreeObject)
		writer, err := obj.Writer()
		if err != nil {
			panic(err)
		}
		if _, err = writer.Write(raw); err != nil {
			panic(err)
		}
		if err = writer.Close(); err != nil {
			panic(err)
		}
		var tree object.Tree
		err = tree.Decode(obj)
		if mode == "10068" {
			if !errors.Is(err, object.ErrMalformedTree) {
				fmt.Println("invalid octal:", err)
				os.Exit(42)
			}
			continue
		}
		hash := exec.Command("git", "-C", dir, "hash-object", "-w", "--literally", "-t", "tree", "--stdin")
		hash.Stdin = bytes.NewReader(raw)
		id, oracleErr := hash.Output()
		if oracleErr != nil {
			panic(oracleErr)
		}
		listing, oracleErr := exec.Command("git", "-C", dir, "ls-tree", strings.TrimSpace(string(id))).Output()
		if oracleErr != nil {
			panic(oracleErr)
		}
		want, oracleErr := strconv.ParseUint(strings.Fields(string(listing))[0], 8, 32)
		if oracleErr != nil {
			panic(oracleErr)
		}
		if err != nil || len(tree.Entries) != 1 || uint64(tree.Entries[0].Mode) != want || tree.Entries[0].Name != "x" {
			fmt.Printf("mode length %d, Git %o, entries %v, error %v\n", len(mode), want, tree.Entries, err)
			os.Exit(42)
		}
	}
}
