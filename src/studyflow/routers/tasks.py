from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
from studyflow.schemas.tasks import TaskCreate, TaskResponse, TaskUpdate
from studyflow.services.tasks import (
    SubjectNotFoundError,
)
from studyflow.services.tasks import (
    create_task as create_task_service,
)
from studyflow.services.tasks import (
    delete_task as delete_task_service,
)
from studyflow.services.tasks import (
    get_task as get_task_service,
)
from studyflow.services.tasks import (
    get_tasks as get_tasks_service,
)
from studyflow.services.tasks import (
    update_task as update_task_service,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    try:
        task = create_task_service(
            db=db,
            user_id=user.id,
            data=data,
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return task


@router.get("/", response_model=list[TaskResponse])
def read_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    return get_tasks_service(
        db=db,
        user_id=user.id,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def read_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    task = get_task_service(
        db=db,
        user_id=user.id,
        task_id=task_id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def edit_task(
    task_id: UUID,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    try:
        task = update_task_service(
            db=db,
            user_id=user.id,
            task_id=task_id,
            data=data,
        )
    except SubjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    deleted = delete_task_service(
        db=db,
        user_id=user.id,
        task_id=task_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
