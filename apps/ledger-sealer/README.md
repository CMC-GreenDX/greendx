# ledger-sealer

A small Go service in front of the Trillian log server ([ADR-0001](../../docs/adr/0001-core-technology-choices.md)). Trillian speaks only gRPC; this service uses the official Trillian client library and offers three HTTP calls to Carbon Ledger:

| Method and path | Purpose |
|---|---|
| `POST /trees` | Create and initialise a log; Carbon Ledger keeps one per tenant |
| `POST /trees/{id}/leaves` | Append a leaf (`{"data": base64}`), wait for its inclusion in a signed root, and return the leaf index, leaf hash, tree size and root hash |
| `GET /trees/{id}/leaves/{index}` | Read a leaf back and verify its inclusion proof against the latest signed root |

Trillian v1.8.0 (log server and log signer) stores its Merkle tree in its own PostgreSQL database `trillian`, created by `deploy/compose/postgres/migrate.sh` from the upstream schema.
