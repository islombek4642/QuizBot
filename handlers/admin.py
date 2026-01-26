from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from db.session import get_db
from models.user import User
from models.group import Group
from models.quiz import Quiz
from models.session import QuizSession
from constants.messages import Messages
from handlers.common import QuizStates, get_main_keyboard, get_admin_ai_keyboard, get_admin_backup_keyboard, get_cancel_keyboard
from core.config import settings
from core.logger import logger
import json
import asyncio
from datetime import datetime, timedelta
from typing import Any
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

router = Router()

# Only allow admin commands
router.message.filter(F.from_user.id == settings.ADMIN_ID)

@router.message(F.text.in_([Messages.get("ADMIN_USERS_BTN", "UZ"), Messages.get("ADMIN_USERS_BTN", "EN")]))
async def admin_users_list(message: types.Message, db: AsyncSession, lang: str):
    await show_users_page(message, db, lang, 1)

async def show_users_page(message: types.Message, db: AsyncSession, lang: str, page: int):
    limit = 20
    offset = (page - 1) * limit
    
    total_q = select(func.count(User.id))
    total = (await db.execute(total_q)).scalar()
    
    reg_q = select(func.count(User.id)).filter(User.phone_number.is_not(None))
    registered = (await db.execute(reg_q)).scalar()
    
    users_q = select(User).order_by(desc(User.created_at)).limit(limit).offset(offset)
    result = await db.execute(users_q)
    users = result.scalars().all()
    
    text = Messages.get("ADMIN_USERS_TITLE", lang).format(total=total, registered=registered) + "\n\n"
    
    for user in users:
        status = "🟢" if user.is_active else "🔴"
        reg = "📱" if user.phone_number else "👤"
        name = user.full_name or "No Name"
        text += f"{status} {reg} <b>{name}</b> <code>{user.telegram_id}</code>\n"
        
    # Pagination
    keyboard_builder = get_pagination_keyboard(page, total, limit, "users", lang)
    
    await message.answer(text, reply_markup=keyboard_builder.as_markup())

def get_pagination_keyboard(page, total, limit, type_str, lang):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    
    total_pages = (total + limit - 1) // limit
    
    if page > 1:
        builder.button(text="⬅️", callback_data=f"adm_{type_str}:{page-1}")
    
    builder.button(text=f"{page}/{total_pages}", callback_data="noop")
    
    if page < total_pages:
        builder.button(text="➡️", callback_data=f"adm_{type_str}:{page+1}")
        
    return builder

@router.callback_query(F.data.startswith("adm_users:"))
async def admin_users_pagination(callback: types.CallbackQuery, db: AsyncSession, lang: str):
    page = int(callback.data.split(":")[1])
    await show_users_page(callback.message, db, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_GROUPS_BTN", "UZ"), Messages.get("ADMIN_GROUPS_BTN", "EN")]))
async def admin_groups_list(message: types.Message, db: AsyncSession, lang: str):
    await show_groups_page(message, db, lang, 1)

async def show_groups_page(message: types.Message, db: AsyncSession, lang: str, page: int):
    limit = 20
    offset = (page - 1) * limit
    
    total_q = select(func.count(Group.id))
    total = (await db.execute(total_q)).scalar()
    
    groups_q = select(Group).order_by(desc(Group.created_at)).limit(limit).offset(offset)
    result = await db.execute(groups_q)
    groups = result.scalars().all()
    
    text = Messages.get("ADMIN_GROUPS_TITLE", lang).format(total=total) + "\n\n"
    
    for group in groups:
        status = "🟢" if group.is_active else "🔴"
        title = group.title or "No Title"
        text += f"{status} <b>{title}</b> <code>{group.telegram_id}</code>\n"
        
    keyboard_builder = get_pagination_keyboard(page, total, limit, "groups", lang)
    await message.answer(text, reply_markup=keyboard_builder.as_markup())

@router.callback_query(F.data.startswith("adm_groups:"))
async def admin_groups_pagination(callback: types.CallbackQuery, db: AsyncSession, lang: str):
    page = int(callback.data.split(":")[1])
    await show_groups_page(callback.message, db, lang, page)
    await callback.answer()

@router.message(F.text.in_([Messages.get("ADMIN_STATS_BTN", "UZ"), Messages.get("ADMIN_STATS_BTN", "EN")]))
async def admin_stats(message: types.Message, db: AsyncSession, lang: str, redis: Any):
    # Basic Counters
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    reg_users = (await db.execute(select(func.count(User.id)).filter(User.phone_number.is_not(None)))).scalar()
    total_groups = (await db.execute(select(func.count(Group.id)))).scalar()
    total_quizzes = (await db.execute(select(func.count(Quiz.id)))).scalar()
    
    # Today's stats
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_users = (await db.execute(select(func.count(User.id)).filter(User.created_at >= today_start))).scalar()
    today_reg = (await db.execute(select(func.count(User.id)).filter(User.created_at >= today_start, User.phone_number.is_not(None)))).scalar()
    today_quizzes = (await db.execute(select(func.count(Quiz.id)).filter(Quiz.created_at >= today_start))).scalar()
    
    # Session stats
    total_sessions = (await db.execute(select(func.count(QuizSession.id)))).scalar()
    active_sessions = (await db.execute(select(func.count(QuizSession.id)).filter(QuizSession.is_active == True))).scalar()
    
    # Active Groups finding (Redis keys scan)
    active_group_sessions = 0
    active_lobbies = 0
    try:
        keys = await redis.keys("group_quiz:*")
        active_group_sessions = len(keys)
        lobby_keys = await redis.keys("quiz_lobby:*")
        active_lobbies = len(lobby_keys)
    except:
        pass
    
    # AI Stats from Redis
    ai_gen_total = await redis.get("stats:ai_generated") or 0
    ai_conv_total = await redis.get("stats:ai_converted") or 0
    word_upload_total = await redis.get("stats:word_uploaded") or 0
    
    uptime = "N/A" # TODO: Implement uptime tracking
        
    msg = Messages.get("ADMIN_STATS_MSG", lang).format(
        total_users=total_users,
        registered_users=reg_users,
        unregistered_users=total_users - reg_users,
        today_users=today_users,
        today_reg=today_reg,
        today_unreg=today_users - today_reg,
        total_groups=total_groups,
        total_quizzes=total_quizzes,
        today_quizzes=today_quizzes,
        total_sessions=total_sessions,
        active_quizzes=active_sessions + active_group_sessions,
        active_groups=active_group_sessions,
        active_lobbies=active_lobbies,
        active_private=active_sessions,
        ai_gen_total=int(ai_gen_total),
        ai_conv_total=int(ai_conv_total),
        word_upload_total=int(word_upload_total),
        uptime=uptime
    )
    
    await message.answer(msg, parse_mode="HTML")

# AI Settings
@router.message(F.text.in_([Messages.get("ADMIN_AI_SETTINGS_BTN", "UZ"), Messages.get("ADMIN_AI_SETTINGS_BTN", "EN")]))
async def admin_ai_settings(message: types.Message, state: FSMContext, lang: str):
    await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
    
    gen_limit = settings.AI_GENERATE_LIMIT_HOURS
    conv_limit = settings.AI_CONVERT_LIMIT_HOURS
    
    msg = Messages.get("ADMIN_AI_SETTINGS_TITLE", lang).format(
        gen_limit=gen_limit,
        conv_limit=conv_limit
    )
    
    await message.answer(msg, reply_markup=get_admin_ai_keyboard(lang))

@router.message(QuizStates.ADMIN_AI_SETTINGS)
async def admin_ai_settings_handle(message: types.Message, state: FSMContext, lang: str):
    if message.text in [Messages.get("BACK_BTN", "UZ"), Messages.get("BACK_BTN", "EN")]:
        await state.clear()
        await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_main_keyboard(lang, settings.ADMIN_ID))
        return
        
    if message.text in [Messages.get("ADMIN_SET_GEN_LIMIT_BTN", "UZ"), Messages.get("ADMIN_SET_GEN_LIMIT_BTN", "EN")]:
        await state.set_state(QuizStates.ADMIN_SETTING_GENERATE_COOLDOWN)
        await message.answer(Messages.get("ADMIN_SET_GEN_LIMIT", lang), reply_markup=get_cancel_keyboard(lang))
        
    elif message.text in [Messages.get("ADMIN_SET_CONV_LIMIT_BTN", "UZ"), Messages.get("ADMIN_SET_CONV_LIMIT_BTN", "EN")]:
        await state.set_state(QuizStates.ADMIN_SETTING_CONVERT_COOLDOWN)
        await message.answer(Messages.get("ADMIN_SET_CONV_LIMIT", lang), reply_markup=get_cancel_keyboard(lang))

