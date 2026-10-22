// ledger-sealer is a small HTTP front for a Trillian verifiable log, used by Carbon Ledger to seal closed periods.
//
//	POST /trees                      create and initialise a log, returns its id (one log per tenant)
//	POST /trees/{id}/leaves          append a leaf, wait until it is included in a signed root, return index and root
//	GET  /trees/{id}/leaves/{index}  read a leaf back and verify its inclusion proof against the latest signed root
//
// Only the official Trillian client library talks to the log; this service adds no cryptography of its own.
package main

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/google/trillian"
	"github.com/google/trillian/client"
	"github.com/google/trillian/types"
	"github.com/transparency-dev/merkle/rfc6962"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/durationpb"
)

type server struct {
	admin trillian.TrillianAdminClient
	log   trillian.TrillianLogClient
}

func main() {
	addr := getenv("TRILLIAN_ADDR", "trillian-log-server:8090")
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		slog.Error("cannot create gRPC client", "error", err)
		os.Exit(1)
	}
	s := &server{admin: trillian.NewTrillianAdminClient(conn), log: trillian.NewTrillianLogClient(conn)}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("POST /trees", s.createTree)
	mux.HandleFunc("POST /trees/{id}/leaves", s.appendLeaf)
	mux.HandleFunc("GET /trees/{id}/leaves/{index}", s.readLeaf)

	slog.Info("ledger-sealer listening", "addr", ":8080", "trillian", addr)
	if err := http.ListenAndServe(":8080", mux); err != nil {
		slog.Error("server stopped", "error", err)
		os.Exit(1)
	}
}

func (s *server) createTree(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	tree, err := client.CreateAndInitTree(ctx, &trillian.CreateTreeRequest{Tree: &trillian.Tree{
		TreeState:       trillian.TreeState_ACTIVE,
		TreeType:        trillian.TreeType_LOG,
		DisplayName:     "ecotrace-ledger",
		MaxRootDuration: durationpb.New(time.Hour),
	}}, s.admin, s.log)
	if err != nil {
		fail(w, 502, "create tree", err)
		return
	}
	writeJSON(w, 201, map[string]string{"tree_id": strconv.FormatInt(tree.TreeId, 10)})
}

func (s *server) logClient(ctx context.Context, idText string) (*client.LogClient, int64, error) {
	id, err := strconv.ParseInt(idText, 10, 64)
	if err != nil {
		return nil, 0, errors.New("invalid tree id")
	}
	tree, err := s.admin.GetTree(ctx, &trillian.GetTreeRequest{TreeId: id})
	if err != nil {
		return nil, 0, err
	}
	c, err := client.NewFromTree(s.log, tree, types.LogRootV1{})
	if err != nil {
		return nil, 0, err
	}
	if _, err := c.UpdateRoot(ctx); err != nil {
		return nil, 0, err
	}
	return c, id, nil
}

func (s *server) appendLeaf(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()
	var body struct {
		Data string `json:"data"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		fail(w, 400, "decode body", err)
		return
	}
	data, err := base64.StdEncoding.DecodeString(body.Data)
	if err != nil || len(data) == 0 {
		fail(w, 400, "data must be non-empty base64", err)
		return
	}
	c, id, err := s.logClient(ctx, r.PathValue("id"))
	if err != nil {
		fail(w, 502, "open log", err)
		return
	}
	// AddLeaf queues the leaf and returns once it is included in a signed log root and the proof verifies.
	if err := c.AddLeaf(ctx, data); err != nil {
		fail(w, 502, "append leaf", err)
		return
	}
	root := c.GetRoot()
	leafHash := rfc6962.DefaultHasher.HashLeaf(data)
	proof, err := s.log.GetInclusionProofByHash(ctx, &trillian.GetInclusionProofByHashRequest{
		LogId: id, LeafHash: leafHash, TreeSize: int64(root.TreeSize), OrderBySequence: true,
	})
	if err != nil || len(proof.Proof) == 0 {
		fail(w, 502, "inclusion proof", err)
		return
	}
	writeJSON(w, 201, map[string]any{
		"tree_id":    strconv.FormatInt(id, 10),
		"leaf_index": proof.Proof[0].LeafIndex,
		"leaf_hash":  hex.EncodeToString(leafHash),
		"tree_size":  root.TreeSize,
		"root_hash":  hex.EncodeToString(root.RootHash),
		"timestamp":  time.Unix(0, int64(root.TimestampNanos)).UTC().Format(time.RFC3339Nano),
	})
}

func (s *server) readLeaf(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	index, err := strconv.ParseInt(r.PathValue("index"), 10, 64)
	if err != nil {
		fail(w, 400, "invalid leaf index", err)
		return
	}
	c, id, err := s.logClient(ctx, r.PathValue("id"))
	if err != nil {
		fail(w, 502, "open log", err)
		return
	}
	leaves, err := s.log.GetLeavesByRange(ctx, &trillian.GetLeavesByRangeRequest{LogId: id, StartIndex: index, Count: 1})
	if err != nil || len(leaves.Leaves) == 0 {
		fail(w, 404, "leaf not found", err)
		return
	}
	data := leaves.Leaves[0].LeafValue
	// Proves the leaf is part of the log the signer committed to: it cannot have been rewritten.
	included := c.VerifyInclusion(ctx, data) == nil
	root := c.GetRoot()
	writeJSON(w, 200, map[string]any{
		"tree_id":   strconv.FormatInt(id, 10),
		"data":      base64.StdEncoding.EncodeToString(data),
		"leaf_hash": hex.EncodeToString(rfc6962.DefaultHasher.HashLeaf(data)),
		"included":  included,
		"tree_size": root.TreeSize,
		"root_hash": hex.EncodeToString(root.RootHash),
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func fail(w http.ResponseWriter, status int, what string, err error) {
	msg := what
	if err != nil {
		msg += ": " + err.Error()
	}
	slog.Error("request failed", "status", status, "error", msg)
	writeJSON(w, status, map[string]string{"detail": msg})
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
