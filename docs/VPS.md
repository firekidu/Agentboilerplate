# Deploy on a VPS

A VPS is a rented computer that stays online. You manage its operating system, backups, security updates and application. Start with a fresh Ubuntu 24.04 server. A planning size for this small pilot is 4 virtual CPUs, 8 GB RAM and at least 60 GB SSD; this is not a tested customer-capacity guarantee. No GPU is needed because the model runs at the AI provider. Existing workloads reduce the resources available to this application.

## Prepare the server and access

1. Create the server near your users and in a region acceptable for their data. Record its public IP address.
2. Use an SSH public key for access. Keep its private key on your computer. Use your provider's Ubuntu or other sudo-enabled account; use `ubuntu` in the commands below only if that is the actual account.
3. In the provider firewall, permit TCP 22 from your current public IP only. Permit TCP 80 and 443 from the internet. Leave 8000, 5432, 6333, 6334 and monitoring ports closed. Update the SSH rule when your home IP changes.
4. Open PowerShell or a terminal on your computer and connect:

```bash
ssh ubuntu@YOUR_SERVER_IP
```

Confirm the host fingerprint against the provider's console when available. The first connection asks you to trust the server. A password prompt for the private key's passphrase is normal.

## Put the project on the server

For a first deployment, uploading the source ZIP avoids putting GitHub account credentials on the server. Run this command on your **own computer**, in the folder containing the ZIP:

```bash
scp nimble-rag-agent.zip ubuntu@YOUR_SERVER_IP:~/
```

Then, on the **server**:

```bash
sudo apt-get update
sudo apt-get install -y unzip python3 git
unzip nimble-rag-agent.zip
cd nimble-rag-agent
sudo bash deploy/install_docker_ubuntu.sh
```

If you clone a private GitHub repository instead, use a read-only SSH deploy key for this repository. Do not place a broad personal access token in a clone URL, command history or `.env`.

The installation script is for a fresh Ubuntu 24.04 machine. It uses Docker's official package repository. If you already have Docker through Coolify or another setup, check it first and avoid replacing that installation. If another reverse proxy already owns ports 80 and 443, deploy this app behind that proxy instead of starting the supplied Caddy service. The instructions below assume a fresh server.

## Generate configuration and start the local demonstration

```bash
python3 scripts/setup_env.py
chmod 600 .env
sudo docker compose up -d --build
sudo docker compose ps
curl -f http://127.0.0.1:8000/health/ready
```

Save the displayed admin and reader keys in your password manager. A healthy response contains `status: ready` and `mode: fake`. Initial image downloads can take several minutes. `docker compose ps` should show the API healthy and both databases running.

The API is bound to the server's loopback address. To use it from your computer without opening port 8000, open a **second local terminal**:

```bash
ssh -L 8000:127.0.0.1:8000 ubuntu@YOUR_SERVER_IP
```

Leave that connection open. Visit http://localhost:8000 on your computer, connect, upload the example and ask the refund question. Close the SSH connection when done. If local port 8000 is already in use, use `-L 8001:127.0.0.1:8000` and visit port 8001 instead.

## Enable the real model

On the server, edit the private configuration:

```bash
nano .env
```

Set `AI_BACKEND=openai` and add your `OPENAI_API_KEY`. Use a project key dedicated to this application. Set a provider spending budget and alerts in that account. Keep the embedding model and dimensions unchanged during this lesson. Save with Ctrl O, Enter, and leave Nano with Ctrl X.

```bash
sudo docker compose up -d --force-recreate api
curl -f http://127.0.0.1:8000/health/ready
```

The mode should now be `openai`. Upload the example again because live embeddings use a different collection. Verify a cited answer and an out-of-scope refusal. A service health check does not verify your model key, credits or answer quality; a real upload and question do.

## Add your domain and HTTPS

1. In your DNS provider, add an A record such as `agent` pointing to the server's public IPv4 address. Use DNS-only mode while learning. Remove a conflicting AAAA record unless IPv6 is configured on this server.
2. In `.env`, set `DOMAIN=agent.yourdomain.com` and set `ACME_EMAIL` to an address you control. Use your actual domain; do not leave `example.com`.
3. Confirm the domain resolves to the correct address. On Windows use `nslookup agent.yourdomain.com`; on Linux the same command is available after installing `dnsutils`.
4. Start the production overlay:

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml up -d --build
sudo docker compose -f compose.yaml -f compose.prod.yaml ps
```

Caddy requests and renews a TLS certificate for the configured domain. It needs correct DNS and reachable ports 80 and 443. Visit `https://agent.yourdomain.com` and verify there is no certificate warning. The overlay forces live mode and refuses to start without a real model key.

PostgreSQL and Qdrant have no published host ports. Do not add them for convenience. Docker-published ports can bypass common host firewall rules; the provider firewall and explicit port bindings are the primary controls in this setup. The public proxy also blocks `/docs`, `/redoc`, `/openapi.json` and `/metrics`; use the SSH tunnel when you need them.

## Verify deployment before onboarding anyone

- Open the HTTPS page from a different internet connection.
- Confirm an invalid key gets rejected and the reader key cannot upload.
- Upload a small non-sensitive document and check the source text behind its answer.
- Restart the API, ask a follow-up using the existing page, and confirm the same conversation still works.
- Create a second customer key and confirm it cannot see the first customer's documents.
- Complete a backup and restore exercise on another machine.

Use the combined Compose command for future production updates. Running only the base file's `up` can remove production overrides from the API. Basic `logs`, `exec`, `stop` and `start` commands do not recreate configuration.

## Routine commands

```bash
sudo docker compose logs --tail 80 api
sudo docker compose logs --tail 80 postgres qdrant
sudo docker compose -f compose.yaml -f compose.prod.yaml logs --tail 80 caddy
sudo docker stats --no-stream
df -h
```

Treat logs and backups as customer data even though application logs omit document bodies. Never post `.env`, keys or unredacted provider errors to a public issue. See the operations guide for updates and recovery.
