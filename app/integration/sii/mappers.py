"""Translate raw SII payloads into application domain models."""

from __future__ import annotations

import re

from app.application.models import (
    ClassSession,
    CourseGrades,
    GradesPeriod,
    Kardex,
    KardexEntry,
    PartialGrade,
    ScheduledCourse,
    SchedulePeriod,
    StudentProfile,
    parse_grade,
)
from app.integration.sii.raw_schemas import (
    RawGradesPeriod,
    RawKardex,
    RawProfile,
    RawSchedulePeriod,
)

DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado")
_TIME_RANGE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def _photo_data_url(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = "".join(raw.split())
    if cleaned.startswith("data:"):
        return cleaned
    return f"data:image/jpeg;base64,{cleaned}"


def to_profile(raw: RawProfile) -> StudentProfile:
    return StudentProfile(
        numero_control=raw.numero_control.strip(),
        full_name=" ".join(raw.persona.split()),
        email=raw.email.strip(),
        semester=raw.semestre,
        credits_accumulated=raw.creditos_acumulados,
        weighted_average=round(raw.promedio_ponderado, 2),
        arithmetic_average=round(raw.promedio_aritmetico, 2),
        subjects_taken=raw.materias_cursadas,
        subjects_approved=raw.materias_aprobadas,
        subjects_failed=raw.materias_reprobadas,
        subjects_failed_not_accredited=raw.num_mat_rep_no_acreditadas or 0,
        complementary_credits=raw.creditos_complementarios,
        progress_pct=raw.porcentaje_avance,
        progress_in_progress_pct=raw.porcentaje_avance_cursando,
        photo_data_url=_photo_data_url(raw.foto),
    )


def to_kardex(raw: RawKardex) -> Kardex:
    entries = []
    for item in raw.kardex:
        numeric, label = parse_grade(item.calificacion)
        entries.append(
            KardexEntry(
                clave=item.clave_materia.strip().upper(),
                name=item.nombre_materia.strip(),
                term_code=item.periodo.strip().upper(),
                credits=item.creditos,
                grade=numeric,
                grade_label=label,
                description=item.descripcion.strip(),
                semester=item.semestre,
            )
        )
    return Kardex(progress_pct=raw.porcentaje_avance, entries=entries)


def to_grades(raw_periods: list[RawGradesPeriod]) -> list[GradesPeriod]:
    periods = []
    for raw in raw_periods:
        courses = []
        for item in raw.materias:
            partials = [
                PartialGrade(number=p.numero_calificacion, grade=parse_grade(p.calificacion)[0])
                for p in sorted(item.calificaciones, key=lambda p: p.numero_calificacion)
            ]
            courses.append(
                CourseGrades(
                    group_id=item.materia.id_grupo,
                    clave=item.materia.clave_materia.strip().upper(),
                    name=item.materia.nombre_materia.strip(),
                    group_letter=item.materia.letra_grupo,
                    partials=partials,
                )
            )
        periods.append(
            GradesPeriod(
                term_code=raw.periodo.clave_periodo.strip().upper(),
                year=raw.periodo.anio,
                description=raw.periodo.descripcion_periodo,
                courses=courses,
            )
        )
    return periods


def parse_time_range(value: str | None) -> tuple[str, str] | None:
    """`"9:00-11:00"` → `("09:00", "11:00")`; anything unparseable → None."""
    if not value:
        return None
    match = _TIME_RANGE.match(value)
    if not match:
        return None
    h1, m1, h2, m2 = match.groups()
    return f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"


def to_schedule(raw_periods: list[RawSchedulePeriod]) -> list[SchedulePeriod]:
    periods = []
    for raw in raw_periods:
        courses = []
        for row in raw.horario:
            sessions = []
            for day in DAYS:
                parsed = parse_time_range(getattr(row, day))
                if parsed is None:
                    continue
                room = getattr(row, f"{day}_clave_salon")
                sessions.append(ClassSession(day=day, start=parsed[0], end=parsed[1], room=room))
            courses.append(
                ScheduledCourse(
                    group_id=row.id_grupo,
                    clave=row.clave_materia.strip().upper(),
                    name=row.nombre_materia.strip(),
                    group_letter=row.letra_grupo,
                    plan_name=row.nombre_plan,
                    sessions=sessions,
                )
            )
        periods.append(
            SchedulePeriod(
                term_code=raw.periodo.clave_periodo.strip().upper(),
                year=raw.periodo.anio,
                description=raw.periodo.descripcion_periodo,
                courses=courses,
            )
        )
    return periods
