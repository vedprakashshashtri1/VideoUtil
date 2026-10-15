# VideoUtil Deployment Guide

# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot

This guide covers Docker, Docker Compose, Streamlit Community Cloud, Heroku,
Northflank, Koyeb, Hugging Face Spaces, Google Cloud, and Google Colab.

## Before deploying

Add these secrets in the platform dashboard, or copy `.env.example` to `.env`
on your own server:

```env
APP_ID=12345678
API_HASH=your_api_hash
TG_BOT_TOKEN=1234567890:your_bot_token
BOT_USERNAME=YourBotUsername
AUTH_USERS=123456789
LOG_CHANNEL=@YourLogChannel
DB_URL=mongodb+srv://user:password@cluster.example.mongodb.net/
DB_NAME=enc
```

Optional: `SESSION_NAME`, `UPDATES_CHANNEL`, `PICS`, `USER_SESSION_STRING`,
`STRING_API_ID`, `STRING_API_HASH`, `SESSION_USER_ID`, `UPSTREAM_REPO`,
`GIT_TOKEN` (PAT so `/update` can pull this private repo), `WORK_DIR`, `PORT`.

Important operational rules:

- Keep the instance/replica count at **1**. Two polling processes with the
  same bot token cause Telegram `getUpdates` conflicts.
- Never commit `.env`, `secrets.toml`, bot tokens, MongoDB URIs, or string
  sessions. They are excluded by `.gitignore` and `.dockerignore`.
- Container platforms get an HTTP health server on `$PORT` — `/` and `/health`
  return 200. The image defaults to port `7860`. Hosts without `PORT` (VPS,
  Streamlit) skip the server.
- Video encoding is CPU heavy. Free tiers work for light use but will throttle
  or kill long 4K encodes; check the platform's CPU/memory limits.
- Free services sleep, stop after quota exhaustion, or use ephemeral disks. A
  VPS or a paid always-on container is the reliable choice for 24/7 hosting.
- Sessions, thumbnails, and temp files live under `WORK_DIR`
  (Docker image uses `/data`). Mount a persistent volume where supported.

## Docker or Docker Compose

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
docker compose logs -f
```

Compose mounts the `video-util-data` volume at `/data` and restarts the single
bot container unless explicitly stopped. For plain Docker:

```bash
docker build -t videoutil-bot .
docker run -d --name videoutil-bot --restart unless-stopped \
  --env-file .env -p 7860:7860 -v video-util-data:/data videoutil-bot
```

Health check: `http://SERVER_IP:7860/health`.

## Streamlit Community Cloud

