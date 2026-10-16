"""Formato uniforme de las respuestas de error."""

from pydantic import BaseModel, Field


class ErrorCampo(BaseModel):
    campo: str = Field(description="Ubicación del parámetro inválido.", examples=["query.limit"])
    mensaje: str


class DetalleError(BaseModel):
    codigo: str = Field(
        description="Código estable del error, pensado para uso programático.",
        examples=["api_key_invalida"],
    )
    mensaje: str = Field(description="Descripción legible del error.")
    request_id: str | None = Field(default=None, description="ID de la solicitud, para soporte.")
    detalles: list[ErrorCampo] | None = None


class ErrorRespuesta(BaseModel):
    error: DetalleError
