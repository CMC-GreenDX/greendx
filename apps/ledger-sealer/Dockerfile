FROM golang:1.27.3-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY main.go .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /ledger-sealer .

FROM alpine:3.24.3
RUN adduser -D -u 10001 sealer
COPY --from=build /ledger-sealer /usr/local/bin/ledger-sealer
USER sealer
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
ENTRYPOINT ["/usr/local/bin/ledger-sealer"]
