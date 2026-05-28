from fastapi import APIRouter, HTTPException, status

from ..auth import create_jwt, upsert_user, verify_init_data
from ..models import AuthResponse, AuthTelegramRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthResponse)
async def auth_telegram(body: AuthTelegramRequest):
    """
    Verify Telegram WebApp initData and return a JWT.
    Called once when the Mini App opens.
    """
    try:
        tg_user = verify_init_data(body.init_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user = await upsert_user(tg_user)
    token = create_jwt(user["id"], user["telegram_id"])

    return AuthResponse(
        access_token=token,
        user=UserOut(**user),
    )
