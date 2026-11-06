from __future__ import annotations

import base64
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from app.application.models import Curriculum, CurriculumRules, Requisite, Subject
from app.application.whatif.engine.graph import CurriculumGraph
from app.application.whatif.engine.state import StudentState, build_student_state
from app.core.config import Settings
from app.core.errors import InvalidCredentialsError, SiiUnauthorizedError
from app.data.db import create_engine, create_sessionmaker
from app.data.orm import Base
from app.data.seed.seed import load_seed, seed_database
from app.integration.sii import mappers
from app.integration.sii.raw_schemas import RawGradesPeriod, RawKardex, RawProfile, RawSchedulePeriod
from app.interaction.dependencies import get_db, get_sii_gateway, settings_dep
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
TEST_PASSWORD = "test-password"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_jwt(exp: int | None = None, sub: int = 126310) -> str:
    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    exp = exp or int(time.time()) + 3600
    return f"{b64({'typ': 'JWT', 'alg': 'HS256'})}.{b64({'sub': sub, 'iat': exp - 3600, 'exp': exp})}.sig"


def curriculum_from_seed() -> Curriculum:
    data = load_seed()
    return Curriculum(
        id=1,
        total_credits=data["curriculum"]["total_credits"],
        code=data["curriculum"]["code"],
        specialty_code=data["curriculum"]["specialty_code"],
        name=data["curriculum"]["name"],
        subjects=[Subject(**s) for s in data["subjects"]],
        requisites=[
            Requisite(subject_clave=r["subject"], requires_clave=r["requires"], type=r["type"])
            for r in data["requisites"]
        ],
        rules=CurriculumRules(**data["rules"]),
    )


@pytest.fixture
def curriculum() -> Curriculum:
    return curriculum_from_seed()


@pytest.fixture
def graph(curriculum: Curriculum) -> CurriculumGraph:
    return CurriculumGraph.from_curriculum(curriculum)


@pytest.fixture
def kardex():
    return mappers.to_kardex(RawKardex.model_validate(load_fixture("kardex.json")["data"]))


@pytest.fixture
def periods():
    return mappers.to_grades(
        [RawGradesPeriod.model_validate(p) for p in load_fixture("calificaciones.json")["data"]]
    )


@pytest.fixture
def state(graph, kardex, periods) -> StudentState:
    return build_student_state(graph, kardex, periods)


class FakeSii:
    """In-memory SII built from the real responses captured in tests/fixtures."""

    def __init__(self) -> None:
        self.token = make_jwt()
        self.valid_tokens = {self.token}

    async def login(self, email: str, password: str) -> str:
        if password != TEST_PASSWORD:
            raise InvalidCredentialsError()
        return self.token

    def _check(self, token: str) -> None:
        if token not in self.valid_tokens:
            raise SiiUnauthorizedError()

    async def get_profile(self, token: str):
        self._check(token)
        return mappers.to_profile(RawProfile.model_validate(load_fixture("estudiante.json")["data"]))

    async def get_kardex(self, token: str):
        self._check(token)
        return mappers.to_kardex(RawKardex.model_validate(load_fixture("kardex.json")["data"]))

    async def get_grades(self, token: str):
        self._check(token)
        return mappers.to_grades(
            [RawGradesPeriod.model_validate(p) for p in load_fixture("calificaciones.json")["data"]]
        )

    async def get_schedule(self, token: str):
        self._check(token)
        return mappers.to_schedule(
            [RawSchedulePeriod.model_validate(p) for p in load_fixture("horarios.json")["data"]]
        )


@pytest.fixture
def fake_sii() -> FakeSii:
    return FakeSii()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        admin_control_numbers=["23031035"],
        session_ttl_minutes=30,
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
async def client(settings: Settings, fake_sii: FakeSii) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as db:
        await seed_database(db)

    async def override_db():
        async with sessionmaker() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_sii_gateway] = lambda: fake_sii
    app.dependency_overrides[settings_dep] = lambda: settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await engine.dispose()


async def login(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "l23031035@celaya.tecnm.mx", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]
