"""Administration of the stored curriculum (subjects, requisites, rules)."""

from __future__ import annotations

from app.application.models import CurriculumRules, Requisite, Subject
from app.application.ports import CurriculumRepository
from app.application.whatif.engine.graph import find_cycle
from app.core.errors import (
    ConflictError,
    CurriculumNotConfiguredError,
    CycleDetectedError,
    NotFoundError,
    ValidationFailedError,
)


class AdminCurriculumService:
    def __init__(self, curricula: CurriculumRepository) -> None:
        self._curricula = curricula

    async def _curriculum_id(self) -> int:
        curriculum_id = await self._curricula.get_active_id()
        if curriculum_id is None:
            raise CurriculumNotConfiguredError()
        return curriculum_id

    # ------------------------------------------------------------------ subjects

    async def list_subjects(self) -> list[Subject]:
        return await self._curricula.list_subjects(await self._curriculum_id())

    async def create_subject(self, subject: Subject) -> Subject:
        cid = await self._curriculum_id()
        subject.clave = subject.clave.strip().upper()
        if await self._curricula.get_subject(cid, subject.clave) is not None:
            raise ConflictError(f"Ya existe una materia con clave {subject.clave}.")
        return await self._curricula.create_subject(cid, subject)

    async def update_subject(self, clave: str, subject: Subject) -> Subject:
        cid = await self._curriculum_id()
        subject.clave = clave.strip().upper()
        return await self._curricula.update_subject(cid, subject)

    async def delete_subject(self, clave: str) -> None:
        cid = await self._curriculum_id()
        await self._curricula.delete_subject(cid, clave.strip().upper())

    # ------------------------------------------------------------------ requisites

    async def list_requisites(self) -> list[Requisite]:
        return await self._curricula.list_requisites(await self._curriculum_id())

    async def add_requisite(self, requisite: Requisite) -> Requisite:
        cid = await self._curriculum_id()
        requisite.subject_clave = requisite.subject_clave.strip().upper()
        requisite.requires_clave = requisite.requires_clave.strip().upper()
        if requisite.subject_clave == requisite.requires_clave:
            raise ValidationFailedError("Una materia no puede requerirse a sí misma.")

        subjects = await self._curricula.list_subjects(cid)
        claves = {s.clave for s in subjects}
        missing = {requisite.subject_clave, requisite.requires_clave} - claves
        if missing:
            raise NotFoundError("No existe la materia " + ", ".join(sorted(missing)) + ".")

        existing = await self._curricula.list_requisites(cid)
        if any(
            {r.subject_clave, r.requires_clave} == {requisite.subject_clave, requisite.requires_clave}
            for r in existing
        ):
            raise ConflictError("Ya existe un requisito entre esas materias.")

        edges = [(r.requires_clave, r.subject_clave) for r in existing]
        edges.append((requisite.requires_clave, requisite.subject_clave))
        cycle = find_cycle(claves, edges)
        if cycle:
            raise CycleDetectedError(
                "El requisito crearía un ciclo: " + " → ".join(cycle) + ".",
                details={"cycle": cycle},
            )
        return await self._curricula.add_requisite(cid, requisite)

    async def delete_requisite(self, requisite_id: int) -> None:
        cid = await self._curriculum_id()
        if not await self._curricula.delete_requisite(cid, requisite_id):
            raise NotFoundError("El requisito no existe.")

    # ------------------------------------------------------------------ rules

    async def get_rules(self) -> CurriculumRules:
        return await self._curricula.get_rules(await self._curriculum_id())

    async def update_rules(self, rules: CurriculumRules) -> CurriculumRules:
        if rules.min_credits_per_term > rules.max_credits_per_term:
            raise ValidationFailedError("La carga mínima no puede ser mayor a la máxima.")
        return await self._curricula.update_rules(await self._curriculum_id(), rules)
