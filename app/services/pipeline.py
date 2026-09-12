from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import Pipeline, PipelineStage


DEFAULT_STAGES = (
    ("Nuevo", "none"),
    ("Contactado", "none"),
    ("Calificado", "none"),
    ("Cita/Diagnóstico", "none"),
    ("Propuesta", "none"),
    ("Ganado", "won"),
    ("Perdido", "lost"),
)


async def create_default_pipeline(session: AsyncSession, tenant_id: UUID) -> Pipeline:
    pipeline = Pipeline(tenant_id=tenant_id, name="Ventas", is_default=True)
    session.add(pipeline)
    await session.flush()
    session.add_all(
        [
            PipelineStage(
                tenant_id=tenant_id,
                pipeline_id=pipeline.id,
                name=name,
                position=position,
                terminal_type=terminal_type,
            )
            for position, (name, terminal_type) in enumerate(DEFAULT_STAGES, start=1)
        ]
    )
    await session.flush()
    return pipeline
