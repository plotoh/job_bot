from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from app.fsm.states import AdminChannelStates  # нужно создать новые состояния
from app.database.models import AsyncSessionLocal, TelegramChannel, Account
from app.services.account_crud import get_all_accounts

router = Router()


# Список каналов
@router.callback_query(F.data == "admin_channels")
async def list_channels(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        channels = await session.execute(select(TelegramChannel))
        channels = channels.scalars().all()
    text = "📢 Управление каналами:\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel")]
    ])
    for ch in channels:
        text += f"• {ch.title} (ID: {ch.id}) – {'✅' if ch.is_active else '❌'}\n"
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"✏️ {ch.title}",
            callback_data=f"admin_edit_channel_{ch.id}"
        )])
    await callback.message.edit_text(text, reply_markup=kb)


# Добавление канала
@router.callback_query(F.data == "admin_add_channel")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите ID канала (целое число):")
    await state.set_state(AdminChannelStates.waiting_channel_id)


@router.message(AdminChannelStates.waiting_channel_id, F.text)
async def add_channel_id(message: Message, state: FSMContext):
    try:
        channel_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    await state.update_data(channel_id=channel_id)
    await message.answer("Введите название канала:")
    await state.set_state(AdminChannelStates.waiting_channel_title)


@router.message(AdminChannelStates.waiting_channel_title, F.text)
async def add_channel_title(message: Message, state: FSMContext):
    title = message.text
    data = await state.get_data()
    channel_id = data['channel_id']
    async with AsyncSessionLocal() as session:
        # Проверяем, есть ли уже
        existing = await session.get(TelegramChannel, channel_id)
        if existing:
            await message.answer("❌ Канал с таким ID уже существует.")
            await state.clear()
            return
        channel = TelegramChannel(id=channel_id, title=title, is_active=True)
        session.add(channel)
        await session.commit()
    await message.answer(f"✅ Канал «{title}» добавлен!")
    # Вернуться к списку каналов
    await list_channels(message, state)  # нужно реализовать функцию, которая принимает update


# Редактирование канала (изменение названия, активности, управление доступом пользователей)
@router.callback_query(F.data.startswith("admin_edit_channel_"))
async def edit_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[3])
    await state.update_data(channel_id=channel_id)
    async with AsyncSessionLocal() as session:
        channel = await session.get(TelegramChannel, channel_id)
        # Получаем всех пользователей, у которых есть доступ
        users = await session.execute(select(Account))
        users = users.scalars().all()
    text = f"Канал: {channel.title}\nID: {channel.id}\nАктивен: {'✅' if channel.is_active else '❌'}\n\n"
    text += "Пользователи с доступом:\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить активность", callback_data="admin_channel_toggle")],
        [InlineKeyboardButton(text="👥 Управление доступом", callback_data="admin_channel_users")],
        [InlineKeyboardButton(text="❌ Удалить канал", callback_data="admin_channel_delete")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_channels")]
    ])
    for user in users:
        has_access = channel in user.channels
        text += f"{'✅' if has_access else '❌'} {user.username} (ID: {user.id})\n"
    await callback.message.edit_text(text, reply_markup=kb)

# Далее реализовать переключение активности, управление доступом (добавление/удаление связей)
