from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.csrf import require_csrf
from studyflow.models.user import User
from studyflow.routers.time_blocks import to_response
from studyflow.schemas.series import (
    FollowingDeleteResponse,
    FollowingUpdate,
    SeriesConflictResponse,
    SeriesCreate,
    SeriesPreviewBlock,
    SeriesPreviewResponse,
)
from studyflow.schemas.time_blocks import BlockResponse, BlockSummary
from studyflow.services import series as series_service
from studyflow.services import time_blocks as block_service
from studyflow.services.series import (
    ConflictingMove,
    FollowingConflictError,
    PlannedBlock,
    SeriesConflictError,
)
from studyflow.services.time_blocks import SubjectNotFoundError, TaskNotFoundError

router = APIRouter(prefix="/blocks", tags=["Time block series"])

MAX_CONFLICTS_SHOWN = 10


def to_preview_block(item: PlannedBlock, zone: ZoneInfo) -> SeriesPreviewBlock:
    return SeriesPreviewBlock(
        title=item.block.title,
        starts_at=item.block.starts_at.astimezone(zone),
        ends_at=item.block.ends_at.astimezone(zone),
        conflicts=[BlockSummary.model_validate(block) for block in item.conflicts],
    )


def to_move_block(item: ConflictingMove, zone: ZoneInfo) -> SeriesPreviewBlock:
    return SeriesPreviewBlock(
        title=item.title,
        starts_at=item.starts_at.astimezone(zone),
        ends_at=item.ends_at.astimezone(zone),
        conflicts=item.conflicts,
    )


@router.post(
    "/series/preview",
    response_model=SeriesPreviewResponse,
    dependencies=[Depends(require_csrf)],
)
def preview_series(
    data: SeriesCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SeriesPreviewResponse:
    try:
        planned = series_service.plan_series(db, user.id, user.timezone, data)
    except (TaskNotFoundError, SubjectNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    zone = ZoneInfo(user.timezone)
    return SeriesPreviewResponse(
        total_blocks=len(planned),
        conflicting_blocks=sum(1 for item in planned if item.conflicts),
        blocks=[to_preview_block(item, zone) for item in planned],
    )


@router.post(
    "/series",
    response_model=list[BlockResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "Some blocks overlap existing planned blocks. Nothing was saved. "
                "Repeat the request with allow_conflicts=true to save anyway."
            ),
        },
    },
)
def create_series(
    data: SeriesCreate,
    allow_conflicts: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BlockResponse]:
    try:
        blocks = series_service.create_series(
            db=db,
            user_id=user.id,
            timezone=user.timezone,
            data=data,
            allow_conflicts=allow_conflicts,
        )
    except (TaskNotFoundError, SubjectNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SeriesConflictError as exc:
        zone = ZoneInfo(user.timezone)
        detail = SeriesConflictResponse(
            message=str(exc),
            total_conflicting_blocks=len(exc.conflicting),
            blocks=[
                to_preview_block(item, zone)
                for item in exc.conflicting[:MAX_CONFLICTS_SHOWN]
            ],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=jsonable_encoder(detail),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    conflicts = block_service.get_conflict_map(
        db,
        user.id,
        blocks[0].starts_at,
        blocks[-1].ends_at,
    )
    return [to_response(block, conflicts.get(block.id, [])) for block in blocks]


@router.patch(
    "/{block_id}/following",
    response_model=list[BlockResponse],
    dependencies=[Depends(require_csrf)],
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "Some changed blocks overlap other planned blocks. Nothing was "
                "changed. Repeat the request with allow_conflicts=true to save."
            ),
        },
    },
)
def update_following_blocks(
    block_id: UUID,
    data: FollowingUpdate,
    allow_conflicts: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BlockResponse]:
    try:
        blocks = series_service.update_following(
            db=db,
            user_id=user.id,
            timezone=user.timezone,
            block_id=block_id,
            data=data,
            allow_conflicts=allow_conflicts,
        )
    except FollowingConflictError as exc:
        zone = ZoneInfo(user.timezone)
        detail = SeriesConflictResponse(
            message=str(exc),
            total_conflicting_blocks=len(exc.conflicting),
            blocks=[
                to_move_block(item, zone)
                for item in exc.conflicting[:MAX_CONFLICTS_SHOWN]
            ],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=jsonable_encoder(detail),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if blocks is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    conflicts = block_service.get_conflict_map(
        db,
        user.id,
        min(block.starts_at for block in blocks),
        max(block.ends_at for block in blocks),
    )
    return [to_response(block, conflicts.get(block.id, [])) for block in blocks]


@router.delete(
    "/{block_id}/following",
    response_model=FollowingDeleteResponse,
    dependencies=[Depends(require_csrf)],
)
def delete_following_blocks(
    block_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FollowingDeleteResponse:
    try:
        deleted = series_service.delete_following(db, user.id, block_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if deleted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Block not found",
        )

    return FollowingDeleteResponse(deleted_blocks=deleted)
