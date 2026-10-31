package main

import (
 "bufio"
 "bytes"
 "errors"
 "fmt"
 "io"
 "strings"
 "testing/iotest"

 "github.com/go-git/go-git/v6/plumbing"
 "github.com/go-git/go-git/v6/plumbing/object"
)

type injected struct { plumbing.EncodedObject; reader io.Reader }
func (o injected) Reader() (io.ReadCloser, error) { return io.NopCloser(o.reader), nil }
func main() {
 sentinel := errors.New("mode read failed")
 chunk, readErr := bufio.NewReader(io.MultiReader(strings.NewReader("8"), iotest.ErrReader(sentinel))).ReadSlice(' ')
 fmt.Printf("readslice bytes=%q sentinel=%t error=%v\n", chunk, errors.Is(readErr,sentinel), readErr)
 for _, tc := range []struct {name, input string; fail bool}{
  {"sentinel-empty", "", true}, {"sentinel-valid", "100", true},
  {"sentinel-zeros-1000", strings.Repeat("0", 1000), true},
  {"sentinel-zeros-9000", strings.Repeat("0", 9000), true},
  {"sentinel-invalid", "8", true}, {"terminated-invalid", "8 a\x00" + string(make([]byte,20)), false},
  {"normal-valid", "100644 a\x00" + string(make([]byte,20)), false},
 } {
  m := &plumbing.MemoryObject{}; m.SetType(plumbing.TreeObject); _, _ = m.Write([]byte("100644 a\x00"))
  var r io.Reader = bytes.NewBufferString(tc.input)
  if tc.fail { r = io.MultiReader(r, iotest.ErrReader(sentinel)) }
  var t object.Tree; err := t.Decode(injected{m,r})
  fmt.Printf("%s sentinel=%t malformed=%t error=%v entries=%d\n",tc.name,errors.Is(err,sentinel),errors.Is(err,object.ErrMalformedTree),err,len(t.Entries))
 }
}
