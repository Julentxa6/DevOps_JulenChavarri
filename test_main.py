import pytest
from fastapi.testclient import TestClient

from main import app, state

client = TestClient(app)


def setup_function() -> None:
    state["current_sequence"] = []
    state["failed_attempts"] = 0
    state["logs"] = []


def test_healthz_endpoint() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_endpoint_structure() -> None:
    response = client.get("/status")
    assert response.status_code == 200
    payload = response.json()

    assert set(payload.keys()) == {"sensors", "peripherals", "logs"}
    assert isinstance(payload["sensors"], dict)
    assert "temperature_c" in payload["sensors"]
    assert "luminosity_lux" in payload["sensors"]

    assert isinstance(payload["peripherals"], dict)
    assert set(payload["peripherals"].keys()) == {"leds", "buttons"}
    assert isinstance(payload["peripherals"]["leds"], dict)
    assert isinstance(payload["peripherals"]["buttons"], dict)

    assert isinstance(payload["logs"], list)


def test_access_attempt_sequence_granted() -> None:
    response1 = client.post("/access/attempt", json={"button_id": 1})
    assert response1.status_code == 200
    assert response1.json()["status"] == "pending"

    response2 = client.post("/access/attempt", json={"button_id": 2})
    assert response2.status_code == 200
    assert response2.json()["status"] == "pending"

    response3 = client.post("/access/attempt", json={"button_id": 1})
    assert response3.status_code == 200
    assert response3.json()["status"] == "granted"

    status_response = client.get("/status")
    assert status_response.status_code == 200
    logs = status_response.json()["logs"]
    assert any(entry["result"] == "ACCESO CONCEDIDO" for entry in logs)


def test_access_attempt_invalid_button() -> None:
    response = client.post("/access/attempt", json={"button_id": 99})
    assert response.status_code == 400
