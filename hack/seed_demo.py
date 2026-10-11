#!/usr/bin/env python3
"""Seed a running Playbook instance with the demo catalog.

Creates tags and actions that point at the demo scripts bundled with the Helm
chart (charts/playbook/scripts), and optionally runs a few of them so the
history drawer has content. Idempotent: existing tags/actions with the same
name/title are reused, not duplicated.

    python hack/seed_demo.py --url http://localhost:8000 --password changeme --run

Works against a local run, a `kubectl port-forward`, or a Route. Stdlib only.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

TAGS = [
    # (name, type, color)
    ("Deploy", "function", "blue"),
    ("Kubernetes", "function", "indigo"),
    ("Database", "function", "amber"),
    ("Quality", "function", "green"),
    ("Security", "function", "rose"),
    ("Release", "function", "plum"),
    ("Examples", "function", "slate"),
    ("Platform", "team", "slate"),
    ("SRE", "team", "slate"),
    ("Data", "team", "slate"),
    ("QA", "team", "slate"),
]

SERVICES = ["orders-api", "payments-api", "web-frontend", "search-indexer"]
ENVIRONMENTS = ["dev", "staging", "prod"]
NAMESPACES = ["shop-dev", "shop-staging", "shop-prod"]


def p(name, type_="text", **kw):
    return {"name": name, "type": type_, **kw}


ACTIONS = [
    {
        "title": "Deploy service",
        "description": "Roll out a service version to an environment with Helm and wait for the rollout.",
        "icon": "rocket", "tags": ["Deploy", "Platform"],
        "script_path": "deploy/deploy_service.sh",
        "parameters": [
            p("service", "select", options=SERVICES, default="orders-api", required=True),
            p("version", default="2.4.0", required=True),
            p("environment", "radio", options=ENVIRONMENTS, default="staging", required=True),
            p("dry_run", "checkbox", default=False),
        ],
    },
    {
        "title": "Roll back release",
        "description": "Revert a Helm release to its previous revision.",
        "icon": "helm", "tags": ["Deploy", "Platform"],
        "script_path": "deploy/rollback_release.sh",
        "parameters": [
            p("service", "select", options=SERVICES, required=True),
            p("environment", "radio", options=ENVIRONMENTS, default="staging", required=True),
            p("reason"),
        ],
    },
    {
        "title": "Restart deployment",
        "description": "Rolling restart, e.g. to pick up a rotated secret.",
        "icon": "openshift", "tags": ["Kubernetes", "SRE"],
        "script_path": "kubernetes/restart_deployment.sh",
        "parameters": [
            p("namespace", "select", options=NAMESPACES, default="shop-staging", required=True),
            p("deployment", default="orders-api", required=True),
        ],
    },
    {
        "title": "Scale deployment",
        "description": "Set the replica count of a deployment.",
        "icon": "kubernetes", "tags": ["Kubernetes", "SRE"],
        "script_path": "kubernetes/scale_deployment.sh",
        "parameters": [
            p("namespace", "select", options=NAMESPACES, default="shop-staging", required=True),
            p("deployment", default="orders-api", required=True),
            p("replicas", "number", default="3", required=True),
        ],
    },
    {
        "title": "Back up database",
        "description": "Logical backup with checksum, published as a download.",
        "icon": "database", "tags": ["Database", "Data"],
        "script_path": "database/backup_database.py",
        "parameters": [
            p("database", "select", options=["orders", "payments", "inventory"], default="orders", required=True),
            p("compress", "checkbox", default=True),
        ],
    },
    {
        "title": "Run smoke tests",
        "description": "Post-deploy smoke suite; produces a JUnit report.",
        "icon": "activity", "tags": ["Quality", "QA"],
        "script_path": "quality/smoke_tests.py",
        "parameters": [
            p("environment", "radio", options=ENVIRONMENTS, default="staging", required=True),
            p("suite", "select", options=["core", "checkout", "full"], default="core"),
        ],
    },
    {
        "title": "Certificate expiry report",
        "description": "List TLS certificates expiring within N days as CSV.",
        "icon": "shield", "tags": ["Security", "SRE"],
        "script_path": "security/cert_expiry_report.py",
        "parameters": [p("days", "number", default="30", required=True)],
    },
    {
        "title": "Generate release notes",
        "description": "Markdown changelog between two tags, grouped by type.",
        "icon": "git", "tags": ["Release", "Platform"],
        "script_path": "release/release_notes.py",
        "parameters": [
            p("from_version", default="v2.3.0", required=True),
            p("to_version", default="v2.4.0", required=True),
        ],
    },
    {
        "title": "Hello world",
        "description": "Minimal example: parameters in, artifact out.",
        "icon": "play", "tags": ["Examples"],
        "script_path": "examples/hello.py",
        "parameters": [p("name", default="world"), p("greeting", default="Hello")],
    },
    {
        "title": "Long task (graceful stop)",
        "description": "Runs for a minute; press Stop to watch its cleanup trap run.",
        "icon": "gauge", "tags": ["Examples"],
        "script_path": "examples/long_task.py",
        "parameters": [],
    },
    {
        "title": "Process an uploaded file",
        "description": "File parameter demo: upload, process, download the result.",
        "icon": "upload", "tags": ["Examples"],
        "script_path": "examples/show_file.py",
        "parameters": [p("doc", "file", required=True)],
    },
    {
        "title": "Failing script",
        "description": "Exits non-zero to show how failures are reported.",
        "icon": "alert", "tags": ["Examples"],
        "script_path": "examples/fail_demo.sh",
        "parameters": [],
    },
]

# Runs that populate the history drawer: (action title, values).
DEMO_RUNS = [
    ("Generate release notes", {}),
    ("Back up database", {"database": "payments"}),
    ("Failing script", {}),
    ("Run smoke tests", {"environment": "staging"}),
    ("Deploy service", {"service": "payments-api", "version": "2.4.1", "environment": "staging"}),
]


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            sys.exit(f"{method} {path} -> {exc.code}: {exc.read().decode(errors='replace')}")
        return json.loads(raw) if raw else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--password", required=True, help="ADMIN_PASSWORD of the instance")
    ap.add_argument("--run", action="store_true", help="also execute a few actions to fill history")
    args = ap.parse_args()

    c = Client(args.url)
    c.call("POST", "/api/v1/admin/login", {"password": args.password})

    tag_ids = {t["name"]: t["id"] for t in c.call("GET", "/api/v1/tags")}
    for name, type_, color in TAGS:
        if name not in tag_ids:
            tag_ids[name] = c.call("POST", "/api/v1/tags", {"name": name, "type": type_, "color": color})["id"]
    print(f"tags: {len(tag_ids)}")

    existing = {a["title"]: a["id"] for a in c.call("GET", "/api/v1/actions/admin")}
    action_ids = {}
    for spec in ACTIONS:
        body = {**spec, "tags": [tag_ids[t] for t in spec["tags"]]}
        if spec["title"] in existing:
            action_ids[spec["title"]] = existing[spec["title"]]
            c.call("PUT", f"/api/v1/actions/{existing[spec['title']]}", body)
        else:
            action_ids[spec["title"]] = c.call("POST", "/api/v1/actions", body)["id"]
    print(f"actions: {len(action_ids)}")

    if args.run:
        for title, values in DEMO_RUNS:
            res = c.call("POST", f"/api/v1/execute/{action_ids[title]}", {"values": values})
            eid = res["execution_id"]
            for _ in range(120):
                runs = {e["id"]: e for e in c.call("GET", "/api/v1/executions?limit=50")}
                status = runs.get(eid, {}).get("status")
                if status in ("SUCCESS", "FAILED", "STOPPED"):
                    break
                time.sleep(0.5)
            print(f"ran {title!r}: {status}")


if __name__ == "__main__":
    main()
