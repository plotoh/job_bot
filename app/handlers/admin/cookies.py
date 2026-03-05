import os
import tempfile
import http.cookiejar
import logging
from datetime import datetime

from aiogram import types, F, Router, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, FSInputFile

from app.fsm.states import AdminEditStates
from app.database.models import AsyncSessionLocal, Account
from app.handlers.admin.common import show_account_menu

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_upload_cookies")
async def upload_cookies_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📤 Отправьте файл с cookies в формате Netscape (cookies.txt).\n\n"
        "Как получить такой файл:\n"
        "1. Установите расширение 'Get cookies.txt' для Chrome/Edge.\n"
        "2. Зайдите на hh.ru, выполните вход.\n"
        "3. Нажмите на иконку расширения и выберите 'Export'.\n"
        "4. Пришлите полученный файл сюда."
    )
    await state.set_state(AdminEditStates.waiting_cookies_file)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.waiting_cookies_file), F.document)
async def upload_cookies_file(message: Message, state: FSMContext, bot: Bot):
    document = message.document
    if not document.file_name.endswith('.txt'):
        await message.answer("❌ Пожалуйста, отправьте файл с расширением .txt")
        return

    file = await bot.get_file(document.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
        await bot.download_file(file.file_path, tmp.name)
        tmp_path = tmp.name

    try:
        jar = http.cookiejar.MozillaCookieJar(tmp_path)
        jar.load(ignore_discard=True, ignore_expires=True)
        cookies_dict = {cookie.name: cookie.value for cookie in jar}
    except Exception as e:
        await message.answer(f"❌ Ошибка при парсинге файла: {e}")
        logger.error("Cookie parsing error: %s", e, exc_info=True)
        os.unlink(tmp_path)
        return
    finally:
        os.unlink(tmp_path)

    data = await state.get_data()
    account_id = data.get("account_id")
    if not account_id:
        await message.answer("❌ Аккаунт не выбран")
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            await message.answer("❌ Аккаунт не найден")
            await state.clear()
            return
        account.cookies = cookies_dict
        account.cookies_updated_at = datetime.utcnow()
        await session.commit()

    await message.answer(f"✅ Cookies успешно загружены. Сохранено {len(cookies_dict)} записей.")
    logger.info("Admin uploaded cookies for account %d", account_id)

    await show_account_menu(message, account_id, state)


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_download_cookies")
async def download_cookies(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    account_id = data.get("account_id")
    if not account_id:
        await callback.answer("Аккаунт не выбран", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account or not account.cookies:
            await callback.answer("Нет cookies для экспорта", show_alert=True)
            return
        cookies_dict = account.cookies

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp:
        jar = http.cookiejar.MozillaCookieJar(tmp.name)
        for name, value in cookies_dict.items():
            cookie = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=".hh.ru",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False
            )
            jar.set_cookie(cookie)
        jar.save(ignore_discard=True, ignore_expires=True)
        tmp_path = tmp.name

    await callback.message.answer_document(
        FSInputFile(tmp_path),
        caption=f"Cookies для аккаунта {account.username} (формат Netscape)"
    )
    os.unlink(tmp_path)
    await callback.answer()
    logger.info("Admin downloaded cookies for account %d", account_id)
