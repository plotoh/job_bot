from aiogram.fsm.state import State, StatesGroup


# Общее состояние для редактирования полей (используется и админом, и пользователем)
class CommonEditStates(StatesGroup):
    waiting_value = State()  # ожидание ввода значения


# Состояния для администратора
class AdminEditStates(StatesGroup):
    choosing_account = State()   # выбор аккаунта из списка
    choosing_action = State()    # выбор действия над аккаунтом
    # Удаляем все состояния для конкретных полей – они заменены CommonEditStates


# Состояния для пользователя
class UserSettingsStates(StatesGroup):
    choosing_field = State()     # выбор поля для редактирования

    waiting_username = State()
    waiting_password = State()


class UserTestStates(StatesGroup):
    main_menu = State()
    waiting_count = State()


class AdminChannelStates(StatesGroup):
    waiting_channel_id = State()
    waiting_channel_title = State()