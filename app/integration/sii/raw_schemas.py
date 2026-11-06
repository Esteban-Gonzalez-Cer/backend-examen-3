"""Raw shapes of the SII ITC responses (only the fields we use). Lenient on purpose."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RawProfile(_Raw):
    numero_control: str
    persona: str
    email: str = ""
    semestre: int = 0
    num_mat_rep_no_acreditadas: int | None = 0
    creditos_acumulados: int = 0
    promedio_ponderado: float = 0.0
    promedio_aritmetico: float = 0.0
    materias_cursadas: int = 0
    materias_reprobadas: int = 0
    materias_aprobadas: int = 0
    creditos_complementarios: int = 0
    porcentaje_avance: float = 0.0
    # SII spells it "percentaje".
    porcentaje_avance_cursando: float | None = Field(
        default=None,
        validation_alias=AliasChoices("percentaje_avance_cursando", "porcentaje_avance_cursando"),
    )
    foto: str | None = None


class RawKardexEntry(_Raw):
    nombre_materia: str
    clave_materia: str
    periodo: str
    creditos: int = 0
    calificacion: str | None = None
    descripcion: str = ""
    semestre: int = 0


class RawKardex(_Raw):
    porcentaje_avance: float = 0.0
    kardex: list[RawKardexEntry] = []


class RawPeriod(_Raw):
    clave_periodo: str
    anio: int
    descripcion_periodo: str = ""


class RawSubjectRef(_Raw):
    id_grupo: int
    nombre_materia: str
    clave_materia: str
    letra_grupo: str = ""


class RawPartial(_Raw):
    id_calificacion: int | None = None
    numero_calificacion: int
    calificacion: str | None = None


class RawCourseGrades(_Raw):
    materia: RawSubjectRef
    # SII spells it "calificaiones".
    calificaciones: list[RawPartial] = Field(
        default_factory=list,
        validation_alias=AliasChoices("calificaiones", "calificaciones"),
    )


class RawGradesPeriod(_Raw):
    periodo: RawPeriod
    materias: list[RawCourseGrades] = []


class RawScheduleRow(_Raw):
    id_grupo: int
    letra_grupo: str = ""
    nombre_materia: str
    clave_materia: str
    nombre_plan: str | None = None
    lunes: str | None = None
    lunes_clave_salon: str | None = None
    martes: str | None = None
    martes_clave_salon: str | None = None
    miercoles: str | None = None
    miercoles_clave_salon: str | None = None
    jueves: str | None = None
    jueves_clave_salon: str | None = None
    viernes: str | None = None
    viernes_clave_salon: str | None = None
    sabado: str | None = None
    sabado_clave_salon: str | None = None


class RawSchedulePeriod(_Raw):
    periodo: RawPeriod
    horario: list[RawScheduleRow] = []
