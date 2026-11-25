"""HY4-C: local catalogs are validated, deterministic and network-free."""

from app.catalog.loader import load_courses, load_roles


def test_roles_are_valid_local_templates():
    roles = load_roles()
    assert len(roles) >= 5
    assert len({row["role_id"] for row in roles}) == len(roles)
    for row in roles:
        assert "本地教学模板" in row["source_note"]
        assert row["required_skills"]
        assert row["typical_tasks"]


def test_courses_are_valid_and_have_check_dates():
    courses = load_courses()
    assert 12 <= len(courses) <= 25
    assert len({row["course_id"] for row in courses}) == len(courses)
    known = {row["course_id"] for row in courses}
    for row in courses:
        assert row["url"].startswith(("https://", "http://"))
        assert row["last_checked_at"].startswith("20")
        assert row["estimated_hours"] > 0
        assert set(row["prerequisites"]) <= known
        assert row["verification"]


def test_courses_prefer_project_owned_materials():
    courses = load_courses()
    project = [row for row in courses if row["provider"] == "CareerLens"]
    assert len(project) >= len(courses) // 2


async def test_catalog_endpoints_are_read_only_and_open(client):
    roles = await client.get("/api/v1/catalog/roles")
    assert roles.status_code == 200
    assert roles.json()[0]["role_id"]
    courses = await client.get("/api/v1/catalog/courses")
    assert courses.status_code == 200
    assert courses.json()[0]["url"].startswith("https://")
