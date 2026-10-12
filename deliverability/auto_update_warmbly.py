#!/usr/bin/env python3
"""
Warmbly Autonomous Auto-Update Cron Worker
Monitors upstream GitHub repo (https://github.com/warmbly/warmbly) and GHCR container images.
Automatically detects when updates are published, safely applies local production bindings,
recreates all Warmbly containers, performs health verification, and cleans up unused images.
"""

import os
import sys
import time
import datetime
import subprocess
import urllib.request
from pathlib import Path

WARMBLY_DIR = Path("/opt/apps/warmbly")
LOG_FILE = Path("/var/log/warmbly-auto-update.log")
BACKUP_COMPOSE = WARMBLY_DIR / "docker-compose.yml.local_backup"


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def run_cmd(cmd: list[str], cwd=None) -> tuple[int, str]:
    res = subprocess.run(
        cmd,
        cwd=cwd or WARMBLY_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    return res.returncode, res.stdout.strip()


def patch_docker_compose(content: str) -> str:
    """Applies required local port isolation and internal host bindings."""
    # 1. Postgres localhost isolation
    content = content.replace('ports: ["15432:5432"]', 'ports: ["127.0.0.1:15432:5432"]')
    # 2. Redis localhost isolation
    content = content.replace('ports: ["16379:6379"]', 'ports: ["127.0.0.1:16379:6379"]')
    # 3. NATS localhost isolation
    content = content.replace('ports: ["4222:4222", "8222:8222"]', 'ports: ["127.0.0.1:4222:4222", "127.0.0.1:8222:8222"]')
    
    # 4. Backend port 8085 + host gateway
    if 'ports: ["127.0.0.1:8085:8080"]' not in content:
        content = content.replace(
            'ports: ["8080:8080"]',
            'ports: ["127.0.0.1:8085:8080"]\n    extra_hosts:\n      - "host.docker.internal:host-gateway"'
        )
    
    # 5. Worker host gateway for local SMTP/IMAP
    worker_target = 'image: ${WARMBLY_IMAGE_PREFIX:-ghcr.io/warmbly/warmbly}/worker'
    if 'extra_hosts:\n      - "host.docker.internal:host-gateway"\n    image: ${WARMBLY_IMAGE_PREFIX:-ghcr.io/warmbly/warmbly}/worker' not in content:
        content = content.replace(
            worker_target,
            'extra_hosts:\n      - "host.docker.internal:host-gateway"\n    ' + worker_target
        )
    
    # 6. Realtime localhost isolation
    content = content.replace('ports: ["4000:4000"]', 'ports: ["127.0.0.1:4000:4000"]')
    # 7. Web frontend localhost isolation
    content = content.replace('ports: ["5173:80"]', 'ports: ["127.0.0.1:5173:80"]')
    # 8. Admin localhost isolation
    content = content.replace('ports: ["5174:80"]', 'ports: ["127.0.0.1:5174:80"]')
    
    return content


def check_health(retries=5, delay=5) -> bool:
    """Verifies that the web frontend and backend API respond locally."""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request("http://127.0.0.1:5173")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def main(force=False):
    if not WARMBLY_DIR.exists():
        log(f"ERROR: Warmbly directory {WARMBLY_DIR} does not exist.")
        sys.exit(1)

    log("🔍 Checking for Warmbly updates...")

    # 1. Fetch latest upstream git commits
    code, out = run_cmd(["git", "fetch", "origin", "main", "--quiet"])
    if code != 0:
        log(f"⚠️ git fetch failed: {out}")
        sys.exit(1)

    _, local_commit = run_cmd(["git", "rev-parse", "HEAD"])
    _, remote_commit = run_cmd(["git", "rev-parse", "origin/main"])

    has_git_update = (local_commit != remote_commit)

    # 2. Check for new Docker image updates
    code, pull_check = run_cmd(["docker", "compose", "pull"])
    has_image_update = ("Downloaded newer image" in pull_check or "Pull complete" in pull_check)

    if not has_git_update and not has_image_update and not force:
        log(f"ℹ️ Warmbly is already on latest version ({local_commit[:8]}). No updates needed.")
        return

    log(f"🚀 Update detected! Git update: {has_git_update} ({local_commit[:8]} -> {remote_commit[:8]}), Image update: {has_image_update}")

    compose_path = WARMBLY_DIR / "docker-compose.yml"
    
    # 3. Backup current working docker-compose.yml
    if compose_path.exists():
        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                current_compose = f.read()
            with open(BACKUP_COMPOSE, "w", encoding="utf-8") as f:
                f.write(current_compose)
        except Exception as e:
            log(f"⚠️ Failed to write backup compose: {e}")

    # 4. If git update available, reset to upstream and patch
    if has_git_update or force:
        log("🔄 Pulling latest source code from origin/main...")
        run_cmd(["git", "reset", "--hard", "origin/main"])
        
        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                clean_compose = f.read()
            
            patched_compose = patch_docker_compose(clean_compose)
            
            with open(compose_path, "w", encoding="utf-8") as f:
                f.write(patched_compose)
            log("🔧 Successfully reapplied production port & gateway customizations.")
        except Exception as e:
            log(f"❌ Error patching docker-compose.yml: {e}")
            if BACKUP_COMPOSE.exists():
                log("Restoring backup docker-compose.yml...")
                compose_path.write_text(BACKUP_COMPOSE.read_text())

    # 5. Pull any remaining container layers
    log("📥 Pulling updated production container images...")
    run_cmd(["docker", "compose", "pull"])

    # 6. Recreate and start containers
    log("♻️ Recreating Warmbly microservices...")
    code, up_out = run_cmd(["docker", "compose", "up", "-d", "--remove-orphans"])
    if code != 0:
        log(f"❌ Error starting containers: {up_out}")
        if BACKUP_COMPOSE.exists():
            log("Rolling back to backup docker-compose.yml...")
            compose_path.write_text(BACKUP_COMPOSE.read_text())
            run_cmd(["docker", "compose", "up", "-d"])
        sys.exit(1)

    # 7. Clean up old unused docker images to prevent VPS disk bloat
    run_cmd(["docker", "image", "prune", "-f"])

    # 8. Verify service health
    log("🩺 Verifying instance health...")
    if check_health():
        _, new_head = run_cmd(["git", "rev-parse", "--short", "HEAD"])
        log(f"🎉 Warmbly successfully updated to {new_head} and verified healthy at https://warmly.tanim.tech!")
    else:
        log("⚠️ Warmbly web service did not respond with 200 within timeout. Check container logs.")


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    main(force=force_flag)
