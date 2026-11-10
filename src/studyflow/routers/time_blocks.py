from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.csrf import require_csrf
from studyflow.models.time_block import TimeBlock
from studyflow.models.user import User
from studyflow.schemas.time_blocks import (
    BlockConflictResponse,
    BlockCreate,
    BlockResponse,
    BlockSummary,
    BlockUpdate,
)
from studyflow.services import time_blocks as block_service
from studyflow.services.time_blocks import (
    BlockConflictError,
    SubjectNotFoundError,
    TaskNotFoundError,
)

router = APIRouter(prefix="/blocks", tags=["Time blocks"])

CONFLICT_RESPONSE = {
    status.HTTP_409_CONFLICT: {
        "description": (
            "The block overlaps other planned blocks. Nothing was saved. "
            "Repeat the request with allow_conflicts=true to save it anyway."
        ),
    },
}


def to_response(block: TimeBlock, conflict_ids: list[UUID]) -> BlockResponse:
    response = BlockResponse.model_validate(block)
    return response.model_copy(update={"conflicting_block_ids": conflict_ids})


def conflict_error(exc: BlockConflictError) -> HTTPException:
    detail = BlockConflictResponse(
        message=str(exc),
        conflicts=[BlockSummary.model_validate(block) for block in exc.conflicts],
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=jsonable_encoder(detail),
    )


@router.post(
    "/",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses=CONFLICT_RESPONSE,
)
def create_block(
    data: BlockCreate,
    allow_conflicts: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BlockResponse:
    try:
        block = block_service.create_block(
            db=db,
            user_id=user.id,
            data=data,
            allow_conflicts=allow_conflicts,
        )
    except (TaskNotFoundError, SubjectNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BlockConflictError as exc:
        raise conflict_error(exc) from exc

    return to_response(block, block_service.get_conflict_ids(db, block))


@router.get("/", response_model=list[BlockResponse])
def read_blocks(
    period_start: Annotated[AwareDatetime, Query(alias="from")],
    period_end: Annotated[AwareDatetime, Query(alias="to")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BlockResponse]:
    try:
        blocks = block_service.list_blocks(db, user.id, period_start, period_end)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    conflicts = block_service.get_conflict_map(db, user.id, period_start, period_end)
    return [to_response(block, conflicts.get(block.id, [])) for block in blocks]


@router.get("/{block_id}", response_model=BlockResponse)
def read_block(
    block_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BlockResponse:
    block = block_service.get_block(db, user.id, block_id)

    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    return to_response(block, block_service.get_conflict_ids(db, block))


@router.patch(
    "/{block_id}",
    response_model=BlockResponse,
    dependencies=[Depends(require_csrf)],
    responses=CONFLICT_RESPONSE,
)
def edit_block(
    block_id: UUID,
    data: BlockUpdate,
    allow_conflicts: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BlockResponse:
    try:
        block = block_service.update_block(
            db=db,
            user_id=user.id,
            block_id=block_id,
            data=data,
            allow_conflicts=allow_conflicts,
        )
    except (TaskNotFoundError, SubjectNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BlockConflictError as exc:
        raise conflict_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    return to_response(block, block_service.get_conflict_ids(db, block))


@router.delete(
    "/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def remove_block(
    block_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    deleted = block_service.delete_block(db=db, user_id=user.id, block_id=block_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )
