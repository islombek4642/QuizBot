from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import json

from core.config import settings
from constants.messages import Messages
from models.user import User
from models.quiz import Quiz
from models.session import QuizSession
from services.user_service import UserService
from core.logger import logger

router = Router()
# Only allow admin to use these handlers
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)

@router.message(F.text.in_([Messages.get("ADMIN_USERS_BTN", "UZ"), Messages.get("ADMIN_USERS_BTN", "EN")]))
async def admin_list_users(message: types.Message, db: AsyncSession, user_service: UserService):
    lang = await user_service.get_language(message.from_user.id)
    await show_users_page(message, db, lang, page=0)

async def show_users_page(message_or_query, db: AsyncSession, lang: str, page: int):
    limit = 10
    offset = page * limit
    
    # Get total count
    total_result = await db.execute(select(func.count(User.id)))
    total_users = total_result.scalar()
    
    # Get users for page
    result = await db.execute(select(User).offset(offset).limit(limit).order_by(User.id.desc()))
    users = result.scalars().all()
    
    text = Messages.get("ADMIN_USERS_TITLE", lang).format(total=total_users) + "\n\n"
    
    builder = InlineKeyboardBuilder()
    for i, user in enumerate(users, 1 + offset):
        if user.username:
            text += f"{i}. <a href='https://t.me/{user.username}'>{name}</a>\n"
        else:
            text += f"{i}. <a href='tg://user?id={user.telegram_id}'>{name}</a> (ID: {user.telegram_id})\n"
        
    text += "\n" + Messages.get("ADMIN_PAGE", lang).format(page=page+1, total=(total_users + limit - 1) // limit)
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text=Messages.get("PREV_BTN", lang), callback_data=f"admin_users_page_{page-1}"))
    if offset + limit < total_users:
        nav_buttons.append(types.InlineKeyboardButton(text=Messages.get("NEXT_BTN", lang), callback_data=f"admin_users_page_{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
        
    if isinstance(message_or_query, types.Message):
        await message_or_query.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML", link_preview_options=types.LinkPreviewOptions(is_disabled=True))
    else:
        await message_or_query.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML", link_preview_options=types.LinkPreviewOptions(is_disabled=True))

@router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_pagination(callback: types.CallbackQuery, db: AsyncSession, user_service: UserService):
    page = int(callback.data.split("_")[-1])
    lang = await user_service.get_language(callback.from_user.id)
    await show_users_page(callback, db, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_GROUPS_BTN", "UZ"), Messages.get("ADMIN_GROUPS_BTN", "EN")]))
async def admin_list_groups(message: types.Message, redis, user_service: UserService):
    lang = await user_service.get_language(message.from_user.id)
    await show_groups_page(message, redis, lang, page=0)

async def show_groups_page(message_or_query, redis, lang: str, page: int):
    GROUP_MEMBERS_KEY = "bot_groups"
    limit = 10
    offset = page * limit
    
    # Redis smembers doesn't support offset/limit natively easily for small sets
    # Get all and slice
    all_groups = await redis.smembers(GROUP_MEMBERS_KEY)
    total_groups = len(all_groups)
    groups_slice = list(all_groups)[offset:offset+limit]
    
    text = Messages.get("ADMIN_GROUPS_TITLE", lang).format(total=total_groups) + "\n\n"
    
    builder = InlineKeyboardBuilder()
    for i, group_id in enumerate(groups_slice, 1 + offset):
        info = await redis.hgetall(f"group_info:{group_id}")
        title = info.get("title") or f"Group {group_id}"
        username = info.get("username")
        
        if username:
            text += f"{i}. <a href='https://t.me/{username}'>{title}</a>\n"
        else:
            # Cannot link to private group easily without invite link
            text += f"{i}. <b>{title}</b> (ID: {group_id})\n"
        
    text += "\n" + Messages.get("ADMIN_PAGE", lang).format(page=page+1, total=(total_groups + limit - 1) // limit if total_groups > 0 else 1)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text=Messages.get("PREV_BTN", lang), callback_data=f"admin_groups_page_{page-1}"))
    if offset + limit < total_groups:
        nav_buttons.append(types.InlineKeyboardButton(text=Messages.get("NEXT_BTN", lang), callback_data=f"admin_groups_page_{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
        
    if isinstance(message_or_query, types.Message):
        await message_or_query.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML", link_preview_options=types.LinkPreviewOptions(is_disabled=True))
    else:
        await message_or_query.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML", link_preview_options=types.LinkPreviewOptions(is_disabled=True))

@router.callback_query(F.data.startswith("admin_groups_page_"))
async def admin_groups_pagination(callback: types.CallbackQuery, redis, user_service: UserService):
    page = int(callback.data.split("_")[-1])
    lang = await user_service.get_language(callback.from_user.id)
    await show_groups_page(callback, redis, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_STATS_BTN", "UZ"), Messages.get("ADMIN_STATS_BTN", "EN")]))
async def admin_statistics(message: types.Message, db: AsyncSession, redis, user_service: UserService):
    lang = await user_service.get_language(message.from_user.id)
    
    # Users count
    res_users = await db.execute(select(func.count(User.id)))
    total_users = res_users.scalar()
    
    # Groups count
    total_groups = await redis.scard("bot_groups")
    
    # Quizzes count
    res_quizzes = await db.execute(select(func.count(Quiz.id)))
    total_quizzes = res_quizzes.scalar()
    
    # Active quizzes (Group)
    # Get all keys starting with group_quiz:
    # Note: keys() is slow on large redis, but fine here
    keys = await redis.keys("group_quiz:*")
    active_group_quizzes = len(keys)
    
    # Active sessions (Private)
    res_active_sessions = await db.execute(select(func.count(QuizSession.id)).filter(QuizSession.is_active == True))
    active_private_quizzes = res_active_sessions.scalar()
    
    total_active = active_group_quizzes + active_private_quizzes
    
    stats_msg = Messages.get("ADMIN_STATS_MSG", lang).format(
        total_users=total_users,
        total_groups=total_groups,
        total_quizzes=total_quizzes,
        active_quizzes=total_active
    )
    
    await message.answer(stats_msg, parse_mode="HTML")
