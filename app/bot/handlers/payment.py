import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import User, Plan
from app.services.payment import record_payment_receipt
from app.bot.states.states import ReceiptState, WalletTopUpState
from app.bot.keyboards.default import get_main_menu_keyboard
from app.bot.utils.texts import get_receipt_pending_text

logger = logging.getLogger(__name__)
router = Router(name="payment")


@router.message(ReceiptState.waiting_for_photo, F.photo)
async def handle_plan_receipt_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    is_admin: bool,
):
    """Receive receipt photo for plan purchase."""
    photo_file_id = message.photo[-1].file_id
    state_data = await state.get_data()
    plan_id = state_data.get("plan_id")
    amount = state_data.get("amount", 0)
    payment_type = state_data.get("payment_type", "plan_purchase")

    plan = None
    if plan_id:
        plan_res = await session.execute(select(Plan).where(Plan.id == plan_id))
        plan = plan_res.scalar_one_or_none()

    receipt = await record_payment_receipt(
        bot=message.bot,
        session=session,
        user=db_user,
        photo_file_id=photo_file_id,
        amount=amount,
        payment_type=payment_type,
        plan=plan,
    )

    await state.clear()
    kb = get_main_menu_keyboard(is_admin=is_admin)
    await message.answer(get_receipt_pending_text(receipt.id), reply_markup=kb)


@router.message(WalletTopUpState.waiting_for_photo, F.photo)
async def handle_wallet_receipt_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    is_admin: bool,
):
    """Receive receipt photo for wallet balance top-up."""
    photo_file_id = message.photo[-1].file_id
    state_data = await state.get_data()
    amount = state_data.get("amount", 0)

    receipt = await record_payment_receipt(
        bot=message.bot,
        session=session,
        user=db_user,
        photo_file_id=photo_file_id,
        amount=amount,
        payment_type="wallet_topup",
        plan=None,
    )

    await state.clear()
    kb = get_main_menu_keyboard(is_admin=is_admin)
    await message.answer(get_receipt_pending_text(receipt.id), reply_markup=kb)


@router.message(ReceiptState.waiting_for_photo)
@router.message(WalletTopUpState.waiting_for_photo)
async def handle_non_photo_receipt(message: Message):
    """Remind user to send an actual photo of the receipt."""
    await message.answer(
        "⚠️ لطفاً رسید واریز را به صورت **عکس (Photo)** ارسال نمایید یا در صورت انصراف، دکمه «❌ انصراف و بازگشت» را لمس کنید."
    )
