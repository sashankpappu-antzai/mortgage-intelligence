# Deploying mortgage-intelligence on a remote Linux server

Single-VM "scp the tarball and run docker compose" deploy. Good for an
internal demo or self-hosted trial without using Render.

> ⚠️ Same caveat as the Render guide: this stack is **not** GLBA-ready. See
> [improvements.md](../improvements.md) before letting real borrower data near it.

---

## What you need

| | |
|---|---|
| A Linux VM | Ubuntu 22.04+ / Debian 12+ recommended. Minimum 2 vCPU / 4 GB RAM / 20 GB disk. |
| Domain name (optional but recommended) | One A-record for `app.example.com` and another for `api.example.com`, both pointing at the VM's public IP. |
| Cloudflare R2 bucket | Object storage for uploaded documents. See [RENDER_DEPLOY.md §2](./RENDER_DEPLOY.md#step-2--create-the-cloudflare-r2-bucket-5-min) for the exact setup steps — the R2 credentials are identical regardless of where you deploy. |
| Anthropic API key (optional) | Only if you want cloud LLM. Otherwise self-host Ollama. |

---

## 1. On your laptop — build the tarball

```sh
cd /Users/sashankpappu/apps/mortgage-intelligence
bash scripts/package.sh
# → dist/mortgage-intelligence.tar.gz
```

The script regenerates `requirements.txt` from the uv lockfile and bundles
the backend, frontend, infra config, and deployment docs into a single
tarball. Excludes `.git`, `node_modules`, virtualenvs, and any `.env*` files
so secrets cannot leak.

---

## 2. On the server — one-time install of Docker

```sh
ssh user@your-server

# Install Docker + Compose plugin (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# log out + back in so the group membership takes effect
exit
ssh user@your-server
docker compose version          # confirm it works
```

---

## 3. Upload + extract the tarball

From your laptop:

```sh
scp dist/mortgage-intelligence.tar.gz user@your-server:/tmp/
```

On the server:

```sh
tar -xzf /tmp/mortgage-intelligence.tar.gz -C ~
cd ~/mortgage-intelligence
```

---

## 4. Fill in secrets

```sh
cp infra/.env.prod.example infra/.env.prod
nano infra/.env.prod            # or vim, whatever you have
```

The file is heavily commented — fill in everything marked `__REPLACE...__`.
At minimum you need:

1. `PUBLIC_FRONTEND_URL`, `PUBLIC_BACKEND_URL`, `ALLOWED_ORIGINS` — your two domains
2. `JWT_SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
3. `POSTGRES_PASSWORD` — any strong password (it's only seen by docker)
4. The four `STORAGE_*` values from your R2 bucket
5. `ANTHROPIC_API_KEY` if using cloud LLM

Tighten file permissions:

```sh
chmod 600 infra/.env.prod
```

---

## 5. Start the stack

```sh
cd ~/mortgage-intelligence
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod up -d --build
```

First build takes ~5 min (Python + Node base images, dependency install,
Next.js build). Subsequent rebuilds are mostly cached.

Watch the logs:

```sh
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod logs -f
# Ctrl-C to detach (services keep running)
```

You should see:
- `postgres` → `database system is ready to accept connections`
- `backend`  → `Running database migrations...` then `Uvicorn running on http://0.0.0.0:8000`
- `frontend` → `▲ Next.js …  Ready`

---

## 6. Put a reverse proxy in front (TLS + public exposure)

The compose file binds backend/frontend to **127.0.0.1 only** — they are not
reachable from the internet yet. Stand up Caddy (one config, free Let's
Encrypt) on the host:

```sh
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

# Write the config
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
app.example.com {
    reverse_proxy 127.0.0.1:3000
}

api.example.com {
    reverse_proxy 127.0.0.1:8000 {
        # SSE keep-alive
        flush_interval -1
    }
}
EOF

sudo systemctl reload caddy
```

Replace `app.example.com` / `api.example.com` with your actual domains.
Caddy auto-issues TLS certs from Let's Encrypt on first request.

Open firewall ports 80 + 443:

```sh
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

---

## 7. Smoke test

From your laptop:

```sh
curl -sf https://api.example.com/health
# → {"status":"ok"}

curl -sf -X POST https://api.example.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"correct-horse-battery","name":"Demo"}'
# → 201 with access_token + refresh_token
```

Then open `https://app.example.com/` in a browser, register, upload a sample PDF.

---

## Operations

| Task | Command |
|---|---|
| View logs | `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod logs -f backend` |
| Restart one service | `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod restart backend` |
| Update from new tarball | Stop the stack, replace files, `up -d --build` again |
| Postgres shell | `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec postgres psql -U mortgage_intelligence -d mortgage_intelligence` |
| Backup DB | `docker compose ... exec -T postgres pg_dump -U mortgage_intelligence mortgage_intelligence \| gzip > backup-$(date +%F).sql.gz` |
| Stop everything | `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod down` |
| Stop AND delete DB data | `docker compose ... down -v` (⚠️ wipes the postgres volume) |

---

## Updating to a new version

On your laptop:

```sh
git pull                                # if working from the repo, or rebuild tarball
bash scripts/package.sh
scp dist/mortgage-intelligence.tar.gz user@your-server:/tmp/
```

On the server:

```sh
cd ~/mortgage-intelligence
tar -xzf /tmp/mortgage-intelligence.tar.gz -C ~ --strip-components=1   # over-write in place
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod up -d --build
```

`.env.prod` is excluded from the tarball, so your secrets survive the update.

---

## Running without Docker (bare metal)

If you can't run Docker on the server:

1. Install Python 3.11+, Node 20+, Postgres 16.
2. `pip install -r requirements.txt` inside a venv.
3. Set the same env vars as `infra/.env.prod` in your shell or a systemd unit.
4. Migrate: `python -m alembic -c backend/db/alembic.ini upgrade head`
5. Run backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
6. Build frontend: `cd frontend && npm ci && npm run build && node .next/standalone/server.js`
7. Put nginx/Caddy in front as in step 6 above.

The bundled Dockerfiles ([backend/Dockerfile](../backend/Dockerfile),
[frontend/Dockerfile](../frontend/Dockerfile)) are the authoritative
runbook for what the bare-metal install needs — read them line-for-line
if you're going that route.
