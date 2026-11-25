"""HY4-C: read-only local catalog endpoints."""

from fastapi import APIRouter

from app.catalog.loader import load_courses, load_roles
from app.schemas.catalog import CourseRead, RoleTemplateRead

router = APIRouter()


@router.get("/roles", response_model=list[RoleTemplateRead])
async def get_roles() -> list[RoleTemplateRead]:
    return [RoleTemplateRead(**row) for row in load_roles()]


@router.get("/courses", response_model=list[CourseRead])
async def get_courses() -> list[CourseRead]:
    return [CourseRead(**row) for row in load_courses()]
