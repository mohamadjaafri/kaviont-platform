"""Read-only cloud inventory and month-to-date cost connectors.

Credentials are read from the process environment or standard provider credential
chains. Values and tokens are never included in returned payloads or audit logs.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _empty(status: str = "not_configured", message: str = "Connector is not configured.") -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "resource_count": 0,
        "resources": [],
        "inventory_scope": "read-only",
        "cost": {"status": "not_configured", "timeframe": "month_to_date"},
    }


def _azure_token() -> str:
    token = os.getenv("AZURE_ACCESS_TOKEN", "").strip()
    if token:
        return token
    tenant = os.getenv("AZURE_TENANT_ID", "").strip()
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    secret = os.getenv("AZURE_CLIENT_SECRET", "").strip()
    if not (tenant and client_id and secret):
        return ""
    response = httpx.post(
        f"https://login.microsoftonline.com/{quote(tenant, safe='')}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": secret,
            "scope": "https://management.azure.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return str(response.json().get("access_token") or "")


def _azure_inventory() -> dict[str, Any]:
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    if not subscription:
        return _empty()
    try:
        token = _azure_token()
        if not token:
            return _empty(message="Set an Azure read-only service principal or AZURE_ACCESS_TOKEN.")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = (
            f"https://management.azure.com/subscriptions/{quote(subscription, safe='')}"
            "/resources?api-version=2021-04-01&$expand=provisioningState"
        )
        resources: list[dict[str, Any]] = []
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=False) as client:
            pages = 0
            while url and pages < 20:
                response = client.get(url, headers=headers)
                if response.status_code in {401, 403}:
                    return _empty("unauthorized", f"Azure Resource Manager returned HTTP {response.status_code}.")
                response.raise_for_status()
                payload = response.json()
                for item in payload.get("value", []):
                    resource_id = str(item.get("id") or "")
                    resource_group = None
                    match = re.search(r"/resourceGroups/([^/]+)", resource_id, re.IGNORECASE)
                    if match:
                        resource_group = match.group(1)
                    resources.append({
                        "id": resource_id,
                        "name": item.get("name"),
                        "type": item.get("type"),
                        "location": item.get("location"),
                        "resource_group": resource_group,
                        "provisioning_state": (item.get("properties") or {}).get("provisioningState"),
                    })
                url = payload.get("nextLink")
                pages += 1

        cost: dict[str, Any] = {"status": "unavailable", "timeframe": "month_to_date"}
        cost_url = (
            f"https://management.azure.com/subscriptions/{quote(subscription, safe='')}"
            "/providers/Microsoft.CostManagement/query?api-version=2025-03-01"
        )
        cost_body = {
            "type": "Usage",
            "timeframe": "MonthToDate",
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                "grouping": [{"type": "Dimension", "name": "ResourceGroupName"}],
            },
        }
        try:
            cost_response = httpx.post(cost_url, headers=headers, json=cost_body, timeout=_TIMEOUT)
            if cost_response.status_code == 200:
                properties = cost_response.json().get("properties", {})
                columns = [column.get("name") for column in properties.get("columns", [])]
                rows = [dict(zip(columns, row)) for row in properties.get("rows", [])]
                cost_total = sum(float(row.get("PreTaxCost") or 0) for row in rows)
                currency = next((row.get("Currency") for row in rows if row.get("Currency")), None)
                cost = {"status": "available", "amount": cost_total, "currency": currency, "timeframe": "month_to_date"}
            elif cost_response.status_code in {401, 403}:
                cost = {"status": "unauthorized", "timeframe": "month_to_date"}
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        return {
            "status": "connected",
            "message": "Azure Resource Manager inventory is read-only.",
            "resource_count": len(resources),
            "resources": resources,
            "inventory_scope": "subscription",
            "cost": cost,
        }
    except (httpx.HTTPError, ValueError, KeyError):
        return _empty("unavailable", "Azure inventory request failed. Check the service-principal permissions and subscription.")


def _aws_inventory() -> dict[str, Any]:
    if not any(os.getenv(key, "").strip() for key in (
        "AWS_ACCESS_KEY_ID", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_PROFILE", "AWS_ROLE_ARN", "AWS_SHARED_CREDENTIALS_FILE"
    )):
        return _empty(message="Configure temporary AWS credentials or a workload identity.")
    try:
        import boto3  # type: ignore[import-not-found]

        session = boto3.Session()
        if not session.get_credentials():
            return _empty("unauthorized", "No AWS credentials were resolved.")
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        tagging = session.client("resourcegroupstaggingapi", region_name=region)
        resources: list[dict[str, Any]] = []
        page_token = None
        pages = 0
        while pages < 20:
            args: dict[str, Any] = {"ResourcesPerPage": 100}
            if page_token:
                args["PaginationToken"] = page_token
            page = tagging.get_resources(**args)
            for item in page.get("ResourceTagMappingList", []):
                arn = item.get("ResourceARN")
                resources.append({
                    "id": arn,
                    "name": str(arn).split("/")[-1] if arn else None,
                    "type": str(arn).split(":")[2] if arn and arn.startswith("arn:") else "unknown",
                    "tags": {tag.get("Key"): tag.get("Value") for tag in item.get("Tags", [])},
                })
            page_token = page.get("PaginationToken")
            pages += 1
            if not page_token:
                break
        cost: dict[str, Any] = {"status": "unavailable", "timeframe": "month_to_date"}
        try:
            today = date.today()
            ce = session.client("ce", region_name="us-east-1")
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": today.replace(day=1).isoformat(),
                    "End": (today + timedelta(days=1)).isoformat(),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
            groups = response.get("ResultsByTime", [{}])[0].get("Groups", [])
            total = sum(float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)) for group in groups)
            currency = next((
                group.get("Metrics", {}).get("UnblendedCost", {}).get("Unit")
                for group in groups
                if group.get("Metrics", {}).get("UnblendedCost", {}).get("Unit")
            ), None)
            cost = {"status": "available", "amount": total, "currency": currency, "timeframe": "month_to_date"}
        except Exception:
            cost = {"status": "unauthorized_or_unavailable", "timeframe": "month_to_date"}
        return {
            "status": "connected",
            "message": "AWS inventory uses the Resource Groups Tagging API and therefore returns tagged resources only.",
            "resource_count": len(resources),
            "resources": resources,
            "inventory_scope": "tagged_resources",
            "cost": cost,
        }
    except ImportError:
        return _empty("unavailable", "Install the optional boto3 dependency to enable AWS inventory.")
    except Exception:
        return _empty("unavailable", "AWS inventory request failed. Check read-only IAM permissions and region settings.")


def _gcp_inventory() -> dict[str, Any]:
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "").strip()
    if not project and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return _empty(message="Configure Application Default Credentials and a Google Cloud project.")
    try:
        import google.auth  # type: ignore[import-not-found]
        from google.auth.transport.requests import Request as GoogleRequest  # type: ignore[import-not-found]

        credentials, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(GoogleRequest())
        project = project or detected_project or ""
        if not project:
            return _empty("not_configured", "Set GOOGLE_CLOUD_PROJECT for Cloud Asset Inventory.")
        headers = {"Authorization": f"Bearer {credentials.token}", "Accept": "application/json"}
        base_url = f"https://cloudasset.googleapis.com/v1/projects/{quote(project, safe='')}/assets"
        params: dict[str, Any] = {"contentType": "RESOURCE", "pageSize": 100}
        resources: list[dict[str, Any]] = []
        page_token = ""
        with httpx.Client(timeout=_TIMEOUT) as client:
            pages = 0
            while pages < 20:
                if page_token:
                    params["pageToken"] = page_token
                response = client.get(base_url, headers=headers, params=params)
                if response.status_code in {401, 403}:
                    return _empty("unauthorized", f"Cloud Asset Inventory returned HTTP {response.status_code}.")
                response.raise_for_status()
                payload = response.json()
                for item in payload.get("assets", []):
                    resource = item.get("resource") or {}
                    data = resource.get("data") or {}
                    resources.append({
                        "id": item.get("name"),
                        "name": data.get("name") or str(item.get("name", "")).split("/")[-1],
                        "type": item.get("assetType"),
                        "location": data.get("location"),
                    })
                page_token = payload.get("nextPageToken") or ""
                pages += 1
                if not page_token:
                    break
        cost: dict[str, Any] = {"status": "not_configured", "timeframe": "month_to_date"}
        table = os.getenv("GCP_BILLING_EXPORT_TABLE", "").strip()
        billing_project = os.getenv("GCP_BILLING_PROJECT_ID", project).strip()
        if table and re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+", table):
            query_url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{quote(billing_project, safe='')}/queries"
            backtick = chr(96)
            query = (
                "SELECT currency, SUM(cost) AS total_cost "
                f"FROM {backtick}{table}{backtick} "
                "WHERE usage_start_time >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH) "
                "GROUP BY currency ORDER BY total_cost DESC LIMIT 10"
            )
            try:
                query_response = httpx.post(
                    query_url,
                    headers=headers,
                    json={"query": query, "useLegacySql": False, "timeoutMs": 20000},
                    timeout=_TIMEOUT,
                )
                if query_response.status_code == 200:
                    result = query_response.json()
                    rows = result.get("rows", [])
                    fields = (result.get("schema") or {}).get("fields", [])
                    names = [field.get("name") for field in fields]
                    values = [
                        {name: cell.get("v") for name, cell in zip(names, row.get("f", []))}
                        for row in rows
                    ]
                    cost = {
                        "status": "available" if result.get("jobComplete") and values else "pending_or_empty",
                        "rows": values,
                        "timeframe": "month_to_date",
                        "source": "BigQuery billing export",
                    }
                elif query_response.status_code in {401, 403}:
                    cost = {"status": "unauthorized", "timeframe": "month_to_date"}
            except (httpx.HTTPError, ValueError):
                cost = {"status": "unavailable", "timeframe": "month_to_date"}
        return {
            "status": "connected",
            "message": "Google Cloud Asset Inventory is read-only. Cost data requires a configured BigQuery billing export.",
            "resource_count": len(resources),
            "resources": resources,
            "inventory_scope": "project",
            "cost": cost,
        }
    except ImportError:
        return _empty("unavailable", "Install google-auth to enable Google Cloud inventory.")
    except Exception:
        return _empty("unavailable", "Google Cloud inventory request failed. Check Cloud Asset API and IAM permissions.")


def get_cloud_inventory() -> dict[str, dict[str, Any]]:
    """Return independent provider results; one unavailable provider never hides others."""

    return {
        "azure": _azure_inventory(),
        "aws": _aws_inventory(),
        "gcp": _gcp_inventory(),
    }
