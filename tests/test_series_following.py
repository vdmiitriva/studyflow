from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from studyflow.dependencies.auth import get_current_user
from studyflow.main import app
from studyflow.models import Subject, TimeBlock, User
from studyflow.services import series as series_service
from studyflow.services.series import moved_times

SERIES_URL = "/api/v1/blocks/series"
BLOCKS_URL = "/api/v1/blocks/"
TASKS_URL = "/api/v1/tasks/"
SUBJECTS_URL = "/api/v1/subjects/"


def utc(hour: int, minute: int = 0, day: int = 10, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


def following_url(block_id) -> str:
    return f"{BLOCKS_URL}{block_id}/following"


# ---------- the new times (no database needed) ----------

ONE_BLOCK = SimpleNamespace(starts_at=utc(10), ends_at=utc(11))
UTC_ZONE = ZoneInfo("UTC")


def test_new_start_and_duration_are_applied():
    assert moved_times(ONE_BLOCK, UTC_ZONE, time(12), 90) == (utc(12), utc(13, 30))


def test_only_the_start_keeps_the_duration():
    assert moved_times(ONE_BLOCK, UTC_ZONE, time(12), None) == (utc(12), utc(13))


def test_only_the_duration_keeps_the_start():
    assert moved_times(ONE_BLOCK, UTC_ZONE, None, 120) == (utc(10), utc(12))


def test_nothing_given_changes_nothing():
    assert moved_times(ONE_BLOCK, UTC_ZONE, None, None) == (utc(10), utc(11))


def test_the_local_date_comes_from_the_current_timezone():
    late = SimpleNamespace(starts_at=utc(23, 30), ends_at=utc(0, 30, day=11))

    in_tokyo = moved_times(late, ZoneInfo("Asia/Tokyo"), time(9), None)
    in_utc = moved_times(late, UTC_ZONE, time(9), None)

    assert in_tokyo == (utc(0, day=11), utc(1, day=11))
    assert in_utc == (utc(9), utc(10))


# ---------- helpers for the API tests ----------


@pytest.fixture
def login(db_session):
    def log_in(timezone: str = "UTC") -> User:
        user = User(email=f"{uuid4()}@example.com", timezone=timezone)
        db_session.add(user)
        db_session.flush()
        app.dependency_overrides[get_current_user] = lambda: user
        return user

    yield log_in
    app.dependency_overrides.pop(get_current_user, None)


def series_body(**fields) -> dict:
    data = {
        "title": "English",
        "first_date": "2026-11-10",
        "last_date": "2026-11-14",
        "start_time": "10:00",
        "duration_minutes": 60,
        "repeat": "daily",
    }
    data.update(fields)
    return data


def make_series(client, **fields) -> list[dict]:
    response = client.post(SERIES_URL, json=series_body(**fields))
    assert response.status_code == 201
    return response.json()


def add_block(db_session, user: User, start: datetime, **fields) -> TimeBlock:
    block = TimeBlock(
        user_id=user.id,
        title=fields.pop("title", "Existing"),
        starts_at=start,
        ends_at=fields.pop("end", start + timedelta(hours=1)),
        **fields,
    )
    db_session.add(block)
    db_session.flush()
    return block


def make_stranger(db_session) -> User:
    stranger = User(email=f"{uuid4()}@example.com")
    db_session.add(stranger)
    db_session.flush()
    return stranger


def moment(block: dict, key: str) -> datetime:
    return datetime.fromisoformat(block[key])


def shape(client, blocks: list[dict]) -> list[tuple[datetime, datetime, str]]:
    """The start, end and status of the blocks as the API shows them now."""
    result = []
    for block in blocks:
        current = client.get(f"{BLOCKS_URL}{block['id']}").json()
        start, end = moment(current, "starts_at"), moment(current, "ends_at")
        result.append((start, end, current["status"]))
    return result


def spans(blocks: list[dict]) -> list[tuple[datetime, datetime]]:
    return [(moment(block, "starts_at"), moment(block, "ends_at")) for block in blocks]


def count_blocks(db_session, user: User) -> int:
    query = select(func.count()).select_from(TimeBlock)
    return db_session.execute(query.where(TimeBlock.user_id == user.id)).scalar_one()


# ---------- changing the block and the following ones ----------


def test_the_selected_and_the_following_blocks_are_changed(client, login):
    login()
    blocks = make_series(client)
    before = shape(client, blocks)

    response = client.patch(
        following_url(blocks[2]["id"]),
        json={"start_time": "12:00", "duration_minutes": 90},
    )

    assert response.status_code == 200
    changed = response.json()
    assert [item["id"] for item in changed] == [item["id"] for item in blocks[2:]]
    assert spans(changed) == [
        (utc(12, day=12), utc(13, 30, day=12)),
        (utc(12, day=13), utc(13, 30, day=13)),
        (utc(12, day=14), utc(13, 30, day=14)),
    ]
    assert {item["series_id"] for item in changed} == {blocks[0]["series_id"]}
    assert shape(client, blocks[:2]) == before[:2]


def test_changing_only_the_start_keeps_each_duration(client, login):
    login()
    blocks = make_series(client)

    response = client.patch(
        following_url(blocks[3]["id"]),
        json={"start_time": "12:00"},
    )

    assert spans(response.json()) == [
        (utc(12, day=13), utc(13, day=13)),
        (utc(12, day=14), utc(13, day=14)),
    ]


def test_changing_only_the_duration_keeps_each_start(client, login):
    login()
    blocks = make_series(client)

    response = client.patch(
        following_url(blocks[3]["id"]),
        json={"duration_minutes": 120},
    )

    assert spans(response.json()) == [
        (utc(10, day=13), utc(12, day=13)),
        (utc(10, day=14), utc(12, day=14)),
    ]


def test_from_the_first_block_changes_everything(client, login):
    login()
    blocks = make_series(client)

    response = client.patch(
        following_url(blocks[0]["id"]),
        json={"start_time": "08:30"},
    )

    assert len(response.json()) == 5


def test_from_the_last_block_changes_only_that_one(client, login):
    login()
    blocks = make_series(client)
    before = shape(client, blocks[:4])

    response = client.patch(
        following_url(blocks[4]["id"]),
        json={"start_time": "08:30"},
    )

    assert [item["id"] for item in response.json()] == [blocks[4]["id"]]
    assert shape(client, blocks[:4]) == before


def test_completed_and_skipped_blocks_are_left_alone(client, login):
    login()
    blocks = make_series(client)
    client.patch(f"{BLOCKS_URL}{blocks[3]['id']}", json={"status": "completed"})
    client.patch(f"{BLOCKS_URL}{blocks[4]['id']}", json={"status": "skipped"})
    before = shape(client, blocks[3:])

    response = client.patch(
        following_url(blocks[2]["id"]),
        json={"start_time": "12:00"},
    )

    assert [item["id"] for item in response.json()] == [blocks[2]["id"]]
    assert shape(client, blocks[3:]) == before


def test_the_selected_block_can_be_skipped_and_still_marks_the_start(client, login):
    login()
    blocks = make_series(client)
    client.patch(f"{BLOCKS_URL}{blocks[2]['id']}", json={"status": "skipped"})
    before = shape(client, blocks[:3])

    response = client.patch(
        following_url(blocks[2]["id"]),
        json={"start_time": "12:00"},
    )

    assert [item["id"] for item in response.json()] == [
        blocks[3]["id"],
        blocks[4]["id"],
    ]
    assert shape(client, blocks[:3]) == before


def test_other_series_and_single_blocks_are_not_touched(client, db_session, login):
    user = login()
    blocks = make_series(client)
    other_series = make_series(client, start_time="15:00")
    single = add_block(db_session, user, utc(16, day=12))
    before = shape(client, other_series)

    client.patch(following_url(blocks[0]["id"]), json={"start_time": "08:00"})

    assert shape(client, other_series) == before
    db_session.refresh(single)
    assert single.starts_at == utc(16, day=12)


def test_a_block_that_is_not_in_a_series_is_refused(client, db_session, login):
    user = login()
    single = add_block(db_session, user, utc(10))

    response = client.patch(following_url(single.id), json={"start_time": "12:00"})

    assert response.status_code == 422
    assert response.json()["detail"] == "The block is not part of a series"


def test_another_users_series_is_not_found(client, db_session, login):
    login()
    stranger = make_stranger(db_session)
    foreign = add_block(db_session, stranger, utc(10), series_id=uuid4())

    response = client.patch(following_url(foreign.id), json={"start_time": "12:00"})

    assert response.status_code == 404
    db_session.refresh(foreign)
    assert foreign.starts_at == utc(10)


def test_a_missing_block_is_not_found(client, login):
    login()

    response = client.patch(following_url(uuid4()), json={"start_time": "12:00"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Block not found"


def test_nothing_to_change_is_refused(client, login):
    login()
    blocks = make_series(client)
    client.patch(f"{BLOCKS_URL}{blocks[4]['id']}", json={"status": "skipped"})

    response = client.patch(
        following_url(blocks[4]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "There are no planned blocks to change"


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"start_time": None},
        {"duration_minutes": None},
        {"start_time": "9:00"},
        {"start_time": "24:00"},
        {"start_time": "12:00:30"},
        {"start_time": 1200},
        {"duration_minutes": 0},
        {"duration_minutes": 1441},
        {"duration_minutes": 1.5},
        {"duration_minutes": "long"},
    ],
    ids=lambda change: str(change),
)
def test_bad_changes_are_refused_and_change_nothing(client, login, change):
    login()
    blocks = make_series(client)
    before = shape(client, blocks)

    response = client.patch(following_url(blocks[1]["id"]), json=change)

    assert response.status_code == 422
    assert shape(client, blocks) == before


# ---------- conflicts ----------


def test_a_conflict_with_another_block_is_reported_and_nothing_changes(
    client, db_session, login
):
    user = login()
    blocks = make_series(client)
    existing = add_block(db_session, user, utc(12, 30, day=12))
    before = shape(client, blocks)

    response = client.patch(
        following_url(blocks[2]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["total_conflicting_blocks"] == 1
    assert [c["id"] for c in detail["blocks"][0]["conflicts"]] == [str(existing.id)]
    assert moment(detail["blocks"][0], "starts_at") == utc(12, day=12)
    assert shape(client, blocks) == before


def test_a_confirmed_conflict_is_saved(client, db_session, login):
    user = login()
    blocks = make_series(client)
    existing = add_block(db_session, user, utc(12, 30, day=12))

    response = client.patch(
        following_url(blocks[2]["id"]),
        params={"allow_conflicts": "true"},
        json={"start_time": "12:00"},
    )

    assert response.status_code == 200
    found = [item["conflicting_block_ids"] for item in response.json()]
    assert found == [[str(existing.id)], [], []]
    assert moment(response.json()[0], "starts_at") == utc(12, day=12)


def test_changed_blocks_can_conflict_with_each_other(client, db_session, login):
    user = login()
    series_id = uuid4()
    first = add_block(db_session, user, utc(9), series_id=series_id)
    second = add_block(db_session, user, utc(11), series_id=series_id)

    refused = client.patch(following_url(first.id), json={"duration_minutes": 180})

    assert refused.status_code == 409
    assert refused.json()["detail"]["total_conflicting_blocks"] == 2
    db_session.refresh(first)
    db_session.refresh(second)
    assert (first.starts_at, first.ends_at) == (utc(9), utc(10))
    assert (second.starts_at, second.ends_at) == (utc(11), utc(12))

    confirmed = client.patch(
        following_url(first.id),
        params={"allow_conflicts": "true"},
        json={"duration_minutes": 180},
    )

    assert confirmed.status_code == 200
    assert [moment(item, "ends_at") for item in confirmed.json()] == [
        utc(12),
        utc(14),
    ]


def test_a_block_does_not_conflict_with_its_own_old_position(client, login):
    login()
    blocks = make_series(client)

    response = client.patch(
        following_url(blocks[4]["id"]),
        json={"start_time": "10:30"},
    )

    assert response.status_code == 200
    assert response.json()[0]["conflicting_block_ids"] == []


def test_the_warning_lists_at_most_ten_blocks(client, db_session, login):
    user = login()
    blocks = make_series(client, last_date="2026-11-21")
    for day in range(10, 22):
        add_block(db_session, user, utc(12, 30, day=day))
    before = shape(client, blocks)

    response = client.patch(
        following_url(blocks[0]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["total_conflicting_blocks"] == 12
    assert len(detail["blocks"]) == 10
    assert shape(client, blocks) == before


def test_skipped_blocks_are_not_a_conflict(client, db_session, login):
    user = login()
    blocks = make_series(client)
    add_block(db_session, user, utc(12, 30, day=12), status="skipped")

    response = client.patch(
        following_url(blocks[2]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 200


# ---------- time zones and clock changes ----------


def test_the_same_clock_time_is_kept_when_the_clocks_change(client, login):
    login("Europe/Berlin")
    blocks = make_series(
        client,
        first_date="2026-10-24",
        last_date="2026-10-26",
        start_time="09:00",
    )

    response = client.patch(
        following_url(blocks[0]["id"]),
        json={"start_time": "10:00"},
    )

    assert [moment(item, "starts_at").astimezone(UTC) for item in response.json()] == [
        utc(8, day=24, month=10),
        utc(9, day=25, month=10),
        utc(9, day=26, month=10),
    ]


def test_the_local_date_follows_the_current_profile_timezone(client, db_session, login):
    user = login("Asia/Tokyo")
    block = add_block(db_session, user, utc(23, 30), series_id=uuid4())

    response = client.patch(following_url(block.id), json={"start_time": "09:00"})

    assert response.status_code == 200
    assert moment(response.json()[0], "starts_at") == utc(0, day=11)
    assert moment(response.json()[0], "ends_at") == utc(1, day=11)


# ---------- all or nothing ----------


def test_an_error_while_checking_changes_nothing(client, login, monkeypatch):
    login()
    blocks = make_series(client)
    before = shape(client, blocks)
    real_find_conflicts = series_service.find_conflicts
    calls = []

    def failing_find_conflicts(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Something broke in the middle")
        return real_find_conflicts(*args, **kwargs)

    monkeypatch.setattr(series_service, "find_conflicts", failing_find_conflicts)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.patch(
        following_url(blocks[0]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 500
    assert len(calls) == 2
    assert shape(client, blocks) == before


def test_an_error_while_saving_rolls_back(client, db_session, login, monkeypatch):
    login()
    blocks = make_series(client)
    rollback = Mock()

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.patch(
        following_url(blocks[0]["id"]),
        json={"start_time": "12:00"},
    )

    assert response.status_code == 500
    rollback.assert_called_once()


def test_changing_the_following_blocks_requires_authentication(client):
    response = client.patch(following_url(uuid4()), json={"start_time": "12:00"})

    assert response.status_code == 401


# ---------- deleting the block and the following ones ----------


def test_the_selected_and_the_following_blocks_are_deleted(client, db_session, login):
    user = login()
    blocks = make_series(client)

    response = client.delete(following_url(blocks[2]["id"]))

    assert response.status_code == 200
    assert response.json() == {"deleted_blocks": 3}
    assert count_blocks(db_session, user) == 2
    for kept in blocks[:2]:
        assert client.get(f"{BLOCKS_URL}{kept['id']}").status_code == 200


def test_completed_and_skipped_blocks_are_not_deleted(client, db_session, login):
    user = login()
    blocks = make_series(client)
    client.patch(f"{BLOCKS_URL}{blocks[2]['id']}", json={"status": "skipped"})
    client.patch(f"{BLOCKS_URL}{blocks[3]['id']}", json={"status": "completed"})

    response = client.delete(following_url(blocks[2]["id"]))

    assert response.json() == {"deleted_blocks": 1}
    assert count_blocks(db_session, user) == 4


def test_deleting_when_nothing_is_left_is_not_an_error(client, login):
    login()
    blocks = make_series(client)
    client.patch(f"{BLOCKS_URL}{blocks[4]['id']}", json={"status": "skipped"})

    response = client.delete(following_url(blocks[4]["id"]))

    assert response.status_code == 200
    assert response.json() == {"deleted_blocks": 0}


def test_other_series_are_not_deleted(client, db_session, login):
    user = login()
    blocks = make_series(client)
    make_series(client, start_time="15:00")

    client.delete(following_url(blocks[0]["id"]))

    assert count_blocks(db_session, user) == 5


def test_tasks_and_subjects_stay_when_blocks_are_deleted(client, db_session, login):
    user = login()
    subject = Subject(name="Physics", user_id=user.id)
    db_session.add(subject)
    db_session.flush()
    blocks = make_series(client, subject_id=str(subject.id))
    task = client.post(TASKS_URL, json={"title": "Lab report"}).json()
    task_blocks = make_series(client, task_id=task["id"], start_time="15:00")

    client.delete(following_url(blocks[0]["id"]))
    client.delete(following_url(task_blocks[0]["id"]))

    assert client.get(f"{SUBJECTS_URL}{subject.id}").status_code == 200
    assert client.get(f"{TASKS_URL}{task['id']}").status_code == 200


def test_deleting_a_block_that_is_not_in_a_series_is_refused(client, db_session, login):
    user = login()
    single = add_block(db_session, user, utc(10))

    response = client.delete(following_url(single.id))

    assert response.status_code == 422
    assert response.json()["detail"] == "The block is not part of a series"
    assert count_blocks(db_session, user) == 1


def test_another_users_blocks_cannot_be_deleted(client, db_session, login):
    login()
    stranger = make_stranger(db_session)
    foreign = add_block(db_session, stranger, utc(10), series_id=uuid4())

    response = client.delete(following_url(foreign.id))

    assert response.status_code == 404
    assert count_blocks(db_session, stranger) == 1


def test_deleting_a_missing_block_is_not_found(client, login):
    login()

    response = client.delete(following_url(uuid4()))

    assert response.status_code == 404


def test_deleting_rolls_back_on_commit_error(client, db_session, login, monkeypatch):
    login()
    blocks = make_series(client)
    rollback = Mock()

    def fail_commit():
        raise RuntimeError("Database commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", rollback)
    test_client = TestClient(app, raise_server_exceptions=False)

    response = test_client.delete(following_url(blocks[0]["id"]))

    assert response.status_code == 500
    rollback.assert_called_once()


def test_deleting_the_following_blocks_requires_authentication(client):
    response = client.delete(following_url(uuid4()))

    assert response.status_code == 401
