# Development Environment Setup

Commands to build and run a complete local Open edX + CertifyMe environment from scratch, using Tutor.

## Prerequisites

```bash
python3 --version                # need 3.8+
docker --version
docker compose version
df -h /                          # confirm at least 20GB free disk
free -h                          # confirm at least 4GB available RAM
```

## 1. Python virtual environment

```bash
mkdir -p ~/Desktop/Injestion
python3 -m venv ~/Desktop/Injestion/tutor-env
                                  # isolates Tutor from any other Python on the system
source ~/Desktop/Injestion/tutor-env/bin/activate
                                  # must be re-run in every new terminal - prompt shows (tutor-env) when active
```

## 2. Install Tutor

```bash
pip install tutor[full]
tutor --version                  # confirms install; also installs official plugins (mfe, discovery, forum, etc.)
```

## 3. Launch Open edX

```bash
tutor local launch
```

Prompts and answers:

```
Are you configuring a production platform? [y/N]
  Testing:    n
  Production: y (requires a real domain already pointed at this server in DNS)

Your website domain name for the LMS (LMS_HOST)
  Testing:    leave default (localhost)
  Production: your real domain, e.g. learn.example.edu

Your website domain name for the CMS/Studio (CMS_HOST)   [production only]
  studio subdomain, e.g. studio.example.edu

Your platform name/title (PLATFORM_NAME)
  any display name

Your public contact email address (CONTACT_EMAIL)
  a real, monitored address
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost   # 200 = LMS is up (production: use your real domain + https)
```

## 4. Install the CertifyMe plugin

```bash
tutor config save --append OPENEDX_EXTRA_PIP_REQUIREMENTS=openedx-certifyme==0.1.0
                                  # registers the published package as a build-time pip requirement
tutor images build openedx       # rebuilds the openedx image with the plugin baked in
tutor local launch               # relaunches with the new image; reuses previous answers, won't re-prompt
```

```bash
curl -s http://localhost/certifyme/health
                                  # should return a JSON response confirming the plugin loaded
```

## Day-to-day restart

```bash
source ~/Desktop/Injestion/tutor-env/bin/activate
tutor local start                # brings the existing stack back up without rebuilding
```

## Stopping everything

```bash
tutor local stop                 # frees RAM without deleting any data/volumes
```

## Known issues

- **`tutor: command not found`** — the venv isn't activated in the current terminal; re-run the
  `source .../activate` command from step 1.
- **Docker image pulls fail with `TLS handshake timeout`** — `tutor local launch` pulls ~10 images
  simultaneously (dozens of concurrent TLS connections); some connections choke under that load even
  when basic single-connection browsing works fine. Retry (Docker resumes partial layers), or reduce
  concurrency:
  ```bash
  echo '{"max-concurrent-downloads": 2}' | sudo tee /etc/docker/daemon.json
  sudo systemctl restart docker
  ```
- **Build fails with a disk space error** — reclaim build cache without touching images/containers/volumes:
  ```bash
  docker builder prune -f
  ```
- **System hangs / keyboard stops responding during a build** — almost always RAM exhaustion, not disk:
  the running platform (MySQL, Celery workers, MongoDB, etc.) and a concurrent build both need real
  memory. Stop the platform first (`tutor local stop`) before rebuilding on a memory-constrained machine.
- **`meilisearch` container crash-loops** (`Version file is corrupted`) — safe to fix, no data loss (the
  search index is a rebuildable cache, not source data):
  ```bash
  tutor local stop
  rm -rf $(tutor config printroot)/data/meilisearch/data.ms
  tutor local start
  ```
- **Config saved but `/certifyme/health` returns empty** — confirms the `tutor images build openedx` +
  `tutor local launch` sequence hasn't actually been run yet; saving the config alone does not rebuild
  the image.