@router.message(QuizStates.ADMIN_SETTING_GENERATE_COOLDOWN)
async def set_gen_cooldown(message: types.Message, state: FSMContext, lang: str):
    if message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
        await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_admin_ai_keyboard(lang))
        return
        
    try:
        val = int(message.text)
        if 0 <= val <= 24:
            # Update settings (In-memory for now, ideally DB or .env re-write)
            settings.AI_GENERATE_LIMIT_HOURS = val
            await message.answer(Messages.get("ADMIN_LIMIT_UPDATED", lang))
            await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
            await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_admin_ai_keyboard(lang))
        else:
            await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
    except ValueError:
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))

@router.message(QuizStates.ADMIN_SETTING_CONVERT_COOLDOWN)
async def set_conv_cooldown(message: types.Message, state: FSMContext, lang: str):
    if message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
        await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_admin_ai_keyboard(lang))
        return
        
    try:
        val = int(message.text)
        if 0 <= val <= 24:
            settings.AI_CONVERT_LIMIT_HOURS = val
            await message.answer(Messages.get("ADMIN_LIMIT_UPDATED", lang))
            await state.set_state(QuizStates.ADMIN_AI_SETTINGS)
            await message.answer(Messages.get("SELECT_BUTTON", lang), reply_markup=get_admin_ai_keyboard(lang))
        else:
            await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))
    except ValueError:
        await message.answer(Messages.get("ADMIN_INVALID_LIMIT", lang))

# Broadcast Section
@router.message(F.text.in_([Messages.get("ADMIN_BROADCAST_BTN", "UZ"), Messages.get("ADMIN_BROADCAST_BTN", "EN")]))
async def admin_broadcast_init(message: types.Message, state: FSMContext, lang: str):
    await state.set_state(QuizStates.ADMIN_BROADCAST_MSG)
    await message.answer(
        Messages.get("ADMIN_BROADCAST_PROMPT", lang),
        reply_markup=get_cancel_keyboard(lang)
    )

@router.message(QuizStates.ADMIN_BROADCAST_MSG)
async def admin_broadcast_capture(message: types.Message, state: FSMContext, lang: str):
    # Check if it's a cancel button (Ultra-Enhanced check)
    text_lower = message.text.lower() if message.text else ""
    is_cancel = message.text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]
    
    if not is_cancel and message.text:
        if message.text.startswith("🚫") or "bekor" in text_lower or "cancel" in text_lower or "otmen" in text_lower:
            is_cancel = True

    if is_cancel:
        await state.clear()
        await message.answer(
            Messages.get("SELECT_BUTTON", lang),
            reply_markup=get_main_keyboard(lang, settings.ADMIN_ID)
        )
        return

    # Prevent accidental broadcasting of commands
    if message.text and message.text.startswith("/") and len(message.text) < 20: 
        await message.answer(Messages.get("BROADCAST_COMMAND_ERROR", lang))
        return

    # Capture content
    content = {
        "text": message.text or message.caption,
        "caption": message.caption,
        "entities": [e.model_dump() for e in (message.entities or message.caption_entities or [])],
        "type": "text"
    }
    
    if message.photo:
        content["type"] = "photo"
        content["file_id"] = message.photo[-1].file_id
    elif message.video:
        content["type"] = "video"
        content["file_id"] = message.video.file_id
    elif message.document:
        content["type"] = "document"
        content["file_id"] = message.document.file_id
    elif message.animation:
        content["type"] = "animation"
        content["file_id"] = message.animation.file_id
    elif message.audio:
        content["type"] = "audio"
        content["file_id"] = message.audio.file_id
    elif message.voice:
        content["type"] = "voice"
        content["file_id"] = message.voice.file_id

    # Save to state
    await state.update_data(broadcast_content=content, preview_message_id=message.message_id)
    
    # Send confirmation
    confirm_kb = ReplyKeyboardBuilder()
    confirm_kb.button(text=Messages.get("BROADCAST_CONFIRM_YES", lang))
    confirm_kb.button(text=Messages.get("BROADCAST_CONFIRM_NO", lang))
    confirm_kb.adjust(2)
    
    preview_text = content.get("text", "") or "[Media]"
    if len(preview_text) > 100: preview_text = preview_text[:100] + "..."
    
    prompt = Messages.get("ADMIN_BROADCAST_CONFIRM_MSG", lang).format(text=preview_text)
    
    await message.answer(prompt, reply_markup=confirm_kb.as_markup(resize_keyboard=True))
    await state.set_state(QuizStates.ADMIN_BROADCAST_CONFIRM)

