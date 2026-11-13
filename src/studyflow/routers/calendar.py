from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.models.user import User
from studyflow.schemas.calendar import FreeWindow
from studyflow.schemas.common import HourMinute
from studyflow.services.calendar import get_free_windows

router = APIRouter(prefix="/calendar", tags=["Calendar"])


@router.get("/free", response_model=list[FreeWindow])
def read_free_windows(
    period_start: Annotated[AwareDatetime, Query(alias="from")],
    period_end: Annotated[AwareDatetime, Query(alias="to")],
    day_start: Annotated[HourMinute | None, Query()] = None,
    day_end: Annotated[HourMinute | None, Query()] = None,
    min_minutes: Annotated[int, Query(ge=1, le=1440)] = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FreeWindow]:
    # The profile hours are used unless the request overrides them.
    # Either of the two can be overridden on its own.
    day_start = user.day_start if day_start is None else day_start
    day_end = user.day_end if day_end is None else day_end

    try:
        windows = get_free_windows(
            db=db,
            user_id=user.id,
            timezone=user.timezone,
            period_start=period_start,
            period_end=period_end,
            day_start=day_start,
            day_end=day_end,
            min_minutes=min_minutes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return [
        FreeWindow(
            starts_at=start,
            ends_at=end,
            minutes=int((end - start).total_seconds() // 60),
        )
        for start, end in windows
    ]
