"""Announcement endpoints for the High School Management System API."""

from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(prefix="/announcements", tags=["announcements"])


class AnnouncementPayload(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    expiration_date: date
    start_date: Optional[date] = None


def require_teacher(teacher_username: Optional[str]) -> None:
    if not teacher_username or not teachers_collection.find_one({"_id": teacher_username}):
        raise HTTPException(status_code=401, detail="Authentication required")


def validate_dates(payload: AnnouncementPayload) -> None:
    if payload.start_date and payload.start_date > payload.expiration_date:
        raise HTTPException(
            status_code=422,
            detail="Start date must be on or before expiration date",
        )


def to_datetime(value: Optional[date], end_of_day: bool = False) -> Optional[datetime]:
    if value is None:
        return None
    chosen_time = time.max if end_of_day else time.min
    return datetime.combine(value, chosen_time, tzinfo=timezone.utc)


def serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "message": document["message"],
        "start_date": document.get("start_date"),
        "expiration_date": document["expiration_date"],
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements active today for the public banner."""
    now = datetime.now(timezone.utc)
    query = {
        "expiration_date": {"$gte": now},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": now}},
            {"start_date": {"$exists": False}},
        ],
    }
    return [serialize_announcement(item) for item in announcements_collection.find(query)]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """Return every announcement for authenticated management."""
    require_teacher(teacher_username)
    items = announcements_collection.find({}).sort("expiration_date", -1)
    return [serialize_announcement(item) for item in items]


@router.post("", status_code=201, response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    require_teacher(teacher_username)
    validate_dates(payload)
    now = datetime.now(timezone.utc)
    document = {
        "message": payload.message.strip(),
        "start_date": to_datetime(payload.start_date),
        "expiration_date": to_datetime(payload.expiration_date, end_of_day=True),
        "created_at": now,
        "updated_at": now,
    }
    result = announcements_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_announcement(document)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    require_teacher(teacher_username)
    validate_dates(payload)
    if not ObjectId.is_valid(announcement_id):
        raise HTTPException(status_code=404, detail="Announcement not found")

    changes = {
        "message": payload.message.strip(),
        "start_date": to_datetime(payload.start_date),
        "expiration_date": to_datetime(payload.expiration_date, end_of_day=True),
        "updated_at": datetime.now(timezone.utc),
    }
    result = announcements_collection.update_one(
        {"_id": ObjectId(announcement_id)}, {"$set": changes}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    document = announcements_collection.find_one({"_id": ObjectId(announcement_id)})
    return serialize_announcement(document)


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None),
) -> None:
    require_teacher(teacher_username)
    if not ObjectId.is_valid(announcement_id):
        raise HTTPException(status_code=404, detail="Announcement not found")
    result = announcements_collection.delete_one({"_id": ObjectId(announcement_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")