"""Load the curriculum (retícula) into the database.

Usage (from `backend/`, venv active):
    python -m app.data.seed.seed           # insert only if the curriculum does not exist yet
    python -m app.data.seed.seed --reset   # replace subjects/requisites/rules with the JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.data.db import create_engine, create_sessionmaker
from app.data.orm import CurriculumORM, CurriculumRulesORM, RequisiteORM, SubjectORM

SEED_FILE = Path(__file__).with_name("curriculum_isic_2010_224_idp.json")


def load_seed(path: Path = SEED_FILE) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    columns = data["subject_columns"]
    data["subjects"] = [dict(zip(columns, row, strict=True)) for row in data["subjects"]]
    data["requisites"] = [
        {"subject": subject, "requires": requires, "type": rtype}
        for subject, requires, rtype in data["requisites"]
    ]
    return data


async def seed_database(db: AsyncSession, *, reset: bool = False, data: dict[str, Any] | None = None) -> str:
    data = data or load_seed()
    meta = data["curriculum"]

    curriculum = (
        await db.execute(select(CurriculumORM).where(CurriculumORM.code == meta["code"]))
    ).scalar_one_or_none()

    if curriculum is not None and not reset:
        return f"Curriculum {meta['code']} already present; nothing to do (use --reset to replace)."

    if curriculum is None:
        curriculum = CurriculumORM(**meta, is_active=True)
        db.add(curriculum)
        await db.flush()
    else:
        for key, value in meta.items():
            setattr(curriculum, key, value)
        await db.execute(delete(RequisiteORM).where(RequisiteORM.curriculum_id == curriculum.id))
        await db.execute(delete(SubjectORM).where(SubjectORM.curriculum_id == curriculum.id))
        await db.execute(
            delete(CurriculumRulesORM).where(CurriculumRulesORM.curriculum_id == curriculum.id)
        )
        await db.flush()

    ids: dict[str, int] = {}
    for item in data["subjects"]:
        row = SubjectORM(curriculum_id=curriculum.id, **item)
        db.add(row)
        await db.flush()
        ids[item["clave"]] = row.id

    for req in data["requisites"]:
        db.add(
            RequisiteORM(
                curriculum_id=curriculum.id,
                subject_id=ids[req["subject"]],
                requires_subject_id=ids[req["requires"]],
                type=req["type"],
            )
        )

    db.add(CurriculumRulesORM(curriculum_id=curriculum.id, **data["rules"]))
    await db.commit()
    return (
        f"Seeded {meta['code']}: {len(data['subjects'])} subjects, "
        f"{len(data['requisites'])} requisites."
    )


async def _main(reset: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings.async_database_url)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as db:
        print(await seed_database(db, reset=reset))
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="replace the existing curriculum")
    args = parser.parse_args()
    asyncio.run(_main(args.reset))
