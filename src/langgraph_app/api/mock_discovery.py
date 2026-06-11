"""Temporary mock discovery API for exercising the application-discovery skill.

Replace these endpoints with your real platform URLs in SKILL.md when ready.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query

_AA_CODE_PATTERN = re.compile(r"^AA\d{5}$")
_MOCK_BEARER_TOKEN = "1234"


def _require_mock_bearer(authorization: str | None = Header(default=None)) -> None:
    """Require ``Authorization: Bearer 1234`` on mock discovery routes."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != _MOCK_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token.")


router = APIRouter(
    prefix="/mock/discovery",
    tags=["mock-discovery"],
    dependencies=[Depends(_require_mock_bearer)],
)

_MOCK_SERVERS: dict[str, list[dict[str, str]]] = {
    "default": [
        {
            "id": "1",
            "hostname": "app-server-01",
            "environment": "Prod",
            "datacenter": "DC-East",
        },
        {
            "id": "2",
            "hostname": "app-server-02",
            "environment": "QA",
            "datacenter": "DC-West",
        },
    ],
}

_MOCK_APPLICATIONS: dict[str, list[dict[str, str]]] = {
    "1": [
        {"id": "101", "name": "Customer Portal", "runtime": "Java 17"},
        {"id": "102", "name": "Billing Service", "runtime": "Node.js 20"},
    ],
    "2": [
        {"id": "201", "name": "Reporting API", "runtime": "Python 3.11"},
    ],
}


def _validate_aa_code(aa_code: str) -> str:
    normalised = aa_code.strip().upper()
    if not _AA_CODE_PATTERN.match(normalised):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid AA number '{aa_code}'. Expected format AA##### (e.g. AA12345).",
        )
    return normalised


@router.get("/{aa_code}/servers")
def list_servers(
    aa_code: str,
    aa_code_query: str | None = Query(default=None, alias="aa_code"),
) -> dict:
    """Return mock servers discovered for an AA number."""
    normalised = _validate_aa_code(aa_code)
    if aa_code_query and aa_code_query.strip().upper() != normalised:
        raise HTTPException(
            status_code=400,
            detail="Path aa_code and query param aa_code must match.",
        )
    return {
        "aa_code": normalised,
        "servers": _MOCK_SERVERS["default"],
    }


@router.get("/{aa_code}/servers/{server_id}/applications")
def list_applications(
    aa_code: str,
    server_id: str,
    aa_code_query: str | None = Query(default=None, alias="aa_code"),
) -> dict:
    """Return mock applications running on a server for an AA number."""
    normalised = _validate_aa_code(aa_code)
    if aa_code_query and aa_code_query.strip().upper() != normalised:
        raise HTTPException(
            status_code=400,
            detail="Path aa_code and query param aa_code must match.",
        )
    applications = _MOCK_APPLICATIONS.get(server_id)
    if applications is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found.")
    return {
        "aa_code": normalised,
        "server_id": server_id,
        "applications": applications,
    }
