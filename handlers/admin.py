from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import json
import time
import asyncio
from typing import List, Any

from core.config import settings
from constants.messages import Messages
from models.user import User
from models.group import Group
from models.quiz import Quiz
from models.session import QuizSession
from services.user_service import UserService
from services.group_service import GroupService
from services.backup_service import send_backup_to_admin
from core.logger import logger
from handlers.common import QuizStates, get_main_keyboard, get_admin_ai_keyboard, get_cancel_keyboard
from aiogram.fsm.context import FSMContext

router = Router()
# Only allow admin to use these handlers
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)

@router.message(F.text.in_([Messages.get("ADMIN_BACKUP_BTN", "UZ"), Messages.get("ADMIN_BACKUP_BTN", "EN")]))
async def admin_manual_backup(message: types.Message, bot: Bot, lang: str):
    await message.answer(Messages.get("BACKUP_STARTED", lang))
    await send_backup_to_admin(bot, lang)

@router.message(F.text.in_([Messages.get("ADMIN_USERS_BTN", "UZ"), Messages.get("ADMIN_USERS_BTN", "EN")]))
async def admin_list_users(message: types.Message, db: AsyncSession, lang: str):
    await show_users_page(message, db, lang, page=0)

async def show_users_page(message_or_query, db: AsyncSession, lang: str, page: int):
    limit = 10
    offset = page * limit
    
    # Get total count (only active users)
    total_result = await db.execute(
        select(func.count(User.id)).filter(User.is_active == True)
    )
    total_users = total_result.scalar() or 0
    
    # Get registered count (active users with phone)
    registered_result = await db.execute(
        select(func.count(User.id)).filter(User.is_active == True, User.phone_number != None)
    )
    registered_users = registered_result.scalar() or 0
    
    # Get users for page (only active users)
    result = await db.execute(
        select(User).filter(User.is_active == True)
        .offset(offset).limit(limit).order_by(User.id.desc())
    )
    users = result.scalars().all()
    
    text = Messages.get("ADMIN_USERS_TITLE", lang).format(
        total=total_users, 
        registered=registered_users
    ) + "\n\n"
    
    builder = InlineKeyboardBuilder()
    for i, user in enumerate(users, 1 + offset):
        # Name display logic: use full name or fallback, truncate if too long
        display_name = user.full_name or f"Foydalanuvchi {user.telegram_id}"
        if len(display_name) > 25:
            display_name = display_name[:22] + "..."
            
        # Phone indicator: ✅ if shared, ⚠️ if not
        indicator = "✅" if user.phone_number else "⚠️"
        # Convert UTC from DB to local Tashkent time (+5)
        uz_time = user.created_at + timedelta(hours=5)
        date_str = uz_time.strftime("%d.%m.%y %H:%M")
        phone = f" — <code>{user.phone_number}</code>" if user.phone_number else " — [Raqamsiz]"
        id_info = f" (<code>{user.telegram_id}</code>)"
        
        link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
        text += f"{i}. {indicator} <a href='{link}'>{display_name}</a>{id_info}{phone} — [{date_str}]\n"
        
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
    
    # Get total count (only active groups)
    total_result = await db.execute(select(func.count(Group.id)).filter(Group.is_active == True))
    total_groups = total_result.scalar()
    
    # Get groups for page
    result = await db.execute(
        select(Group).filter(Group.is_active == True)
        .offset(offset).limit(limit).order_by(Group.id.desc())
    )
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
    from datetime import datetime, timedelta
    
    # Today's date range
    # Today's date range (Aligned with Tashkent 00:00)
    # Since DB is UTC, Today 00:00 Tashkent = Yesterday 19:00 UTC
    today_start_local = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local - timedelta(hours=5)
    
    # Users count (total and active)
    res_users = await db.execute(select(func.count(User.id)))
    total_users_count = res_users.scalar() or 0
    
    res_active_users = await db.execute(select(func.count(User.id)).filter(User.is_active == True))
    active_users_count = res_active_users.scalar() or 0

    # Registered vs Unregistered counts
    res_reg = await db.execute(select(func.count(User.id)).filter(User.is_active == True, User.phone_number != None))
    registered_count = res_reg.scalar() or 0
    
    res_unreg = await db.execute(select(func.count(User.id)).filter(User.is_active == True, User.phone_number == None))
    unregistered_count = res_unreg.scalar() or 0

    res_today_users = await db.execute(
        select(func.count(User.id)).filter(User.created_at >= today_start_utc)
    )
    today_users_count = res_today_users.scalar() or 0
    
    res_today_reg = await db.execute(
        select(func.count(User.id)).filter(User.created_at >= today_start_utc, User.phone_number != None)
    )
    today_registered = res_today_reg.scalar() or 0
    
    res_today_unreg = await db.execute(
        select(func.count(User.id)).filter(User.created_at >= today_start_utc, User.phone_number == None)
    )
    today_unregistered = res_today_unreg.scalar() or 0
    
    # Groups count
    res_groups = await db.execute(select(func.count(Group.id)))
    total_groups = res_groups.scalar()
    
    res_active_groups = await db.execute(select(func.count(Group.id)).filter(Group.is_active == True))
    active_groups_count = res_active_groups.scalar() or 0
    
    # Quizzes count (total and today)
    res_quizzes = await db.execute(select(func.count(Quiz.id)))
    total_quizzes = res_quizzes.scalar()
    
    res_today_quizzes = await db.execute(
        select(func.count(Quiz.id)).filter(Quiz.created_at >= today_start_utc)
    )
    today_quizzes = res_today_quizzes.scalar() or 0
    
    # Total quiz sessions (completed)
    res_total_sessions = await db.execute(
        select(func.count(QuizSession.id)).filter(QuizSession.is_active == False)
    )
    total_sessions = res_total_sessions.scalar() or 0
    
    # Active quizzes (Group) - Redis keys for in-progress quizzes
    group_keys = await redis.keys("group_quiz:*")
    active_group_quizzes = len(group_keys)
    
    # Active lobbies (Group)
    lobby_keys = await redis.keys("quiz_lobby:*")
    active_lobbies = len(lobby_keys)
    
    # Active sessions (Private) - Filter by updated_at within last 2 minutes 
    # Alignment: Using utcnow() to match DB storage, threshold reduced to 2m for stability
    activity_threshold = datetime.utcnow() - timedelta(minutes=2)
    res_active_sessions = await db.execute(
        select(func.count(QuizSession.id))
        .filter(QuizSession.is_active == True, QuizSession.updated_at > activity_threshold)
    )
    active_private_quizzes = res_active_sessions.scalar() or 0
    
    total_active = active_group_quizzes + active_private_quizzes + active_lobbies

    # AI Stats
    ai_gen_total = await redis.get("stats:ai_gen_total") or 0
    ai_conv_total = await redis.get("stats:ai_conv_total") or 0
    
    # Bot uptime (from process start)
    import os
    import psutil
    try:
        process = psutil.Process(os.getpid())
        uptime_seconds = time.time() - process.create_time()
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        mins = int((uptime_seconds % 3600) // 60)
        if days > 0:
            uptime_str = f"{days}d {hours}h {mins}m"
        elif hours > 0:
            uptime_str = f"{hours}h {mins}m"
        else:
            uptime_str = f"{mins}m"
    except:
        uptime_str = "N/A"
    
    stats_msg = Messages.get("ADMIN_STATS_MSG", lang).format(
        total_users=f"{total_users_count} (Active: {active_users_count})",
        registered_users=registered_count,
        unregistered_users=unregistered_count,
        today_users=today_users_count,
        today_reg=today_registered,
        today_unreg=today_unregistered,
        total_groups=f"{total_groups} (Active: {active_groups_count})",
        total_quizzes=total_quizzes,
        today_quizzes=today_quizzes,
        total_sessions=total_sessions,
        active_quizzes=total_active,
        active_groups=active_group_quizzes,
        active_lobbies=active_lobbies,
        active_private=active_private_quizzes,
        ai_gen_total=ai_gen_total,
        ai_conv_total=ai_conv_total,
        uptime=uptime_str
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

    # Get all active users and groups (telegram_id only)
    user_result = await db.execute(select(User.telegram_id).filter(User.is_active == True))
    user_ids = list(user_result.scalars().all())
    
    group_result = await db.execute(select(Group.telegram_id).filter(Group.is_active == True))
    group_ids = list(group_result.scalars().all())
    
    all_targets = user_ids + group_ids
    user_ids_set = set(user_ids)
    
    # Track dead IDs to update DB later
    dead_user_ids = []
    dead_group_ids = []
    
    count = 0
    user_success = 0
    group_success = 0
    
    progress_msg = await message.answer(f"🚀 Broadcasting... 0/{len(all_targets)}")
    
    for i, target_id in enumerate(all_targets, 1):
        try:
            await asyncio.sleep(0.05)  # Rate limit: ~20 messages/second
            # Use copy_message for much better reliability with media
            await bot.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            count += 1
            if target_id in user_ids_set:
                user_success += 1
            else:
                group_success += 1
        except Exception as e:
            from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
            
            if isinstance(e, TelegramRetryAfter):
                logger.warning(f"Rate limit hit during broadcast. Waiting {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                # Retry this specific target once
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.message_id)
                    count += 1
                    if target_id in user_ids_set: user_success += 1
                    else: group_success += 1
                except:
                    pass
                continue

            err_msg = str(e).lower()
            logger.warning(f"Failed to send broadcast to {target_id}: {err_msg}")
            
            # If forbidden or chat not found, mark as inactive
            if "forbidden" in err_msg or "chat not found" in err_msg:
                if target_id in user_ids_set:
                    dead_user_ids.append(target_id)
                    # Also deactivate active sessions for this user
                    await db.execute(
                        update(QuizSession).where(QuizSession.user_id == target_id, QuizSession.is_active == True).values(is_active=False)
                    )
                else:
                    dead_group_ids.append(target_id)
        
        # Update progress every 20 targets
        if i % 20 == 0:
            try:
                await progress_msg.edit_text(f"🚀 Broadcasting... {i}/{len(all_targets)}")
            except:
                pass

    # Batch update inactive targets
    if dead_user_ids:
        from sqlalchemy import update
        await db.execute(
            update(User).where(User.telegram_id.in_(dead_user_ids)).values(is_active=False)
        )
        logger.info(f"Marked {len(dead_user_ids)} users as inactive after broadcast failure.")
        
    if dead_group_ids:
        from sqlalchemy import update
        await db.execute(
            update(Group).where(Group.telegram_id.in_(dead_group_ids)).values(is_active=False)
        )
        logger.info(f"Marked {len(dead_group_ids)} groups as inactive after broadcast failure.")
    
    if dead_user_ids or dead_group_ids:
        await db.commit()
    
    # Save as last broadcast for new users
    await redis.set("global_settings:last_broadcast", json.dumps({
        "from_chat_id": message.chat.id,
        "message_id": message.message_id
    }))
    
    await state.clear()
    await message.answer(
        Messages.get("ADMIN_BROADCAST_SUCCESS", lang).format(
            users=user_success,
            groups=group_success,
            total=count
        ),
        reply_markup=get_main_keyboard(lang, settings.ADMIN_ID)
    )

@router.message(F.text == "/maintenance")
@router.message(F.text.in_([Messages.get("ADMIN_MAINTENANCE_BTN", "UZ"), Messages.get("ADMIN_MAINTENANCE_BTN", "EN")]))
async def admin_maintenance_notify(message: types.Message, bot: Bot, db: AsyncSession, lang: str, redis: Any):
    # 1. Get genuinely active sessions (updated within last 30 minutes)
    activity_threshold = datetime.now() - timedelta(minutes=30)
    result = await db.execute(
        select(QuizSession.user_id)
        .filter(QuizSession.is_active == True, QuizSession.updated_at > activity_threshold)
        .distinct()
    )
    user_ids = list(result.scalars().all())
    
    # 2. Get all active group quizzes from Redis
    group_keys = await redis.keys("group_quiz:*")
    group_ids_from_redis = [int(key.split(":")[1]) for key in group_keys]
    
    # 3. Verify only active groups from DB
    if group_ids_from_redis:
        active_group_res = await db.execute(
            select(Group.telegram_id).filter(Group.telegram_id.in_(group_ids_from_redis), Group.is_active == True)
        )
        group_ids = list(active_group_res.scalars().all())
    else:
        group_ids = []
    
    all_targets = list(set(user_ids + group_ids))
    
    if not all_targets:
        await message.answer(Messages.get("MAINTENANCE_NO_SESSIONS", lang))
        return

    msg_text = Messages.get("MAINTENANCE_WARNING", "UZ") + "\n\n" + Messages.get("MAINTENANCE_WARNING", "EN")
    
    user_count = 0
    group_count = 0

    # Notify users
    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
    from sqlalchemy import update
    
    for user_id in user_ids:
        try:
            await bot.send_message(chat_id=user_id, text=msg_text, parse_mode="HTML")
            user_count += 1
            await asyncio.sleep(0.05)  # 20 messages per second limit
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            err_msg = str(e).lower()
            logger.warning(f"Failed to send maintenance warning to user {user_id}: {e}")
            
            # If forbidden (blocked) or chat not found, deactivate their sessions
            if "forbidden" in err_msg or "chat not found" in err_msg:
                await db.execute(
                    update(QuizSession).where(QuizSession.user_id == user_id, QuizSession.is_active == True).values(is_active=False)
                )
                await db.execute(
                    update(User).where(User.telegram_id == user_id).values(is_active=False)
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to send maintenance warning to user {user_id}: {e}")

    # Notify groups
    for group_id in group_ids:
        try:
            await bot.send_message(chat_id=group_id, text=msg_text, parse_mode="HTML")
            group_count += 1
            await asyncio.sleep(0.05)  # 20 messages per second limit
        except Exception as e:
            logger.warning(f"Failed to send maintenance warning to group {group_id}: {e}")

    total_count = user_count + group_count
    await message.answer(
        Messages.get("MAINTENANCE_SENT_DETAILS", lang).format(
            user_count=user_count, 
            group_count=group_count, 
            total=total_count
        )
    )

@router.message(F.text == "/cleanup_db")
async def admin_silent_cleanup(message: types.Message, bot: Bot, db: AsyncSession, lang: str):
    """
    Check all active users and groups via get_chat (silent) 
    and mark as inactive if inaccessible.
    """
    await message.answer(Messages.get("CLEANUP_STARTED", lang))
    
    # Run in background to not block the bot
    asyncio.create_task(run_silent_cleanup_task(message.chat.id, bot, lang))

async def run_silent_cleanup_task(admin_chat_id: int, bot: Bot, lang: str):
    from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
    from sqlalchemy import select, update, delete
    from models.quiz import Quiz
    from models.session import QuizSession
    
    # We need a new session for the background task
    from db.session import AsyncSessionLocal as async_session_factory
    async with async_session_factory() as session:
        # First: Mass-delete all users already marked as inactive
        # Order matters! Sessions -> Quizzes -> Users
        # Fetch IDs into memory first to avoid subquery issues with concurrent deletions
        res_u_ids = await session.execute(select(User.telegram_id).where(User.is_active == False))
        inactive_user_ids = [r[0] for r in res_u_ids.fetchall()]
        
        if inactive_user_ids:
            # 1. Sessions for inactive users
            await session.execute(delete(QuizSession).where(QuizSession.user_id.in_(inactive_user_ids)))
            
            # 2. Quizzes created by inactive users
            res_q_ids = await session.execute(select(Quiz.id).where(Quiz.user_id.in_(inactive_user_ids)))
            inactive_quiz_ids = [r[0] for r in res_q_ids.fetchall()]
            
            if inactive_quiz_ids:
                # Delete sessions associated with these quizzes
                await session.execute(delete(QuizSession).where(QuizSession.quiz_id.in_(inactive_quiz_ids)))
                # Delete the quizzes
                await session.execute(delete(Quiz).where(Quiz.id.in_(inactive_quiz_ids)))
            
            # 3. Finally delete the User records
            res_u = await session.execute(delete(User).where(User.telegram_id.in_(inactive_user_ids)))
            u_count = res_u.rowcount or 0
        else:
            u_count = 0
        
        res_g = await session.execute(delete(Group).where(Group.is_active == False))
        g_count = res_g.rowcount or 0
        
        initial_dead_count = u_count + g_count
        await session.commit()

        # Get all IDs to check
        res_users = await session.execute(select(User.telegram_id))
        all_user_ids = [r[0] for r in res_users.fetchall()]
        
        res_groups = await session.execute(select(Group.telegram_id))
        all_group_ids = [r[0] for r in res_groups.fetchall()]
        
        all_targets = all_user_ids + all_group_ids
        user_ids_set = set(all_user_ids)
        
        # Improved reporting: Total = Initial dead + items to check
        check_count = len(all_targets)
        report_total = initial_dead_count + check_count
        
        if report_total == 0:
            await bot.send_message(admin_chat_id, "ℹ️ Bazada tekshirish uchun foydalanuvchilar yo'q.")
            return

        # Initial status message including already deleted ones
        status_msg = await bot.send_message(
            admin_chat_id, 
            Messages.get("CLEANUP_PROGRESS", lang).format(
                current=initial_dead_count, 
                total=report_total, 
                percent=int((initial_dead_count/report_total)*100) if report_total > 0 else 100,
                alive=0, 
                dead=initial_dead_count
            ),
            parse_mode="HTML"
        )

        dead_user_ids = []
        dead_group_ids = []
        alive_count = 0
        dead_count = initial_dead_count
        
        for i, target_id in enumerate(all_targets, 1):
            try:
                chat = await bot.get_chat(target_id)
                alive_count += 1
                
                # Refresh user info if it's a user
                if target_id in user_ids_set:
                    full_name = f"{chat.first_name} {chat.last_name}".strip() if chat.last_name else chat.first_name
                    await session.execute(
                        update(User)
                        .where(User.telegram_id == target_id)
                        .values(full_name=full_name, username=chat.username)
                    )
                
                await asyncio.sleep(settings.CLEANUP_SLEEP_SECONDS)
            except TelegramForbiddenError:
                dead_count += 1
                if target_id in user_ids_set: dead_user_ids.append(target_id)
                else: dead_group_ids.append(target_id)
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    dead_count += 1
                    if target_id in user_ids_set: dead_user_ids.append(target_id)
                    else: dead_group_ids.append(target_id)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                pass
            
            # Periodic deletion and progress update
            if i % settings.CLEANUP_BATCH_SIZE == 0 or i == check_count:
                if dead_user_ids:
                    # Satisfy FK constraints for batch deletion
                    # 1. Sessions for dead users
                    await session.execute(delete(QuizSession).where(QuizSession.user_id.in_(dead_user_ids)))
                    
                    # 2. Sessions for quizzes created by dead users
                    dead_quiz_ids_query = select(Quiz.id).where(Quiz.user_id.in_(dead_user_ids))
                    await session.execute(delete(QuizSession).where(QuizSession.quiz_id.in_(dead_quiz_ids_query)))
                    
                    # 3. Quizzes for dead users
                    await session.execute(delete(Quiz).where(Quiz.user_id.in_(dead_user_ids)))
                    
                    # 4. User record
                    await session.execute(delete(User).where(User.telegram_id.in_(dead_user_ids)))
                    dead_user_ids = []
                    
                if dead_group_ids:
                    await session.execute(delete(Group).where(Group.telegram_id.in_(dead_group_ids)))
                    dead_group_ids = []
                
                await session.commit()
                
                # Update progress message
                try:
                    current_processed = initial_dead_count + i
                    await bot.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=status_msg.message_id,
                        text=Messages.get("CLEANUP_PROGRESS", lang).format(
                            current=current_processed,
                            total=report_total,
                            percent=int((current_processed/report_total)*100),
                            alive=alive_count,
                            dead=dead_count
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass # Message might not have changed or was deleted

        await bot.send_message(
            admin_chat_id, 
            Messages.get("CLEANUP_FINISHED_MSG", lang).format(
                total=report_total,
                dead=dead_count
            )
        )
