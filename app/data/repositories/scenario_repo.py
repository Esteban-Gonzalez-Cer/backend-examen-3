from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.models import Scenario
from app.core.errors import NotFoundError
from app.data.orm import ScenarioORM


def _scenario(row: ScenarioORM) -> Scenario:
    return Scenario(
        id=row.id,
        numero_control=row.numero_control,
        name=row.name,
        params=dict(row.params or {}),
        result_summary=dict(row.result_summary or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlScenarioRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_student(self, numero_control: str) -> list[Scenario]:
        rows = (
            await self._db.execute(
                select(ScenarioORM)
                .where(ScenarioORM.numero_control == numero_control)
                .order_by(ScenarioORM.updated_at.desc())
            )
        ).scalars()
        return [_scenario(r) for r in rows]

    async def _row(self, scenario_id: UUID, numero_control: str) -> ScenarioORM | None:
        return (
            await self._db.execute(
                select(ScenarioORM).where(
                    ScenarioORM.id == scenario_id, ScenarioORM.numero_control == numero_control
                )
            )
        ).scalar_one_or_none()

    async def get(self, scenario_id: UUID, numero_control: str) -> Scenario | None:
        row = await self._row(scenario_id, numero_control)
        return _scenario(row) if row else None

    async def create(self, scenario: Scenario) -> Scenario:
        row = ScenarioORM(
            id=scenario.id,
            numero_control=scenario.numero_control,
            name=scenario.name,
            params=scenario.params,
            result_summary=scenario.result_summary,
            created_at=scenario.created_at,
            updated_at=scenario.updated_at,
        )
        self._db.add(row)
        await self._db.commit()
        return _scenario(row)

    async def update(self, scenario: Scenario) -> Scenario:
        row = await self._row(scenario.id, scenario.numero_control)
        if row is None:
            raise NotFoundError("El escenario no existe.")
        row.name = scenario.name
        row.params = scenario.params
        row.result_summary = scenario.result_summary
        row.updated_at = scenario.updated_at
        await self._db.commit()
        return _scenario(row)

    async def delete(self, scenario_id: UUID, numero_control: str) -> bool:
        result = await self._db.execute(
            delete(ScenarioORM).where(
                ScenarioORM.id == scenario_id, ScenarioORM.numero_control == numero_control
            )
        )
        await self._db.commit()
        return bool(result.rowcount)
