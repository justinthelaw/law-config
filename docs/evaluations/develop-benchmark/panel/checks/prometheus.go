package main

import (
    "context"
    "fmt"
    "net/http"
    "net/http/httptest"
    "os"
    "time"

    "github.com/prometheus/client_golang/api"
    v1 "github.com/prometheus/client_golang/api/prometheus/v1"
)

func main() {
    path := make(chan string, 1)
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        path <- r.URL.Path
        w.Header().Set("Content-Type", "application/json")
        fmt.Fprint(w, `{"status":"success","data":["ok"]}`)
    }))
    defer srv.Close()
    client, err := api.NewClient(api.Config{Address:srv.URL}); if err != nil { panic(err) }
    labels := map[string]string{"service.name":"service.name","name":"name"}
    if os.Getenv("PANEL_STAGE") == "contract" {
        labels = map[string]string{"team.io/name":"U__team_2e_io_2f_name",".":"U___2e_","..":"U___2e__2e_"}
    }
    for label, want := range labels {
        got, _, _, err := v1.NewAPI(client).LabelValues(context.Background(), label, nil, time.Time{}, time.Time{})
        if err != nil { fmt.Println(err); os.Exit(42) }
        actual := <-path
        if actual != "/api/v1/label/"+want+"/values" || len(got)!=1 || got[0]!="ok" {
            fmt.Println(label, actual, want, got); os.Exit(42)
        }
    }
}
