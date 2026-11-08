# Installing EcoTrace from source

This guide builds and runs the whole platform from this repository on your own machine:

- the core: identity, gateway, data, events, storage, workflow, ledger;
- the capabilities: Document Intake and Workflow;
- the apps: Carbon Ledger and Purchase Approval;
- the demo console.

Every service is built from the source in this repository or pulled as a pinned, open-source container image. No step needs a closed-source tool.

## 1. Requirements

| | Minimum | Tested with |
|---|---|---|
| Operating system | Linux x86_64. On Windows, use WSL 2 with a Linux distribution. | Ubuntu 24.04 LTS |
| CPU | 4 cores | 4 cores |
| Memory | 8 GB. The running stack uses about 3.2 GB; the first build needs more. 16 GB is recommended. | 16 GB |
| Free disk | 20 GB. Images take about 10 GB and the build cache about 2.5 GB. | |
| Docker Engine with the Compose plugin | Compose v2 or later | Docker 29.9, Compose 5.6 |
| Command-line tools | `git`, `make`, `curl`, `jq` | GNU Make 4.3, jq 1.7 |
| Network | Internet access the first time, to pull images and libraries | |

Free ports on the machine:

- **9080**: the platform, with the console, the APIs and `/api-docs`;
- **8080**: the Keycloak admin console;
- **8081**: the Hasura console.

### Install the tools on Ubuntu

All of these come from Ubuntu's own open-source packages:

```sh
sudo apt update
sudo apt install -y git make curl jq docker.io docker-compose-v2
sudo usermod -aG docker "$USER"   # then log out and back in, so docker works without sudo
docker compose version            # must print v2 or later
```

On other distributions, install Docker Engine and the Compose plugin from your distribution or from <https://docs.docker.com/engine/install/>.

## 2. Get the source

```sh
git clone https://github.com/CMC-GreenDX/greendx.git
cd greendx
```

You can also download a `.tar.gz` source archive of a release from <https://github.com/CMC-GreenDX/greendx/releases> and extract it.

## 3. Configure

All configuration is in `.env`, created from [.env.example](../.env.example). You never edit source files to configure the platform.

```sh
cp .env.example .env   # make up does this for you if .env is missing
```

Before anyone else can reach the machine, replace every `change-me-…` value in `.env` with your own secret. The main settings:

| Setting | Meaning |
|---|---|
| `PUBLIC_URL` | Address users type in the browser. The default is `http://localhost:9080`. Change it when the platform runs on a server: see "Sharing a public link" in [demo-script.md](demo-script.md). |
| `DEMO_USER_PASSWORD` | Password of the demo users `alice`, `an.tran`, `bob` and `binh.le` |
| `KC_ADMIN_PASSWORD`, `HASURA_ADMIN_SECRET` | Administrator passwords of Keycloak and Hasura |
| `POSTGRES_PASSWORD`, `*_DB_PASSWORD` | Database passwords: the superuser, plus one role per service |

AI extraction is optional. Without a key, Document Intake uses its rule-based extractor, which runs entirely on your machine. To use a hosted model, export the key in the shell that runs `make up`. The key is never written to a file in the repository.

```sh
export GEMINI_API_KEY=...          # default provider; or:
export AI_PROVIDER=claude ANTHROPIC_API_KEY=...
```

Read [ADR-0002](adr/0002-hosted-llm-api-for-document-intake.md) before sending real documents to a hosted model.

Companies (tenants) are configured by their config packs in [tenants/](../tenants), validated against the JSON Schemas in [core/schemas/](../core/schemas). See [tools/dxctl](../tools/dxctl/README.md).

## 4. Build and start

```sh
make up       # builds the service images from source, starts everything, waits until healthy, loads the demo companies
make health   # every line must say OK
```

The first `make up` takes about 10 to 20 minutes:

- six images are built from this repository;
- about 10 GB of images are pulled;
- ClamAV downloads its virus signatures.

Later starts take about a minute.

Then open:

| Address | What |
|---|---|
| <http://localhost:9080> | Demo console: log in as `alice` with `DEMO_USER_PASSWORD` |
| <http://localhost:9080/api-docs> | API reference: log in with **Authorize** and use **Try it out**. See the [API guide](api/README.md). |
| <http://localhost:8080/admin/> | Keycloak admin console: user `admin`, password `KC_ADMIN_PASSWORD` |
| <http://localhost:8081/console> | Hasura console: `HASURA_ADMIN_SECRET` |

## 5. Check that it works

Each command prints a PASS or FAIL line per check:

```sh
make demo             # identity -> gateway -> data, with tenant isolation
make rls-check        # PostgreSQL row-level security between companies
make intake-check     # upload, malware scan, extraction, review, duplicates
make workflow-check   # approval processes per company
make ledger-check     # document -> activity -> approval -> emission entry -> lineage
make seal-check       # close and seal a period, detect tampering
make ui-check         # browser test of the console and the API page (uses Docker)
make api-check        # runs the Postman collection
```

`make help` lists every target. [docs/demo-script.md](demo-script.md) walks through the product in the browser.

## 6. Stop, restart, remove

```sh
make down     # stop; data is kept in Docker volumes
make up       # start again
make reset    # stop and delete all data (databases, documents, ledger)
```

To remove everything, run `make reset`, then `docker image prune -a` and delete the folder.

## Without make

`make` only wraps Docker Compose commands, so you can run them directly from the repository root:

```sh
docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile core up -d --build --wait
curl -fsS -X POST http://localhost:8081/v1/metadata -H "Content-Type: application/json" \
  -H "X-Hasura-Admin-Secret: $HASURA_ADMIN_SECRET" -d @deploy/compose/demo/hasura/metadata.json
docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile tools run --rm --build dxctl \
  tenant create tenants/company-a-steel
```

The services run as containers. Their images are built from this repository, and their configuration is mounted from `deploy/`, `core/` and `tenants/`. The commands must therefore run from the repository root, but nothing has to be installed into system folders.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied … docker.sock` | Your user is not in the `docker` group yet. Log out and back in after `usermod`. |
| `port is already allocated` | Another program uses 9080, 8080 or 8081. Stop it, or change the left-hand port in `deploy/compose/docker-compose.yml`. If you change 9080, change `PUBLIC_URL` too. |
| `make up` stops at `clamav` | The first signature download can take several minutes. Run `make up` again. |
| Services restart or are killed | Not enough memory. Close other programs, or use a machine with 16 GB. |
| The login page loops back, or says "invalid redirect" | `PUBLIC_URL` does not match the address in the browser. Fix it in `.env` and run `make up`. |
| A photo takes a long time to read | The hosted AI model is busy. E-invoice XML is read instantly, without AI. |

`make logs` follows the logs of every service.

## Alternative: GitHub Codespaces

If no machine with enough memory is available, the repository's dev container ([.devcontainer](../.devcontainer)) opens a 4-core, 16 GB Linux machine with Docker in GitHub Codespaces. Run the same commands from step 4 there.
