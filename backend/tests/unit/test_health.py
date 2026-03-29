"""Unit tests for the health check endpoint."""

import pytest
from fastapi.testclient import TestClient

from ...main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "mortgage-intelligence"
