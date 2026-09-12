"""Generate deterministic, non-PII capacity data as JSONL."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "working-tree"


def generate(output: Path, *, tenants: int, contacts_per_tenant: int, messages_per_contact: int, seed: int, workers: int, db_version: str, redis_version: str) -> None:
    metadata = {
        "seed": seed, "revision": git_revision(), "cpu": platform.processor(),
        "ram": platform.system(), "worker_count": workers,
        "database_version": db_version, "redis_version": redis_version,
        "simulation_latency_ms": 25,
        "counts": {"tenants": tenants, "contacts": tenants * contacts_per_tenant, "messages": tenants * contacts_per_tenant * messages_per_contact},
    }
    with output.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"kind": "metadata", **metadata}) + "\n")
        for tenant_number in range(tenants):
            tenant_id = f"tenant-{seed}-{tenant_number:06d}"
            stream.write(json.dumps({"kind": "tenant", "id": tenant_id, "name": f"Synthetic Tenant {tenant_number}"}) + "\n")
            for contact_number in range(contacts_per_tenant):
                contact_id = f"contact-{seed}-{tenant_number:06d}-{contact_number:06d}"
                stream.write(json.dumps({"kind": "contact", "id": contact_id, "tenant_id": tenant_id, "name": f"Synthetic Contact {contact_number}", "email": f"contact-{tenant_number}-{contact_number}@example.test"}) + "\n")
                for message_number in range(messages_per_contact):
                    stream.write(json.dumps({"kind": "message", "tenant_id": tenant_id, "contact_id": contact_id, "direction": "inbound" if message_number % 2 == 0 else "outbound", "body": f"Synthetic message {message_number}"}) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("capacity-seed.jsonl"))
    parser.add_argument("--tenants", type=int, default=1000)
    parser.add_argument("--contacts-per-tenant", type=int, default=100)
    parser.add_argument("--messages-per-contact", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--db-version", default="postgres:17")
    parser.add_argument("--redis-version", default="redis:7.4")
    args = parser.parse_args()
    generate(args.output, tenants=args.tenants, contacts_per_tenant=args.contacts_per_tenant, messages_per_contact=args.messages_per_contact, seed=args.seed, workers=args.workers, db_version=args.db_version, redis_version=args.redis_version)
