"""dxctl: onboard and manage EcoTrace tenants from config packs, without code changes.

    dxctl tenant validate tenants/<pack>
    dxctl tenant create   tenants/<pack>     # registry, Keycloak group/roles/users, bucket, facilities (idempotent)
    dxctl tenant disable  <tenant-id>
    dxctl tenant enable   <tenant-id>
    dxctl tenant list
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import asyncpg
import boto3
import requests
import yaml
from botocore.config import Config
from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_DIR = Path(os.environ.get("SCHEMA_DIR", "/schemas"))
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "ecotrace")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ROLES = ["uploader", "reviewer", "approver", "tenant-admin"]
PACK_FILES = {
    "tenant.yaml": "tenant.schema.json",
    "org.yaml": "org.schema.json",
    "document-types.yaml": "document-types.schema.json",
    "emission-sources.yaml": "emission-sources.schema.json",
    "emission-factors.yaml": "emission-factors.schema.json",
}


class Failed(Exception):
    pass


def say(step: str, message: str) -> None:
    print(f"  \033[32m✓\033[0m {step:<10} {message}")


# --- validate -----------------------------------------------------------------------------------

def load_pack(path: Path) -> dict[str, dict]:
    """Validates every file of a config pack against its JSON Schema, then checks cross-file references."""
    if not path.is_dir():
        raise Failed(f"{path} is not a config pack folder")
    pack, errors = {}, []
    for filename, schema_file in PACK_FILES.items():
        file = path / filename
        if not file.exists():
            errors.append(f"{filename}: missing")
            continue
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        schema = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
        for err in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data):
            location = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"{filename}: {location}: {err.message}")
        pack[filename] = data
    if not errors:
        errors += cross_checks(path, pack)
    if errors:
        raise Failed("invalid config pack:\n    " + "\n    ".join(errors))
    return pack


def cross_checks(path: Path, pack: dict[str, dict]) -> list[str]:
    errors = []
    tenant, org = pack["tenant.yaml"], pack["org.yaml"]
    types = {t["id"]: {f["name"] for f in t["fields"]} for t in pack["document-types.yaml"]["document_types"]}
    sources = pack["emission-sources.yaml"]
    facilities = {f["code"] for f in sources["facilities"]}
    if tenant["id"] != path.name:
        errors.append(f"tenant.yaml: id '{tenant['id']}' must equal the folder name '{path.name}'")
    departments = {d["id"] for d in org["departments"]}
    for user in org["users"]:
        if user.get("department") and user["department"] not in departments:
            errors.append(f"org.yaml: user {user['username']}: unknown department {user['department']}")
    for source in sources["sources"]:
        if source["document_type"] not in types:
            errors.append(f"emission-sources.yaml: {source['id']}: document type {source['document_type']} is not accepted in document-types.yaml")
        elif source["quantity_field"] not in types[source["document_type"]]:
            errors.append(f"emission-sources.yaml: {source['id']}: {source['document_type']} has no field {source['quantity_field']}")
        if source.get("facility") and source["facility"] not in facilities:
            errors.append(f"emission-sources.yaml: {source['id']}: unknown facility {source['facility']}")
        if source["factor"] not in pack["emission-factors.yaml"]["factors"]:
            errors.append(f"emission-sources.yaml: {source['id']}: factor {source['factor']} is not in emission-factors.yaml")
    return errors


# --- Keycloak -----------------------------------------------------------------------------------

class Keycloak:
    def __init__(self) -> None:
        token = requests.post(
            f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli", "username": "admin",
                  "password": os.environ["KC_ADMIN_PASSWORD"]}, timeout=15)
        token.raise_for_status()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
        self.base = f"{KEYCLOAK_URL}/admin/realms/{REALM}"

    def call(self, method: str, path: str, **kwargs):
        response = self.session.request(method, self.base + path, timeout=15, **kwargs)
        if response.status_code >= 400:
            raise Failed(f"Keycloak {method} {path}: {response.status_code} {response.text[:200]}")
        return response.json() if response.content and "json" in response.headers.get("Content-Type", "") else None

    def ensure_roles(self) -> None:
        existing = {r["name"] for r in self.call("GET", "/roles")}
        for role in ROLES:
            if role not in existing:
                self.call("POST", "/roles", json={"name": role, "description": f"EcoTrace {role}"})

    def ensure_group(self, tenant_id: str, name: str) -> str:
        group_name = f"tenant-{tenant_id}"
        found = [g for g in self.call("GET", "/groups", params={"search": group_name, "exact": "true"}) if g["name"] == group_name]
        body = {"name": group_name, "attributes": {"tenant_id": [tenant_id], "display_name": [name]}}
        if found:
            self.call("PUT", f"/groups/{found[0]['id']}", json=body)
            return found[0]["id"]
        self.call("POST", "/groups", json=body)
        return [g for g in self.call("GET", "/groups", params={"search": group_name, "exact": "true"}) if g["name"] == group_name][0]["id"]

    def find_user(self, username: str) -> dict | None:
        users = self.call("GET", "/users", params={"username": username, "exact": "true"})
        return users[0] if users else None

    def ensure_user(self, tenant_id: str, group_id: str, user: dict) -> str:
        """Creates or updates a user. Returns a note about the password."""
        existing = self.find_user(user["username"])
        if existing and existing.get("attributes", {}).get("tenant_id", [tenant_id]) != [tenant_id]:
            raise Failed(f"user {user['username']} already belongs to another tenant")
        body = {
            "username": user["username"], "enabled": True, "email": user["email"], "emailVerified": True,
            "firstName": user["first_name"], "lastName": user["last_name"],
            "attributes": {"tenant_id": [tenant_id], **({"department": [user["department"]]} if user.get("department") else {})},
        }
        note = "existing password kept"
        if existing:
            self.call("PUT", f"/users/{existing['id']}", json=body)
            user_id = existing["id"]
        else:
            self.call("POST", "/users", json=body)
            user_id = self.find_user(user["username"])["id"]
            password = os.environ.get(user.get("initial_password_env", ""), "")
            temporary = not password
            if not password:
                password = secrets.token_urlsafe(12)
                note = f"temporary password {password} (must be changed at first login)"
            else:
                note = f"password from ${user['initial_password_env']}"
            self.call("PUT", f"/users/{user_id}/reset-password",
                      json={"type": "password", "value": password, "temporary": temporary})
        self.call("PUT", f"/users/{user_id}/groups/{group_id}")
        roles = [r for r in self.call("GET", "/roles") if r["name"] in user["roles"]]
        self.call("POST", f"/users/{user_id}/role-mappings/realm", json=roles)
        return note

    def set_enabled(self, tenant_id: str, enabled: bool) -> int:
        group = [g for g in self.call("GET", "/groups", params={"search": f"tenant-{tenant_id}", "exact": "true"})
                 if g["name"] == f"tenant-{tenant_id}"]
        if not group:
            return 0
        members = self.call("GET", f"/groups/{group[0]['id']}/members", params={"max": 1000})
        for member in members:
            self.call("PUT", f"/users/{member['id']}", json={**member, "enabled": enabled})
            if not enabled:
                self.call("POST", f"/users/{member['id']}/logout")
        return len(members)

    def member_count(self, tenant_id: str) -> int:
        group = [g for g in self.call("GET", "/groups", params={"search": f"tenant-{tenant_id}", "exact": "true"})
                 if g["name"] == f"tenant-{tenant_id}"]
        return len(self.call("GET", f"/groups/{group[0]['id']}/members", params={"max": 1000})) if group else 0


# --- Storage ------------------------------------------------------------------------------------

def ensure_bucket(tenant_id: str) -> str:
    s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333"),
                      aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"],
                      region_name="us-east-1", config=Config(s3={"addressing_style": "path"}))
    bucket = f"ecotrace-{tenant_id}"
    try:
        s3.head_bucket(Bucket=bucket)
        return f"{bucket} (exists)"
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        return f"{bucket} (created)"


# --- Workflows ----------------------------------------------------------------------------------

def deploy_workflows(path: Path, tenant_id: str) -> list[str]:
    """Deploys workflows/*.bpmn to Flowable under the tenant id. Unchanged files are not deployed again."""
    files = sorted((path / "workflows").glob("*.bpmn"))
    if not files:
        return ["no workflows in the pack"]
    base = os.environ.get("FLOWABLE_URL", "http://flowable:8080/flowable-rest/service")
    auth = ("rest-admin", os.environ.get("FLOWABLE_PASSWORD", ""))
    for _ in range(60):  # Flowable can still be starting during `make up`
        try:
            requests.get(f"{base}/repository/deployments", auth=auth, timeout=5).raise_for_status()
            break
        except requests.RequestException:
            time.sleep(3)
    lines = []
    for file in files:
        content = file.read_bytes()
        name = f"{file.stem}@{hashlib.sha256(content).hexdigest()[:12]}"
        found = requests.get(f"{base}/repository/deployments", auth=auth, timeout=15,
                             params={"tenantId": tenant_id, "name": name}).json().get("data", [])
        if found:
            lines.append(f"{file.name}: unchanged ({name})")
            continue
        response = requests.post(f"{base}/repository/deployments", auth=auth, timeout=30,
                                 data={"tenantId": tenant_id, "deploymentName": name},
                                 files={"file": (file.name, content, "text/xml")})
        if response.status_code >= 400:
            raise Failed(f"deploying {file.name}: {response.status_code} {response.text[:300]}")
        lines.append(f"{file.name}: deployed ({name})")
    return lines


# --- Commands -----------------------------------------------------------------------------------

async def create(path: Path) -> None:
    started = time.perf_counter()
    pack = load_pack(path)
    tenant = pack["tenant.yaml"]
    tenant_id = tenant["id"]
    print(f"Onboarding {tenant['name']} ({tenant_id})")
    say("validate", f"{len(PACK_FILES)} files match their JSON Schemas")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO core.tenant (id, name) VALUES ($1, $2) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()", tenant_id, tenant["name"])
            facilities = pack["emission-sources.yaml"]["facilities"]
            for f in facilities:
                await conn.execute(
                    "INSERT INTO core.facility (tenant_id, code, name, kind, province) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (tenant_id, code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind, "
                    "province = EXCLUDED.province", tenant_id, f["code"], f["name"], f["kind"], f.get("province"))
    finally:
        await conn.close()
    say("registry", f"tenant registered, {len(facilities)} facilities")

    kc = Keycloak()
    kc.ensure_roles()
    group_id = kc.ensure_group(tenant_id, tenant["name"])
    say("identity", f"group tenant-{tenant_id}, roles {', '.join(ROLES)}")
    for user in pack["org.yaml"]["users"]:
        note = kc.ensure_user(tenant_id, group_id, user)
        say("user", f"{user['username']} [{', '.join(user['roles'])}]: {note}")

    say("storage", ensure_bucket(tenant_id))
    for line in deploy_workflows(path, tenant_id):
        say("workflow", line)
    print(f"Done in {time.perf_counter() - started:.1f} s. Users can log in at the portal now.")


async def set_status(tenant_id: str, enabled: bool) -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.execute("UPDATE core.tenant SET status = $2, updated_at = now() WHERE id = $1",
                                    tenant_id, "active" if enabled else "disabled")
    finally:
        await conn.close()
    if result.endswith(" 0"):
        raise Failed(f"unknown tenant {tenant_id}")
    count = Keycloak().set_enabled(tenant_id, enabled)
    print(f"{tenant_id}: {'enabled' if enabled else 'disabled'}; {count} users {'enabled' if enabled else 'disabled and logged out'}")


async def list_tenants() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("SELECT t.id, t.name, t.status, t.created_at, "
                                "(SELECT count(*) FROM core.facility f WHERE f.tenant_id = t.id) AS facilities "
                                "FROM core.tenant t ORDER BY t.created_at")
    finally:
        await conn.close()
    kc = Keycloak()
    print(f"{'TENANT':<24} {'STATUS':<9} {'USERS':>5} {'FACILITIES':>10}  NAME")
    for r in rows:
        print(f"{r['id']:<24} {r['status']:<9} {kc.member_count(r['id']):>5} {r['facilities']:>10}  {r['name']}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="dxctl", description="Manage EcoTrace tenants from config packs.")
    sub = parser.add_subparsers(dest="noun", required=True)
    tenant = sub.add_parser("tenant").add_subparsers(dest="verb", required=True)
    for verb in ("validate", "create"):
        tenant.add_parser(verb).add_argument("pack", type=Path)
    for verb in ("disable", "enable"):
        tenant.add_parser(verb).add_argument("tenant_id")
    tenant.add_parser("list")
    args = parser.parse_args()
    try:
        if args.verb == "validate":
            pack = load_pack(args.pack)
            print(f"{pack['tenant.yaml']['id']}: config pack is valid ({len(PACK_FILES)} files)")
        elif args.verb == "create":
            asyncio.run(create(args.pack))
        elif args.verb in ("disable", "enable"):
            asyncio.run(set_status(args.tenant_id, args.verb == "enable"))
        else:
            asyncio.run(list_tenants())
    except Failed as exc:
        print(f"dxctl: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