See the [README](README.md#streamlit-community-cloud-deployment) for the full
walkthrough: entrypoint `app.py`, Python 3.11, secrets pasted in
**Advanced settings → Secrets**. `packages.txt` installs FFmpeg, MediaInfo,
Megatools, Git, and curl automatically.

Community Cloud hibernates apps after 12 hours without web traffic, so open the
app URL periodically if you need the bot online. It is a compatibility option,
not dependable 24/7 hosting.

## Heroku (Container Stack)

The repository includes `heroku.yml`, `app.json`, and a `Procfile`.

```bash
heroku create YOUR_APP_NAME --stack container
heroku config:set APP_ID='...' API_HASH='...' TG_BOT_TOKEN='...' \
  BOT_USERNAME='...' AUTH_USERS='...' LOG_CHANNEL='...' \
  DB_URL='...' DB_NAME='enc'
git push heroku main
heroku ps:scale web=1
```

Or use the **Deploy to Heroku** button created from `app.json`. The container
listens on Heroku's dynamic `PORT`. Heroku's filesystem is ephemeral, so
MongoDB stays the durable store. A single `basic` dyno is the minimum for a
worker like this.

## Northflank

1. Create a **Combined Service** and connect this GitHub repository.
2. Select **Dockerfile** build with file `/Dockerfile` (buildpacks do not ship
   FFmpeg).
3. Add the required secrets under **Runtime variables**.
4. Add a public HTTP port `7860` and set `PORT=7860`, `WORK_DIR=/data`.
5. Configure `/health` as the HTTP health check path.
6. Use one instance only. Attach a volume at `/data` if the plan supports it.

CI/CD is enabled by default: every push to `main` rebuilds and redeploys.

## Koyeb

1. Create an App and a service from the GitHub repository.
2. Choose the repository's **Dockerfile** builder (buildpacks lack FFmpeg).
3. Add the required environment variables/secrets.
4. Set service type **Web**, keep the supplied `PORT`, add `WORK_DIR=/data`.
5. Expose one HTTP port using `PORT`, route `/`, health path `/health`.
6. Deploy with exactly one instance.

`koyeb app init` alternative:

```bash
koyeb app init videoutil \
  --git github.com/PrimeSujoy/VideoUtil \
  --git-branch main \
  --git-builder docker \
  --instance-type nano \
  --port 7860:http \
  --env WORK_DIR=/data
```

## Hugging Face Docker Space

1. Create a new Space with the **Docker** SDK and push this repository into it
   (or import from GitHub).
2. The README's front matter already declares `sdk: docker` and
   `app_port: 7860`; the Docker image defaults `PORT=7860` and exposes it.
3. In **Space Settings → Variables and secrets**, add the required secrets.
4. Add `WORK_DIR=/data` as a variable. Rebuild the Space and check the logs for
   `Health server listening on :7860`.

Use one Space per bot token. Free hardware can sleep and local storage is
ephemeral unless persistent storage is added. UID 1000 in the Dockerfile
matches the Space runtime user.

## Google Cloud

### Cloud Run (simplest)

```bash
gcloud run deploy videoutil \
  --source . \
  --region asia-south1 \
  --no-allow-unauthenticated \
  --min-instances 1 \
  --max-instances 1 \
  --cpu 1 \
  --memory 2Gi \
  --set-env-vars DB_NAME=enc,UPSTREAM_REPO=PrimeSujoy/VideoUtil
```

Add the remaining secrets with `--set-secrets` (for example
`--set-secrets TG_BOT_TOKEN=TG_BOT_TOKEN:latest,...`) or the console. Cloud Run
injects `PORT`, which the health server binds automatically. The bot polls
Telegram constantly, so keep **CPU always allocated** and `min-instances=1` in
the console — otherwise the container freezes between requests. Watch billing:
always-on Cloud Run is not free.

### Compute Engine (most reliable)

A small VM with Docker runs the same image 24/7:

```bash
gcloud compute instances create videoutil \
  --zone asia-south1-a \
  --machine-type e2-medium \
  --image-family debian-12 \
  --image-project debian-cloud \
  --metadata startup-script='apt-get update && apt-get install -y docker.io && systemctl enable --now docker && docker run -d --restart unless-stopped --env-file /root/.env -p 7860:7860 -v video-util-data:/data videoutil-bot'
```

Clone the repo on the VM, create `.env`, then `docker compose up -d --build`.

## Google Colab

Open `VideoUtil_Colab.ipynb` in [Google Colab](https://colab.research.google.com/),
run the cells in order, and paste a GitHub PAT with `repo` scope when cloning
this private repository (make the repo public to skip that step).

1. Cell 1 installs FFmpeg, MediaInfo, Megatools, and Git.
2. Cell 2 clones the repository and installs `requirements.txt`.
3. Cell 3 collects secrets (Colab **Secrets** storage first, prompt fallback)
   and writes `.env` — `bot/get_cfg.py` loads it automatically.
4. Cell 4 starts the bot; interrupt the kernel to stop it.
5. Cell 5 enables the keep-alive snippet so the runtime is not disconnected.

Colab is a demo/testing host: the VM can disconnect after inactivity, disks are
ephemeral, and CPU throttling will slow large encodes. Keep exactly one active
run per bot token.

## Troubleshooting

`Conflict: terminated by other getUpdates request`
: Another deployment or local process is using the same bot token. Stop it and
  leave exactly one running instance.

Health check fails
: Confirm the platform injects `PORT` (or the image default `7860`), the
  service routes to that port, and the check path is `/health`.

Bot exits immediately
: Check logs for missing `APP_ID`, `API_HASH`, `TG_BOT_TOKEN`, `AUTH_USERS`,
  `LOG_CHANNEL`, or `DB_URL`. MongoDB Atlas must allow the host's network
  access (IP allowlist `0.0.0.0/0` for dynamic hosts).

FFmpeg not found
: Deploy with the repository's Dockerfile (installs FFmpeg, MediaInfo, Git).
  On VPS: `apt install ffmpeg mediainfo git`.

`/update` fails
: Set `UPSTREAM_REPO` and `GIT_TOKEN` secrets; inside Docker the image already
  ships Git.

Files disappear after restart
: The host uses an ephemeral filesystem. Attach a volume at `/data`
  (`WORK_DIR`), or use a VPS. Partial downloads are intentionally cleaned on
  startup.
