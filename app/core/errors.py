"""Domain exceptions. The interaction layer translates them into HTTP responses."""

from typing import Any


class AppError(Exception):
    code = "APP_ERROR"
    default_message = "Ocurrió un error inesperado."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class InvalidCredentialsError(AppError):
    code = "INVALID_CREDENTIALS"
    default_message = "Correo o contraseña incorrectos."


class InvalidTokenError(AppError):
    code = "INVALID_TOKEN"
    default_message = "Sesión no válida. Inicia sesión de nuevo."


class SessionExpiredError(AppError):
    code = "SESSION_EXPIRED"
    default_message = "Tu sesión expiró. Inicia sesión de nuevo."


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    default_message = "No tienes permisos para realizar esta acción."


class NotFoundError(AppError):
    code = "NOT_FOUND"
    default_message = "El recurso solicitado no existe."


class ConflictError(AppError):
    code = "CONFLICT"
    default_message = "La operación entra en conflicto con los datos existentes."


class CycleDetectedError(ConflictError):
    code = "CYCLE_DETECTED"
    default_message = "El requisito crearía un ciclo en la retícula."


class ValidationFailedError(AppError):
    code = "VALIDATION_ERROR"
    default_message = "Los datos enviados no son válidos."


class CurriculumNotConfiguredError(AppError):
    code = "CURRICULUM_NOT_CONFIGURED"
    default_message = "No hay una retícula cargada. Ejecuta el seed de la base de datos."


class SiiUnavailableError(AppError):
    code = "SII_UNAVAILABLE"
    default_message = "El SII no está disponible en este momento. Intenta más tarde."


class SiiBadResponseError(AppError):
    code = "SII_BAD_RESPONSE"
    default_message = "El SII respondió con datos inesperados."


class SiiUnauthorizedError(AppError):
    """Raised by the integration layer when SII rejects the bearer token."""

    code = "SII_UNAUTHORIZED"
    default_message = "El SII rechazó el token."
