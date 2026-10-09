from aiogram.fsm.state import State, StatesGroup


class ReceiptState(StatesGroup):
    waiting_for_photo = State()


class WalletTopUpState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_photo = State()


class AdminAddPlanState(StatesGroup):
    waiting_for_title = State()
    waiting_for_traffic = State()
    waiting_for_duration = State()
    waiting_for_price = State()
    waiting_for_description = State()


class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()


class AdminUserManageState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_balance = State()


class AdminRejectReceiptState(StatesGroup):
    waiting_for_reason = State()


class AdminManageAdminState(StatesGroup):
    waiting_for_admin_id = State()