@router.message(QuizStates.ADMIN_BROADCAST_CONFIRM)
async def admin_broadcast_confirm(message: types.Message, state: FSMContext, bot: Bot, db: AsyncSession, redis, lang: str):
    if message.text in [Messages.get("BROADCAST_CONFIRM_NO", "UZ"), Messages.get("BROADCAST_CONFIRM_NO", "EN")]:
        await state.clear()
        await message.answer(
            Messages.get("BROADCAST_CANCELLED", lang),
            reply_markup=get_main_keyboard(lang, settings.ADMIN_ID)
        )
        return

    if message.text not in [Messages.get("BROADCAST_CONFIRM_YES", "UZ"), Messages.get("BROADCAST_CONFIRM_YES", "EN")]:
        await message.answer("Please choose Yes or No.")
        return

    # User confirmed YES - Execute Broadcast
    data = await state.get_data()
    content = data.get("broadcast_content")
    original_msg_id = data.get("preview_message_id")
    
    # FINAL SAFETY CHECK: Ensure we are not broadcasting "Cancel" text
    text_content = content.get("text", "").lower()
    if len(text_content) < 30 and ("bekor" in text_content or "cancel" in text_content or "🚫" in text_content):
        await state.clear()
        await message.answer("⚠️ <b>Safety Stop:</b> It looks like you are trying to broadcast the 'Cancel' button text.\n\nBroadcast aborted.", reply_markup=get_main_keyboard(lang, settings.ADMIN_ID))
        return
    
    # Save broadcast CONTENT for new users (Persistent independent of admin chat history)
    await redis.set("global_settings:last_broadcast_content", json.dumps(content))

    # Get targets
    user_result = await db.execute(select(User.telegram_id).filter(User.is_active == True))
    user_ids = list(user_result.scalars().all())
    
    group_result = await db.execute(select(Group.telegram_id).filter(Group.is_active == True))
    group_ids = list(group_result.scalars().all())
    
    all_targets = user_ids + group_ids
    user_ids_set = set(user_ids)
    
    dead_user_ids = []
    dead_group_ids = []
    
    count = 0
    user_success = 0
    group_success = 0
    
    # Remove Confirm keyboard immediately
    progress_msg = await message.answer(f"🚀 Broadcasting... 0/{len(all_targets)}", reply_markup=types.ReplyKeyboardRemove())
    
    for i, target_id in enumerate(all_targets, 1):
        try:
            await asyncio.sleep(0.05)
            # Use copy_message with the Original Message ID
            await bot.copy_message(
                chat_id=target_id,
                from_chat_id=message.chat.id,
                message_id=original_msg_id
            )
            count += 1
            if target_id in user_ids_set:
                user_success += 1
            else:
                group_success += 1
        except Exception as e:
            from aiogram.exceptions import TelegramRetryAfter
            
            if isinstance(e, TelegramRetryAfter):
                logger.warning(f"Rate limit hit. Waiting {e.retry_after}s.")
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=original_msg_id)
                    count += 1
                    if target_id in user_ids_set: user_success += 1
                    else: group_success += 1
                except:
                    pass
                continue

            err_msg = str(e).lower()
            
            if "forbidden" in err_msg or "chat not found" in err_msg:
                from sqlalchemy import update
                if target_id in user_ids_set:
                    dead_user_ids.append(target_id)
                    await db.execute(
                        update(QuizSession).where(QuizSession.user_id == target_id, QuizSession.is_active == True).values(is_active=False)
                    )
                else:
                    dead_group_ids.append(target_id)
        
        if i % 20 == 0:
            try:
                await progress_msg.edit_text(f"🚀 Broadcasting... {i}/{len(all_targets)}")
            except:
                pass

    if dead_user_ids:
        from sqlalchemy import update
        await db.execute(update(User).where(User.telegram_id.in_(dead_user_ids)).values(is_active=False))
        
    if dead_group_ids:
        from sqlalchemy import update
        await db.execute(update(Group).where(Group.telegram_id.in_(dead_group_ids)).values(is_active=False))
    
    if dead_user_ids or dead_group_ids:
        await db.commit()
    
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
    # 1. Get genuinely active sessions (updated within last 30 seconds)
    activity_threshold = datetime.utcnow() - timedelta(seconds=30)
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
    
    all_targets = user_ids + group_ids
    count = 0
    
    if not all_targets:
        await message.answer("⚠️ No active users found right now.")
        return

    progress = await message.answer(f"📢 Verifying active sessions... Found {len(all_targets)} targets.")
    
    for target in all_targets:
        try:
            await bot.send_message(target, "🛠 <b>Tech Maintenance</b>\n\nBot will restart in 1 minute. Please finish your quiz.")
            count += 1
        except:
            pass
            
    await message.answer(f"✅ Maintenance alert sent to {count} active users/groups.")

