from aiogram.fsm.state import State, StatesGroup


# Состояния для администратора
class AdminEditStates(StatesGroup):
    choosing_account = State()
    choosing_action = State()
    editing_filter = State()
    editing_resume = State()
    editing_proxy = State()
    editing_limit = State()
    editing_limit_range = State()
    editing_interval_range = State()
    editing_work_hours = State()
    editing_prompt = State()


class AdminAddAccountStates(StatesGroup):
    waiting_telegram_id = State()
    waiting_username = State()
    waiting_password = State()
    waiting_resume_id = State()
    waiting_proxy = State()
    waiting_filter_url = State()
    waiting_filter_pages = State()


# Состояния для пользователя
class UserSettingsStates(StatesGroup):
    choosing_field = State()
    waiting_username = State()
    waiting_password = State()
    waiting_proxy = State()
    waiting_resume = State()
    waiting_filter = State()


class UserTestStates(StatesGroup):
    main_menu = State()
    waiting_count = State()
