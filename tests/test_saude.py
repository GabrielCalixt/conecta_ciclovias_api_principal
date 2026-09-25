from fastapi import status
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_saude():

    response = client.get("/saude")
    assert response.status_code == status.HTTP_200_OK, (
        f"serviço com status {response.status_code}"
    )
    assert response.json() == {"status": "ok"}
