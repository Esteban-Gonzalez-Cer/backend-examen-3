from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application.models import Curriculum, CurriculumRules, Requisite, Subject
from app.core.errors import ConflictError, NotFoundError
from app.data.orm import CurriculumORM, CurriculumRulesORM, RequisiteORM, SubjectORM


def _subject(row: SubjectORM) -> Subject:
    return Subject(
        id=row.id,
        clave=row.clave,
        name=row.name,
        credits=row.credits,
        ht=row.ht,
        hp=row.hp,
        suggested_semester=row.suggested_semester,
        grid_row=row.grid_row,
        grid_col=row.grid_col,
        kind=row.kind,  # type: ignore[arg-type]
        min_credit_pct=row.min_credit_pct,
        counts_toward_load=row.counts_toward_load,
    )


def _apply(row: SubjectORM, subject: Subject) -> None:
    row.name = subject.name
    row.credits = subject.credits
    row.ht = subject.ht
    row.hp = subject.hp
    row.suggested_semester = subject.suggested_semester
    row.grid_row = subject.grid_row
    row.grid_col = subject.grid_col
    row.kind = subject.kind
    row.min_credit_pct = subject.min_credit_pct
    row.counts_toward_load = subject.counts_toward_load


class SqlCurriculumRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------ curriculum

    async def get_active_id(self) -> int | None:
        return (
            await self._db.execute(
                select(CurriculumORM.id).where(CurriculumORM.is_active.is_(True)).order_by(CurriculumORM.id)
            )
        ).scalars().first()

    async def get_active(self) -> Curriculum | None:
        row = (
            await self._db.execute(
                select(CurriculumORM).where(CurriculumORM.is_active.is_(True)).order_by(CurriculumORM.id)
            )
        ).scalars().first()
        if row is None:
            return None
        return Curriculum(
            id=row.id,
            code=row.code,
            specialty_code=row.specialty_code,
            name=row.name,
            total_credits=row.total_credits,
            subjects=await self.list_subjects(row.id),
            requisites=await self.list_requisites(row.id),
            rules=await self.get_rules(row.id),
        )

    # ------------------------------------------------------------------ subjects

    async def list_subjects(self, curriculum_id: int) -> list[Subject]:
        rows = (
            await self._db.execute(
                select(SubjectORM)
                .where(SubjectORM.curriculum_id == curriculum_id)
                .order_by(SubjectORM.suggested_semester, SubjectORM.grid_row, SubjectORM.clave)
            )
        ).scalars()
        return [_subject(r) for r in rows]

    async def _subject_row(self, curriculum_id: int, clave: str) -> SubjectORM | None:
        return (
            await self._db.execute(
                select(SubjectORM).where(
                    SubjectORM.curriculum_id == curriculum_id, SubjectORM.clave == clave
                )
            )
        ).scalar_one_or_none()

    async def get_subject(self, curriculum_id: int, clave: str) -> Subject | None:
        row = await self._subject_row(curriculum_id, clave)
        return _subject(row) if row else None

    async def create_subject(self, curriculum_id: int, subject: Subject) -> Subject:
        row = SubjectORM(curriculum_id=curriculum_id, clave=subject.clave)
        _apply(row, subject)
        self._db.add(row)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise ConflictError(f"Ya existe una materia con clave {subject.clave}.") from exc
        await self._db.refresh(row)
        return _subject(row)

    async def update_subject(self, curriculum_id: int, subject: Subject) -> Subject:
        row = await self._subject_row(curriculum_id, subject.clave)
        if row is None:
            raise NotFoundError(f"No existe la materia {subject.clave}.")
        _apply(row, subject)
        await self._db.commit()
        return _subject(row)

    async def delete_subject(self, curriculum_id: int, clave: str) -> None:
        row = await self._subject_row(curriculum_id, clave)
        if row is None:
            raise NotFoundError(f"No existe la materia {clave}.")
        # Explicit so it also works where FK cascades are off (SQLite).
        await self._db.execute(
            delete(RequisiteORM).where(
                or_(RequisiteORM.subject_id == row.id, RequisiteORM.requires_subject_id == row.id)
            )
        )
        await self._db.delete(row)
        await self._db.commit()

    # ------------------------------------------------------------------ requisites

    async def list_requisites(self, curriculum_id: int) -> list[Requisite]:
        target = aliased(SubjectORM)
        source = aliased(SubjectORM)
        rows = await self._db.execute(
            select(RequisiteORM.id, target.clave, source.clave, RequisiteORM.type)
            .join(target, RequisiteORM.subject_id == target.id)
            .join(source, RequisiteORM.requires_subject_id == source.id)
            .where(RequisiteORM.curriculum_id == curriculum_id)
            .order_by(RequisiteORM.id)
        )
        return [
            Requisite(id=rid, subject_clave=subject, requires_clave=requires, type=rtype)  # type: ignore[arg-type]
            for rid, subject, requires, rtype in rows
        ]

    async def add_requisite(self, curriculum_id: int, requisite: Requisite) -> Requisite:
        subject = await self._subject_row(curriculum_id, requisite.subject_clave)
        requires = await self._subject_row(curriculum_id, requisite.requires_clave)
        if subject is None or requires is None:
            raise NotFoundError("Alguna de las materias no existe.")
        row = RequisiteORM(
            curriculum_id=curriculum_id,
            subject_id=subject.id,
            requires_subject_id=requires.id,
            type=requisite.type,
        )
        self._db.add(row)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise ConflictError("Ese requisito ya existe.") from exc
        return Requisite(
            id=row.id,
            subject_clave=requisite.subject_clave,
            requires_clave=requisite.requires_clave,
            type=requisite.type,
        )

    async def delete_requisite(self, curriculum_id: int, requisite_id: int) -> bool:
        result = await self._db.execute(
            delete(RequisiteORM).where(
                RequisiteORM.id == requisite_id, RequisiteORM.curriculum_id == curriculum_id
            )
        )
        await self._db.commit()
        return bool(result.rowcount)

    # ------------------------------------------------------------------ rules

    async def get_rules(self, curriculum_id: int) -> CurriculumRules:
        row = await self._db.get(CurriculumRulesORM, curriculum_id)
        if row is None:
            return CurriculumRules()
        return CurriculumRules(
            max_credits_per_term=row.max_credits_per_term,
            min_credits_per_term=row.min_credits_per_term,
            summer_max_subjects=row.summer_max_subjects,
            passing_grade=row.passing_grade,
        )

    async def update_rules(self, curriculum_id: int, rules: CurriculumRules) -> CurriculumRules:
        row = await self._db.get(CurriculumRulesORM, curriculum_id)
        if row is None:
            row = CurriculumRulesORM(curriculum_id=curriculum_id)
            self._db.add(row)
        row.max_credits_per_term = rules.max_credits_per_term
        row.min_credits_per_term = rules.min_credits_per_term
        row.summer_max_subjects = rules.summer_max_subjects
        row.passing_grade = rules.passing_grade
        await self._db.commit()
        return rules
