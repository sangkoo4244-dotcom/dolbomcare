import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import center_directory
from app.database import Base, get_db


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="돌봄케어 강남점", address="서울시 강남구", phone="02-1111-1111", is_public_listed=True))
    db.add(models.Center(id=2, name="돌봄케어 부산점", address="부산시 해운대구", phone="051-2222-2222", is_public_listed=True))
    db.add(models.Center(id=3, name="테스트센터", address="서울시 비공개구", phone="02-3333-3333", is_public_listed=False))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(center_directory.router, prefix="/api/v1/centers")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_directory_requires_no_login(client):
    res = client.get("/api/v1/centers/directory")
    assert res.status_code == 200


def test_directory_only_lists_opted_in_centers(client):
    res = client.get("/api/v1/centers/directory")
    names = {c["name"] for c in res.json()["centers"]}
    assert names == {"돌봄케어 강남점", "돌봄케어 부산점"}


def test_directory_hides_operational_fields(client):
    res = client.get("/api/v1/centers/directory")
    center = res.json()["centers"][0]
    assert set(center.keys()) == {"id", "name", "address", "phone", "logo_image"}


def test_directory_search_by_name(client):
    res = client.get("/api/v1/centers/directory?q=강남")
    names = {c["name"] for c in res.json()["centers"]}
    assert names == {"돌봄케어 강남점"}


def test_directory_search_by_address(client):
    res = client.get("/api/v1/centers/directory?q=해운대")
    names = {c["name"] for c in res.json()["centers"]}
    assert names == {"돌봄케어 부산점"}


def test_directory_search_excludes_private_center_even_if_name_matches(client):
    res = client.get("/api/v1/centers/directory?q=테스트센터")
    assert res.json()["centers"] == []
