import httpx
import pytest
import respx

from app.core.errors import (
    InvalidCredentialsError,
    SiiBadResponseError,
    SiiUnauthorizedError,
    SiiUnavailableError,
)
from app.integration.sii.client import SiiClient, build_http_client
from tests.conftest import load_fixture, make_jwt

BASE = "https://sii.example.test/api"


@pytest.fixture
async def sii():
    http = build_http_client(BASE, 2)
    yield SiiClient(http)
    await http.aclose()


@respx.mock
async def test_login_returns_token(sii):
    token = make_jwt()
    route = respx.post(f"{BASE}/login").respond(
        200,
        json={"responseCodeTxt": "200 OK", "message": {"login": {"token": token}}, "status": 200, "flag": "success"},
    )
    assert await sii.login("a@celaya.tecnm.mx", "x") == token
    assert route.called
    assert route.calls[0].request.url.path == "/api/login"


@respx.mock
@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"message": "Credenciales incorrectas", "flag": "error"}),
        (200, {"message": "Usuario o contraseña incorrectos", "flag": "error"}),
        (422, {"errors": {"email": ["required"]}}),
    ],
)
async def test_login_rejects_bad_credentials(sii, status, body):
    respx.post(f"{BASE}/login").respond(status, json=body)
    with pytest.raises(InvalidCredentialsError):
        await sii.login("a@celaya.tecnm.mx", "wrong")


@respx.mock
async def test_login_timeout_means_unavailable(sii):
    respx.post(f"{BASE}/login").mock(side_effect=httpx.ConnectTimeout("boom"))
    with pytest.raises(SiiUnavailableError):
        await sii.login("a@celaya.tecnm.mx", "x")


@respx.mock
async def test_login_server_error_means_unavailable(sii):
    respx.post(f"{BASE}/login").respond(502, text="Bad gateway")
    with pytest.raises(SiiUnavailableError):
        await sii.login("a@celaya.tecnm.mx", "x")


@respx.mock
async def test_profile_is_mapped_and_sends_bearer(sii):
    route = respx.get(f"{BASE}/movil/estudiante").respond(200, json=load_fixture("estudiante.json"))
    profile = await sii.get_profile("tok")
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok"
    assert profile.numero_control == "23031035"
    assert profile.credits_accumulated == 203
    assert profile.progress_in_progress_pct == 45
    assert profile.photo_data_url.startswith("data:image/jpeg;base64,/9j/")
    assert "\n" not in profile.photo_data_url


@respx.mock
async def test_unauthorized_token(sii):
    respx.get(f"{BASE}/movil/estudiante/kardex").respond(401, json={"message": "Token expirado"})
    with pytest.raises(SiiUnauthorizedError):
        await sii.get_kardex("expired")


@respx.mock
async def test_flag_false_with_token_message_is_unauthorized(sii):
    respx.get(f"{BASE}/movil/estudiante/kardex").respond(200, json={"flag": False, "message": "Token inválido"})
    with pytest.raises(SiiUnauthorizedError):
        await sii.get_kardex("expired")


@respx.mock
async def test_flag_false_is_bad_response(sii):
    respx.get(f"{BASE}/movil/estudiante/kardex").respond(200, json={"flag": False, "message": "Error"})
    with pytest.raises(SiiBadResponseError):
        await sii.get_kardex("tok")


@respx.mock
async def test_grades_handles_the_calificaiones_typo(sii):
    respx.get(f"{BASE}/movil/estudiante/calificaciones").respond(200, json=load_fixture("calificaciones.json"))
    periods = await sii.get_grades("tok")
    assert periods[0].term_code == "26/2"
    course = next(c for c in periods[0].courses if c.clave == "IDD-2503")
    assert [p.grade for p in course.partials] == [75, 75, None, None]


@respx.mock
async def test_schedule_parses_days(sii):
    respx.get(f"{BASE}/movil/estudiante/horarios").respond(200, json=load_fixture("horarios.json"))
    periods = await sii.get_schedule("tok")
    cyber = next(c for c in periods[0].courses if c.clave == "IDD-2502")
    assert [(s.day, s.start, s.end, s.room) for s in cyber.sessions] == [
        ("lunes", "12:00", "13:00", "LRC"),
        ("martes", "11:00", "13:00", "LRC"),
        ("jueves", "11:00", "13:00", "LRC"),
    ]


@respx.mock
async def test_kardex_accepts_ac_grades(sii):
    respx.get(f"{BASE}/movil/estudiante/kardex").respond(200, json=load_fixture("kardex.json"))
    kardex = await sii.get_kardex("tok")
    act = next(e for e in kardex.entries if e.clave == "ACT-0000")
    assert act.grade is None and act.grade_label == "AC"
    assert len(kardex.entries) == 44