# Backup Section
@router.message(F.text.in_([Messages.get("ADMIN_BACKUP_BTN", "UZ"), Messages.get("ADMIN_BACKUP_BTN", "EN")]))
async def admin_backup_menu(message: types.Message, lang: str):
    await message.answer("📦 Backup System", reply_markup=get_admin_backup_keyboard(lang))

@router.message(F.text.in_([Messages.get("ADMIN_TAKE_BACKUP_BTN", "UZ"), Messages.get("ADMIN_TAKE_BACKUP_BTN", "EN")]))
async def admin_take_backup(message: types.Message, lang: str):
    from services.backup_service import BackupService
    
    status_msg = await message.answer("⏳ Creating backup...")
    try:
        file_path = await BackupService.create_backup()
        if file_path:
            await message.reply_document(
                types.FSInputFile(file_path),
                caption=f"✅ Backup created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            # Cleanup
            try:
                os.remove(file_path)
            except:
                pass
        else:
            await message.answer("❌ Failed to create backup file.")
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await message.answer(f"❌ Error: {e}")
    finally:
        await status_msg.delete()

@router.message(F.document)
async def admin_restore_init(message: types.Message, state: FSMContext, lang: str):
    # Check if user sent a .sql or .sql.gz file
    doc = message.document
    if not (doc.file_name.endswith('.sql') or doc.file_name.endswith('.sql.gz')):
        return # Ignore non-sql files
        
    await state.set_state(QuizStates.WAITING_FOR_RESTORE_CONFIRM)
    await state.update_data(file_id=doc.file_id, file_name=doc.file_name)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("RESTORE_SMART_MERGE_BTN", lang))
    builder.button(text=Messages.get("RESTORE_FULL_BTN", lang))
    builder.button(text=Messages.get("CANCEL_BTN", lang))
    builder.adjust(1)
    
    await message.reply(
        Messages.get("ADMIN_RESTORE_INFO", lang),
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@router.message(QuizStates.WAITING_FOR_RESTORE_CONFIRM)
async def admin_restore_handle(message: types.Message, state: FSMContext, bot: Bot, lang: str, db: AsyncSession):
    text = message.text
    data = await state.get_data()
    file_id = data.get('file_id')
    file_name = data.get('file_name')
    
    if text in [Messages.get("CANCEL_BTN", "UZ"), Messages.get("CANCEL_BTN", "EN")]:
        await state.clear()
        await message.answer(Messages.get("CANCELLED", lang), reply_markup=get_main_keyboard(lang, settings.ADMIN_ID))
        return

    from services.backup_service import BackupService
    
    # Download file
    file = await bot.get_file(file_id)
    file_path = f"temp_{file_name}"
    await bot.download_file(file.file_path, file_path)
    
    status_msg = await message.answer(Messages.get("RESTORE_PROCESSING", lang))
    
    try:
        if text in [Messages.get("RESTORE_SMART_MERGE_BTN", "UZ"), Messages.get("RESTORE_SMART_MERGE_BTN", "EN")]:
            # Smart Merge
            stats = await BackupService.smart_merge_users(db, file_path)
            if stats['users_new'] == 0 and stats['groups_new'] == 0:
                await message.answer(Messages.get("MERGE_NO_NEW_DATA", lang))
            else:
                await message.answer(
                    Messages.get("MERGE_SUCCESS_MSG", lang).format(
                        users=stats['users_total'], u_new=stats['users_new'], u_old=stats['users_existing'],
                        groups=stats['groups_total'], g_new=stats['groups_new'], g_old=stats['groups_existing'],
                        quizzes=0, q_new=0, q_old=0 
                    )
                )
                
        elif text in [Messages.get("RESTORE_FULL_BTN", "UZ"), Messages.get("RESTORE_FULL_BTN", "EN")]:
            # Full Restore (Not implemented safely yet, stick to merge or logic)
            # For now, just do merge as it's safer
            await message.answer("⚠️ Full Restore requires shell access. Performing Smart Merge instead.")
            await BackupService.smart_merge_users(db, file_path)
            
    except Exception as e:
        logger.error(f"Restore error: {e}")
        await message.answer(f"❌ Restore error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.delete()
        await state.clear()
        await message.answer("Done.", reply_markup=get_main_keyboard(lang, settings.ADMIN_ID))
