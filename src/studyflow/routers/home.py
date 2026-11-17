from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from studyflow.database import get_db
from studyflow.dependencies.auth import get_current_user
from studyflow.dependencies.clock import get_now
from studyflow.models.user import User
from studyflow.schemas.home import HomeBlock, HomeResponse, HomeSubject
from studyflow.services import home as home_service
from studyflow.services.home import BlockWithSubject

router = APIRouter(prefix="/home", tags=["Home"])


def to_home_block(item: BlockWithSubject, zone: ZoneInfo) -> HomeBlock:
    block, subject = item

    return HomeBlock(
        id=block.id,
        title=block.title,
        starts_at=block.starts_at.astimezone(zone),
        ends_at=block.ends_at.astimezone(zone),
        task_id=block.task_id,
        subject=HomeSubject.model_validate(subject) if subject is not None else None,
    )


@router.get("", response_model=HomeResponse)
def read_home(
    now: datetime = Depends(get_now),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HomeResponse:
    zone = ZoneInfo(user.timezone)
    following = home_service.get_next_block(db, user.id, now)

    return HomeResponse(
        now=[
            to_home_block(item, zone)
            for item in home_service.get_current_blocks(db, user.id, now)
        ],
        next=to_home_block(following, zone) if following is not None else None,
    )
