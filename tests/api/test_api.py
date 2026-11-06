from app.application.services.auth_service import jwt_expiry
from tests.conftest import TEST_PASSWORD, login, make_jwt


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- auth


async def test_login_returns_token_and_expiry(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "l23031035@celaya.tecnm.mx", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "bearer"
    assert body["student"]["numeroControl"] == "23031035"
    assert body["student"]["isAdmin"] is True
    assert body["expiresAt"]


async def test_login_bad_credentials(client):
    response = await client.post("/api/v1/auth/login", json={"email": "x@celaya.tecnm.mx", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_empty_fields(client):
    response = await client.post("/api/v1/auth/login", json={"email": "  ", "password": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_session_ttl_is_capped_at_30_minutes(client, fake_sii):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "l23031035@celaya.tecnm.mx", "password": TEST_PASSWORD}
    )
    from datetime import datetime

    expires = datetime.fromisoformat(response.json()["expiresAt"])
    token_exp = jwt_expiry(fake_sii.token)
    assert (token_exp - expires).total_seconds() > 25 * 60  # token lives 60 min, session 30


async def test_protected_routes_require_token(client):
    for path in ("/api/v1/students/me", "/api/v1/students/me/kardex", "/api/v1/whatif/analysis"):
        response = await client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_unknown_token_is_rejected(client):
    response = await client.get("/api/v1/students/me", headers=auth(make_jwt()))
    assert response.status_code == 401


async def test_expired_session(client, settings):
    settings.session_ttl_minutes = 0
    token = await login(client)
    response = await client.get("/api/v1/students/me", headers=auth(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


async def test_sii_rejection_expires_our_session(client, fake_sii):
    token = await login(client)
    fake_sii.valid_tokens.clear()
    first = await client.get("/api/v1/students/me", headers=auth(token))
    assert first.status_code == 401
    assert first.json()["error"]["code"] == "SESSION_EXPIRED"
    fake_sii.valid_tokens.add(token)
    second = await client.get("/api/v1/students/me", headers=auth(token))
    assert second.status_code == 401  # our session row was deleted


async def test_relogin_issues_a_new_working_token(client, fake_sii):
    old = await login(client)
    fake_sii.token = make_jwt(sub=999)
    fake_sii.valid_tokens = {fake_sii.token}
    new = await login(client)
    assert new != old
    assert (await client.get("/api/v1/students/me", headers=auth(new))).status_code == 200


# --------------------------------------------------------------------------- SII-backed views


async def test_profile(client):
    token = await login(client)
    body = (await client.get("/api/v1/students/me", headers=auth(token))).json()
    assert body["fullName"] == "ESTEBAN GONZALEZ CERVANTES"
    assert body["creditsAccumulated"] == 203
    assert body["photoDataUrl"].startswith("data:image/jpeg;base64,")


async def test_grades(client):
    token = await login(client)
    body = (await client.get("/api/v1/students/me/grades", headers=auth(token))).json()
    period = body["periods"][0]
    assert period["termLabel"] == "Ago–Dic 2026"
    mobile = next(c for c in period["courses"] if c["clave"] == "IDD-2503")
    assert mobile["average"] == 75 and mobile["level"] == "warning" and mobile["final"] is None


async def test_kardex(client):
    token = await login(client)
    body = (await client.get("/api/v1/students/me/kardex", headers=auth(token))).json()
    assert body["accreditedCredits"] == 203
    assert body["approvedCount"] == 44
    assert body["average"] == 92.21
    assert [s["semester"] for s in body["semesters"]] == [1, 2, 3, 4, 5, 6]


async def test_schedule(client):
    token = await login(client)
    body = (await client.get("/api/v1/students/me/schedule", headers=auth(token))).json()
    assert len(body["periods"][0]["courses"]) == 6


# --------------------------------------------------------------------------- what-if


async def test_analysis(client):
    token = await login(client)
    body = (await client.get("/api/v1/whatif/analysis", headers=auth(token))).json()
    assert body["projectedGraduationTerm"] == "27/2"
    assert body["deltaVsBaseline"] == 0
    assert len(body["nodes"]) == 54
    assert body["rules"]["maxCreditsPerTerm"] == 36


async def test_simulate_reports_delta(client):
    token = await login(client)
    response = await client.post(
        "/api/v1/whatif/simulate", headers=auth(token), json={"servicioSocial": "in_progress"}
    )
    assert response.status_code == 200
    assert response.json()["deltaVsBaseline"] == -1


async def test_simulate_rejects_unknown_subject(client):
    token = await login(client)
    response = await client.post(
        "/api/v1/whatif/simulate", headers=auth(token), json={"outcomes": {"XXX-0000": "fail"}}
    )
    assert response.status_code == 422


async def test_scenarios_crud(client):
    token = await login(client)
    created = await client.post(
        "/api/v1/whatif/scenarios",
        headers=auth(token),
        json={"name": "Reprobar móviles", "params": {"outcomes": {"IDD-2503": "fail"}}},
    )
    assert created.status_code == 201
    scenario = created.json()
    assert scenario["summary"]["projectedGraduationTerm"] == "27/2"

    listed = (await client.get("/api/v1/whatif/scenarios", headers=auth(token))).json()
    assert [s["id"] for s in listed] == [scenario["id"]]

    detail = (await client.get(f"/api/v1/whatif/scenarios/{scenario['id']}", headers=auth(token))).json()
    assert detail["scenario"]["params"]["outcomes"] == {"IDD-2503": "fail"}
    assert detail["result"]["projectedGraduationTerm"] == "27/2"

    updated = await client.put(
        f"/api/v1/whatif/scenarios/{scenario['id']}",
        headers=auth(token),
        json={"name": "Servicio social ya", "params": {"servicioSocial": "in_progress"}},
    )
    assert updated.json()["summary"]["deltaVsBaseline"] == -1

    deleted = await client.delete(f"/api/v1/whatif/scenarios/{scenario['id']}", headers=auth(token))
    assert deleted.status_code == 204
    missing = await client.get(f"/api/v1/whatif/scenarios/{scenario['id']}", headers=auth(token))
    assert missing.status_code == 404


# --------------------------------------------------------------------------- admin


async def test_admin_requires_allow_list(client, settings):
    settings.admin_control_numbers = []
    token = await login(client)
    response = await client.get("/api/v1/admin/subjects", headers=auth(token))
    assert response.status_code == 403


async def test_admin_subject_and_requisite_flow(client):
    token = await login(client)
    subjects = (await client.get("/api/v1/admin/subjects", headers=auth(token))).json()
    assert len(subjects) == 54

    created = await client.post(
        "/api/v1/admin/subjects",
        headers=auth(token),
        json={"clave": "OPT-0001", "name": "Optativa", "credits": 4, "suggestedSemester": 8, "gridRow": 1, "gridCol": 8},
    )
    assert created.status_code == 201

    req = await client.post(
        "/api/v1/admin/requisites",
        headers=auth(token),
        json={"subjectClave": "OPT-0001", "requiresClave": "SCG-1009", "type": "prereq"},
    )
    assert req.status_code == 201

    cycle = await client.post(
        "/api/v1/admin/requisites",
        headers=auth(token),
        json={"subjectClave": "AED-1285", "requiresClave": "OPT-0001", "type": "prereq"},
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "CYCLE_DETECTED"

    removed = await client.delete(f"/api/v1/admin/requisites/{req.json()['id']}", headers=auth(token))
    assert removed.status_code == 204
    assert (await client.delete("/api/v1/admin/subjects/OPT-0001", headers=auth(token))).status_code == 204


async def test_admin_rules_validation(client):
    token = await login(client)
    rules = (await client.get("/api/v1/admin/rules", headers=auth(token))).json()
    assert rules["maxCreditsPerTerm"] == 36
    bad = await client.put(
        "/api/v1/admin/rules",
        headers=auth(token),
        json={**rules, "minCreditsPerTerm": 40},
    )
    assert bad.status_code == 422
