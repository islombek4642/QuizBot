from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import json
import time
from typing import List, Any

from core.config import settings
from constants.messages import Messages
from models.user import User
from models.group import Group
from models.quiz import Quiz
from models.session import QuizSession
from services.user_service import UserService
from services.group_service import GroupService
from core.logger import logger
from handlers.common import QuizStates, get_main_keyboard, get_admin_ai_keyboard, get_cancel_keyboard
from aiogram.fsm.context import FSMContext

router = Router()
# Only allow admin to use these handlers
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)

@router.message(F.text.in_([Messages.get("ADMIN_USERS_BTN", "UZ"), Messages.get("ADMIN_USERS_BTN", "EN")]))
async def admin_list_users(message: types.Message, db: AsyncSession, lang: str):
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
        # Consistently show Name, ID and Phone
        name = user.full_name or (f"@{user.username}" if user.username else "Noma'lum foydalanuvchi")
        phone = f" — <code>{user.phone_number}</code>" if user.phone_number else " — [Raqamsiz]"
        id_info = f" (<code>{user.telegram_id}</code>)"
        
        if user.username:
            text += f"{i}. <a href='https://t.me/{user.username}'>{name}</a>{id_info}{phone}\n"
        else:
            text += f"{i}. <a href='tg://user?id={user.telegram_id}'>{name}</a>{id_info}{phone}\n"
        
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
async def admin_users_pagination(callback: types.CallbackQuery, db: AsyncSession, lang: str):
    page = int(callback.data.split("_")[-1])
    await show_users_page(callback, db, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_GROUPS_BTN", "UZ"), Messages.get("ADMIN_GROUPS_BTN", "EN")]))
async def admin_list_groups(message: types.Message, db: AsyncSession, lang: str):
    await show_groups_page(message, db, lang, page=0)

async def show_groups_page(message_or_query, db: AsyncSession, lang: str, page: int):
    limit = 10
    offset = page * limit
    
    # Get total count
    total_result = await db.execute(select(func.count(Group.id)))
    total_groups = total_result.scalar()
    
    # Get groups for page
    result = await db.execute(select(Group).offset(offset).limit(limit).order_by(Group.id.desc()))
    groups = result.scalars().all()
    
    text = Messages.get("ADMIN_GROUPS_TITLE", lang).format(total=total_groups) + "\n\n"
    
    builder = InlineKeyboardBuilder()
    for i, group in enumerate(groups, 1 + offset):
        title = group.title or f"Group {group.telegram_id}"
        username = group.username
        
        if username:
            text += f"{i}. <a href='https://t.me/{username}'>{title}</a> (ID: {group.telegram_id})\n"
        else:
            text += f"{i}. <b>{title}</b> (ID: {group.telegram_id})\n"
        
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
async def admin_groups_pagination(callback: types.CallbackQuery, db: AsyncSession, lang: str):
    page = int(callback.data.split("_")[-1])
    await show_groups_page(callback, db, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_STATS_BTN", "UZ"), Messages.get("ADMIN_STATS_BTN", "EN")]))
async def admin_statistics(message: types.Message, db: AsyncSession, redis, lang: str):
    # Users count
    res_users = await db.execute(select(func.count(User.id)))
    total_users = res_users.scalar()
    
    # Groups count
    res_groups = await db.execute(select(func.count(Group.id)))
    total_groups = res_groups.scalar()
    
    # Quizzes count
    res_quizzes = await db.execute(select(func.count(Quiz.id)))
    total_quizzes = res_quizzes.scalar()
    
    # Active quizzes (Group) - Redis keys with 4h TTL
    keys = await redis.keys("group_quiz:*")
    active_group_quizzes = len(keys)
    
    # Active sessions (Private) - Only count recent ones (last 2 hours) to avoid stale data
    two_hours_ago = time.time() - 7200
    res_active_sessions = await db.execute(
        select(func.count(QuizSession.id))
        .filter(QuizSession.is_active == True, QuizSession.start_time > two_hours_ago)
    )
    active_private_quizzes = res_active_sessions.scalar()
    
    total_active = active_group_quizzes + active_private_quizzes

    # AI Stats
    ai_gen_total = await redis.get("stats:ai_gen_total") or 0
    ai_conv_total = await redis.get("stats:ai_conv_total") or 0
    
    stats_msg = Messages.get("ADMIN_STATS_MSG", lang).format(
        total_users=total_users,
        total_groups=total_groups,
        total_quizzes=total_quizzes,
        active_quizzes=total_active,
        active_groups=active_group_quizzes,
        active_private=active_private_quizzes,
        ai_gen_total=int(ai_gen_total),
        ai_conv_total=int(ai_conv_total)
    )
    
    await message.answer(stats_msg, parse_mode="HTML")

# ===================== AI SETTINGS =====================

@router.message(F.text.in_([Messages.get("ADMIN_AI_SETTINGS_BTN", "UZ"), Messages.get("ADMIN_AI_SETTINGS_BTN", "EN")]))
async def admin_ai_settings(message: types.Message, state: FSMContext, redis, lang: str, success_msg: str = None):
    # Get current limits from Redis or use defaults
    gen_limit = await redis.get("global_settings:ai_gen_limit")
    conv_limit = await redis.get("global_settings:ai_conv_limit")
    
    gen_limit = int(gen_limit) if gen_limit else settings.AI_GENERATION_COOLDOWN_HOURS
    conv_limit = int(conv_limit) if conv_limit else settings.AI_CONVERSION_COOLDOWN_HOURS
    
    text = Messages.get("ADMIN_AI_SETTINGS_TITLE", lang).format(
        gen_limit=gen_limit,
        conv_limit=conv_limit
    )
    
    if success_msg:
        text = f"{success_msg}\n\n{text}"
    
    await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
    await message.answer(text, reply_markup=get_admin_ai_keyboard(lang), parse_mode="HTML")

@router.message(QuizStates.ADMIN_AI_SETTINGS, F.text.in_([Messages.get("ADMIN_SET_GEN_LIMIT_BTN", "UZ"), Messages.get("ADMIN_SET_GEN_LIMIT_BTN", "EN")]))
async def admin_prompt_gen_limit(message: types.Message, state: FSMContext, lang: str):
    await state.set_state(QuizStates.ADMIN_SETTING_GENERATE_COOLDOWN)
    await message.answer(Messages.get("ADMIN_SET_GEN_LIMIT", lang), reply_markup=get_cancel_keyboard(lang))

@router.message(QuizStates.ADMIN_AI_SETTINGS, F.text.in_([Messages.get("ADMIN_SET_CONV_LIMIT_BTN", "UZ"), Messages.get("ADMIN_SET_CONV_LIMIT_BTN", "EN")]))
async def admin_prompt_conv_limit(message: types.Message, state: FSMContext, lang: str):
    await state.set_state(QuizStates.ADMIN_SETTING_CONVERT_COOLDOWN)
    await message.answer(Messages.get("ADMIN_SET_CONV_LIMIT", lang), reply_markup=get_cancel_keyboard(lang))

@router.message(QuizStates.ADMIN_AI_SETTINGS, F.text.in_([Messages.get("BACK_BTN", "UZ"), Messages.get("BACK_BTN", "EN")]))
async def admin_ai_settings_back(message: types.Message, state: FSMContext, lang: str):
    await state.clear()
    await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_main_keyboard(lang, settings.ADMIN_ID))

@router.message(QuizStates.ADMIN_SETTING_GENERATE_COOLDOWN)
async def admin_save_gen_limit(message: types.Message, state: FSMContext, redis, lang: str):
    # Check if it's a cancel button
    if message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await admin_ai_settings(message, state, redis, lang)
        return

    if not message.text.isdigit():
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
        return
    
    val = int(message.text)
    if not (0 <= val <= 24):
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
        return

    await redis.set("global_settings:ai_gen_limit", val)
    
    # Clear all existing generation limits for users
    keys = await redis.keys("ai_limit:gen:*")
    if keys:
        await redis.delete(*keys)
        logger.info(f"Cleared {len(keys)} AI generation limits after setting change.")
    
    # Go back to AI settings menu with success message
    await admin_ai_settings(message, state, redis, lang, success_msg=Messages.get("ADMIN_LIMIT_UPDATED", lang))

@router.message(QuizStates.ADMIN_SETTING_CONVERT_COOLDOWN)
async def admin_save_conv_limit(message: types.Message, state: FSMContext, redis, lang: str):
    # Check if it's a cancel button
    if message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await admin_ai_settings(message, state, redis, lang)
        return

    if not message.text.isdigit():
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
        return
    
    val = int(message.text)
    if not (0 <= val <= 24):
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
        return

    await redis.set("global_settings:ai_conv_limit", val)
    
    # Clear all existing conversion limits for users
    keys = await redis.keys("ai_limit:conv:*")
    if keys:
        await redis.delete(*keys)
        logger.info(f"Cleared {len(keys)} AI conversion limits after setting change.")
    
    # Go back to AI settings menu with success message
    await admin_ai_settings(message, state, redis, lang, success_msg=Messages.get("ADMIN_LIMIT_UPDATED", lang))

# ===================== BROADCAST =====================

@router.message(F.text.in_([Messages.get("ADMIN_BROADCAST_BTN", "UZ"), Messages.get("ADMIN_BROADCAST_BTN", "EN")]))
async def admin_broadcast_init(message: types.Message, state: FSMContext, lang: str):
    await state.set_state(QuizStates.ADMIN_BROADCAST_MSG)
    await message.answer(
        Messages.get("ADMIN_BROADCAST_PROMPT", lang),
        reply_markup=get_cancel_keyboard(lang)
    )

@router.message(QuizStates.ADMIN_BROADCAST_MSG)
async def admin_broadcast_execute(message: types.Message, state: FSMContext, bot: Bot, db: AsyncSession, redis, lang: str):
    # Check if it's a cancel button
    if message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await state.clear()
        await message.answer(
            Messages.get("SELECT_BUTTON", lang),
            reply_markup=get_main_keyboard(lang, settings.ADMIN_ID)
        )
        return

    # Get all users and groups (telegram_id only)
    user_result = await db.execute(select(User.telegram_id))
    user_ids = list(user_result.scalars().all())
    
    group_result = await db.execute(select(Group.telegram_id))
    group_ids = list(group_result.scalars().all())
    
    all_targets = user_ids + group_ids
    
    count = 0
    progress_msg = await message.answer(f"🚀 Broadcasting... 0/{len(all_targets)}")
    
    for i, target_id in enumerate(all_targets, 1):
        try:
            # Use copy_message for much better reliability with media
            await bot.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {target_id}: {e}")
        
        # Update progress every 20 targets
        if i % 20 == 0:
            try:
                await progress_msg.edit_text(f"🚀 Broadcasting... {i}/{len(all_targets)}")
            except:
                pass
    
    # Save as last broadcast for new users
    await redis.set("global_settings:last_broadcast", json.dumps({
        "from_chat_id": message.chat.id,
        "message_id": message.message_id
    }))
    
    await state.clear()
    await message.answer(
        Messages.get("ADMIN_BROADCAST_SUCCESS", lang).format(count=count),
        reply_markup=get_main_keyboard(lang, settings.ADMIN_ID)
    )

@router.message(F.text == "/maintenance")
@router.message(F.text.in_([Messages.get("ADMIN_MAINTENANCE_BTN", "UZ"), Messages.get("ADMIN_MAINTENANCE_BTN", "EN")]))
async def admin_maintenance_notify(message: types.Message, bot: Bot, db: AsyncSession, lang: str, redis: Any):
    # 1. Get all active sessions with user telegram_id
    result = await db.execute(
        select(QuizSession.user_id)
        .filter(QuizSession.is_active == True)
        .distinct()
    )
    user_ids = list(result.scalars().all())
    
    # 2. Get all active group quizzes from Redis
    group_keys = await redis.keys("group_quiz:*")
    group_ids = [int(key.split(":")[1]) for key in group_keys]
    
    all_targets = list(set(user_ids + group_ids))
    
    if not all_targets:
        await message.answer(Messages.get("MAINTENANCE_NO_SESSIONS", lang))
        return

    count = 0
    msg_text = Messages.get("MAINTENANCE_WARNING", "UZ") + "\n\n" + Messages.get("MAINTENANCE_WARNING", "EN")
    
    for target_id in all_targets:
        try:
            await bot.send_message(chat_id=target_id, text=msg_text, parse_mode="HTML")
            count += 1
        except Exception as e:
            logger.warning(f"Failed to send maintenance warning to {target_id}: {e}")

    await message.answer(
        Messages.get("MAINTENANCE_SENT", lang).format(count=count)
    )
