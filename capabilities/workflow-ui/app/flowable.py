"""Minimal client for the Flowable REST API. Every call is scoped to one Flowable tenant id (= EcoTrace tenant)."""

from __future__ import annotations

import os

import requests

BASE = os.environ.get("FLOWABLE_URL", "http://flowable:8080/flowable-rest/service")
_session = requests.Session()
_session.auth = (os.environ.get("FLOWABLE_USER", "rest-admin"), os.environ.get("FLOWABLE_PASSWORD", ""))


class FlowableError(Exception):
    pass


def _call(method: str, path: str, **kwargs):
    response = _session.request(method, BASE + path, timeout=20, **kwargs)
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise FlowableError(f"Flowable {method} {path}: {response.status_code} {response.text[:300]}")
    return response.json() if response.content else {}


def _vars(values: dict) -> list[dict]:
    return [{"name": k, "value": v} for k, v in values.items()]


def active_instance(tenant_id: str, process_key: str, business_key: str) -> dict | None:
    found = _call("GET", "/runtime/process-instances", params={
        "tenantId": tenant_id, "processDefinitionKey": process_key, "businessKey": business_key})
    return (found or {}).get("data", [None])[0] if found and found.get("data") else None


def start(tenant_id: str, process_key: str, business_key: str, variables: dict) -> dict:
    return _call("POST", "/runtime/process-instances", json={
        "processDefinitionKey": process_key, "businessKey": business_key, "tenantId": tenant_id,
        "returnVariables": False, "variables": _vars(variables)})


def has_definition(tenant_id: str, process_key: str) -> bool:
    found = _call("GET", "/repository/process-definitions", params={"tenantId": tenant_id, "key": process_key, "latest": "true"})
    return bool(found and found.get("data"))


def tasks(tenant_id: str, groups: list[str]) -> list[dict]:
    if not groups:
        return []
    found = _call("POST", "/query/tasks", json={"tenantId": tenant_id, "candidateGroupIn": groups,
                                                  "includeProcessVariables": True, "size": 100, "sort": "createTime"})
    return found.get("data", []) if found else []


def task(task_id: str) -> dict | None:
    return _call("GET", f"/runtime/tasks/{task_id}")


def candidate_groups(task_id: str) -> set[str]:
    links = _call("GET", f"/runtime/tasks/{task_id}/identitylinks") or []
    return {link["group"] for link in links if link.get("group") and link.get("type") == "candidate"}


def process_variables(instance_id: str) -> dict:
    found = _call("GET", f"/runtime/process-instances/{instance_id}/variables") or []
    return {v["name"]: v.get("value") for v in found}


def complete(task_id: str, variables: dict) -> None:
    _call("POST", f"/runtime/tasks/{task_id}", json={"action": "complete", "variables": _vars(variables)})


def instance_running(instance_id: str) -> bool:
    return _call("GET", f"/runtime/process-instances/{instance_id}") is not None


def history_variables(instance_id: str) -> dict:
    found = _call("GET", "/history/historic-variable-instances", params={"processInstanceId": instance_id, "size": 100})
    return {v["variable"]["name"]: v["variable"].get("value") for v in (found or {}).get("data", [])}
