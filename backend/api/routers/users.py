from fastapi import APIRouter, Depends

from ..auth import CurrentUser, get_current_user
from ..database import get_conn
from ..models import UserOut, UserTenantOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current: CurrentUser = Depends(get_current_user)):
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id, telegram_id, username, first_name, created_at FROM users WHERE id = $1",
            current.user_id,
        )
    return UserOut(**dict(row))


@router.get("/me/tenants", response_model=list[UserTenantOut])
async def get_my_tenants(current: CurrentUser = Depends(get_current_user)):
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT ut.tenant_id, t.name AS tenant_name, ut.role,
                   ut.sub_status, ut.sub_expires_at
            FROM user_tenants ut
            JOIN tenants t ON t.id = ut.tenant_id
            WHERE ut.user_id = $1
            ORDER BY ut.joined_at
            """,
            current.user_id,
        )
    return [UserTenantOut(**dict(r)) for r in rows]
