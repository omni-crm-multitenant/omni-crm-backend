from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext


router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None
    priority: str = "medium"
    source: str = "user"
    source_ref_id: UUID | None = None
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    opportunity_id: UUID | None = None


class TaskResponse(TaskCreate):
    id: UUID
    tenant_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


class TaskPatch(BaseModel):
    description: str | None = None
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None
    priority: str | None = None
    status: str | None = None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, context: TenantContext = Depends(require_tenant_context), session: AsyncSession = Depends(get_session)) -> TaskResponse:
    from app.models.tasks import Task
    task = Task(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(task)
    await session.flush()
    return TaskResponse.model_validate(task, from_attributes=True)


@router.get("", response_model=list[TaskResponse])
async def list_tasks(context: TenantContext = Depends(require_tenant_context), session: AsyncSession = Depends(get_session), status_filter: str | None = None, assigned_user_id: UUID | None = None, overdue: bool = False) -> list[TaskResponse]:
    from app.models.tasks import Task
    query = select(Task).where(Task.tenant_id == context.tenant_id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if assigned_user_id:
        query = query.where(Task.assigned_user_id == assigned_user_id)
    if overdue:
        query = query.where(Task.due_at < datetime.now(UTC), Task.status == "open")
    rows = list((await session.scalars(query.order_by(Task.due_at.asc().nulls_last(), Task.id.asc()))).all())
    return [TaskResponse.model_validate(item, from_attributes=True) for item in rows]


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: UUID, payload: TaskPatch, context: TenantContext = Depends(require_tenant_context), session: AsyncSession = Depends(get_session)) -> TaskResponse:
    from app.models.tasks import Task
    task = await session.scalar(select(Task).where(Task.id == task_id, Task.tenant_id == context.tenant_id).with_for_update())
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND"})
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    await session.flush()
    return TaskResponse.model_validate(task, from_attributes=True)
