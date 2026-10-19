import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from voiceos.api.deps import AuthContext, DbSession, require_role, require_writer
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.domain.phone import normalize_vn_phone
from voiceos.models import Contact
from voiceos.services import enqueue, find_idempotent, paginate, record_audit, store_idempotent

router = APIRouter(prefix="/contacts", tags=["contacts"])

Reader = Annotated[AuthContext, Depends(require_role("auditor"))]
Writer = Annotated[AuthContext, Depends(require_writer("staff"))]


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=64)
    need: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID | None = None


class ContactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    need: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID | None = None
    lifecycle: str | None = Field(default=None, max_length=32)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    phone_raw: str
    normalized_phone: str | None
    phone_status: str
    owner_id: uuid.UUID | None
    lifecycle: str
    need: str | None
    optout_at: datetime | None
    version: int
    created_at: datetime


def _get_owned(db, auth: AuthContext, contact_id: uuid.UUID) -> Contact:
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.tenant_id == auth.tenant_id))
    if contact is None:  # also for other tenants' ids: never confirm existence (AC01)
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy khách hàng")
    return contact


@router.get("")
def list_contacts(
    auth: Reader,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    phone: str | None = None,
):
    stmt = select(Contact).where(Contact.tenant_id == auth.tenant_id)
    if phone:
        normalized = normalize_vn_phone(phone)
        stmt = stmt.where(Contact.normalized_phone == (normalized.e164 or "__none__"))
    rows, next_cursor = paginate(db, stmt, Contact, limit=limit, cursor=cursor)
    return {
        "items": [ContactOut.model_validate(r).model_dump(mode="json") for r in rows],
        "next_cursor": next_cursor,
        "trace_id": trace_id_var.get(),
    }


@router.post("", status_code=201)
def create_contact(
    body: ContactIn,
    auth: Writer,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    payload = body.model_dump(mode="json")
    replay = find_idempotent(
        db, tenant_id=auth.tenant_id, key=idempotency_key, operation="createContact", payload=payload
    )
    if replay:
        return JSONResponse(status_code=replay[0], content=replay[1])

    phone = normalize_vn_phone(body.phone)
    contact = Contact(
        tenant_id=auth.tenant_id,
        name=body.name,
        phone_raw=body.phone,
        normalized_phone=phone.e164,
        phone_status=phone.status,
        need=body.need,
        owner_id=body.owner_id,
    )
    db.add(contact)
    db.flush()
    out = ContactOut.model_validate(contact).model_dump(mode="json")
    record_audit(
        db, tenant_id=auth.tenant_id, actor_user_id=auth.user_id, obj=contact, action="create", after=out
    )
    enqueue(db, tenant_id=auth.tenant_id, topic="contact.created", payload={"contact_id": str(contact.id)})
    response = {"data": out, "phone_check": {"status": phone.status, "reason": phone.reason}}
    store_idempotent(
        db,
        tenant_id=auth.tenant_id,
        key=idempotency_key,
        operation="createContact",
        payload=payload,
        status=201,
        body=response,
    )
    db.commit()
    return {**response, "trace_id": trace_id_var.get()}


@router.get("/{contact_id}")
def get_contact(contact_id: uuid.UUID, auth: Reader, db: DbSession):
    return {"data": ContactOut.model_validate(_get_owned(db, auth, contact_id)).model_dump(mode="json")}


@router.patch("/{contact_id}")
def update_contact(
    contact_id: uuid.UUID,
    body: ContactPatch,
    auth: Writer,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
):
    if if_match is None:
        raise ApiError(428, "IF_MATCH_REQUIRED", "Cần header If-Match với version hiện tại")
    contact = _get_owned(db, auth, contact_id)
    if str(contact.version) != if_match.strip('"'):
        raise ApiError(409, "VERSION_CONFLICT", "Dữ liệu đã được người khác cập nhật, tải lại để tiếp tục")
    before = ContactOut.model_validate(contact).model_dump(mode="json")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    contact.version += 1
    db.flush()
    after = ContactOut.model_validate(contact).model_dump(mode="json")
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=contact,
        action="update",
        before=before,
        after=after,
    )
    db.commit()
    return {"data": after, "trace_id": trace_id_var.get()}
