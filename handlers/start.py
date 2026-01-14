from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command
from constants.messages import Messages
from handlers.common import get_main_keyboard, enable_user_menu, get_contact_keyboard
from services.user_service import UserService

router = Router()
# Only handle private chats - no keyboard buttons in groups
router.message.filter(F.chat.type == "private")

@router.message(CommandStart(), F.chat.type == "private")
@router.message(F.text.in_([Messages.get("START_BTN", "UZ"), Messages.get("START_BTN", "EN")]))
async def cmd_start(message: types.Message, user_service: UserService, state: FSMContext, **kwargs):
    data = kwargs
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    user = await user_service.get_or_create_user(telegram_id)
    if not user or not user.phone_number:
        # Store deep link in state to resume after contact
        args = message.text.split()
        if len(args) > 1:
            await state.update_data(pending_start=args[1])
            
        await message.answer(
            Messages.get("SHARE_CONTACT_PROMPT", lang),
            reply_markup=get_contact_keyboard(lang)
        )
        return

    await enable_user_menu(message.bot, telegram_id)
    
    # Handle deep links
    args = message.text.split()
    if len(args) > 1:
        payload = args[1]
        if payload == "create":
            from handlers.quiz import cmd_create_quiz
            # Correctly passing state
            return await cmd_create_quiz(message, state, user_service)
        elif payload.startswith("quiz_"):
            # Trigger quiz info view
            quiz_id = int(payload.split("_")[1])
            from handlers.quiz import show_quiz_info
            
            # Use injected quiz_service
            quiz_service = data.get("quiz_service")
            if not quiz_service:
                # Fallback if middleware missed it (shouldn't happen)
                from db.session import AsyncSessionLocal
                from services.quiz_service import QuizService
                async with AsyncSessionLocal() as session:
                    quiz_service = QuizService(session)
            
            # Feature: Add to user's list if not already there
            cloned_quiz = await quiz_service.clone_quiz(quiz_id, telegram_id)
            if cloned_quiz:
                await message.answer(Messages.get("QUIZ_ADDED_TO_LIST", lang).format(title=cloned_quiz.title), parse_mode="HTML")
            
            return await show_quiz_info(message.bot, message.chat.id, quiz_id, lang, quiz_service)

    welcome_text = Messages.get("WELCOME", lang) + "\n\n" + Messages.get("FORMAT_INFO", lang)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(lang, telegram_id))
    # Clear any pending start after handling
    await state.clear()

@router.message(F.contact, F.chat.type == "private")
async def process_contact(message: types.Message, user_service: UserService, state: FSMContext, **kwargs):
    data = kwargs
    telegram_id = message.from_user.id
    contact = message.contact
    lang = await user_service.get_language(telegram_id)

    if contact.user_id != telegram_id:
        return

    await user_service.update_user(
        telegram_id=telegram_id,
        phone_number=contact.phone_number,
        full_name=f"{contact.first_name} {contact.last_name}" if contact.last_name else contact.first_name,
        username=message.from_user.username
    )

    await enable_user_menu(message.bot, telegram_id)
    await message.answer(
        Messages.get("CONTACT_SAVED", lang),
        reply_markup=get_main_keyboard(lang, telegram_id)
    )
    
    # Check for pending deep link
    state_data = await state.get_data()
    pending_payload = state_data.get("pending_start")
    if pending_payload:
        # Resume cmd_start with the payload
        new_text = f"/start {pending_payload}"
        new_message = message.model_copy(update={"text": new_text})
        await state.clear()
        return await cmd_start(new_message, user_service, state, **data)

@router.message(Command("help"), F.chat.type == "private")
@router.message(F.text.in_([Messages.get("HELP_BTN", "UZ"), Messages.get("HELP_BTN", "EN")]), F.chat.type == "private")
async def cmd_help(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from core.config import settings

    builder = InlineKeyboardBuilder()
    if settings.ADMIN_ID != 0:
        builder.button(
            text=Messages.get("CONTACT_ADMIN_BTN", lang),
            url=f"tg://user?id={settings.ADMIN_ID}"
        )
    
    await message.answer(
        Messages.get("HELP_TEXT", lang),
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.message(CommandStart(), F.chat.type.in_({"group", "supergroup"}))
async def cmd_start_group(message: types.Message, user_service: UserService, state: FSMContext, redis, **kwargs):
    """Handle /start in groups (Deep Linking only)"""
    args = message.text.split()
    if len(args) < 2:
        return # Ignore bare /start in groups
        
    payload = args[1]
    if not payload.startswith("quiz_"):
        return
        
    # Check admin permission
    member = await message.chat.get_member(message.from_user.id)
    lang = await user_service.get_language(message.from_user.id)
    
    if member.status not in ("administrator", "creator"):
        await message.reply(Messages.get("ONLY_ADMINS", lang))
        return
        
    # Get services
    data = kwargs
    quiz_service = data.get("quiz_service")
    if not quiz_service:
        from db.session import AsyncSessionLocal
        from services.quiz_service import QuizService
        async with AsyncSessionLocal() as session:
            quiz_service = QuizService(session)
            
    # Get quiz
    try:
        quiz_id = int(payload.split("_")[1])
        quiz = await quiz_service.get_quiz(quiz_id)
        if not quiz:
            await message.reply(Messages.get("ERROR_TEST_NOT_FOUND", lang))
            return
            
        # Import start_group_quiz
        from handlers.group import start_group_quiz
        
        # We need session_service.
        session_service = data.get("session_service")
        if not session_service:
             db = data.get("db")
             if db:
                 from services.session_service import SessionService
                 session_service = SessionService(db, redis)
        
        # Use group language preference if set
        group_lang = await redis.get(f"group_lang:{message.chat.id}")
        
        await start_group_quiz(
            message.bot, 
            quiz, 
            message.chat.id, 
            message.from_user.id, 
            group_lang or lang, 
            redis, 
            session_service
        )
        
    except Exception as e:
        from core.logger import logger
        logger.error("Error in cmd_start_group", error=str(e))
