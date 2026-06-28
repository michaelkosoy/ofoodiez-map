import os
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Increase global timeouts for Telegram API to prevent read timeouts on large images
apihelper.READ_TIMEOUT = 120
apihelper.CONNECT_TIMEOUT = 120
from telegram_bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, validate_config
from telegram_bot.parsers.popup import PopupParser
from telegram_bot.parsers.happy_hour import HappyHourParser
from telegram_bot.handlers.popup import PopupHandler
from telegram_bot.handlers.happy_hour import HappyHourHandler

# Reference to the Flask application for database contexts
_flask_app = None

# Global state to keep track of user modes and pending data
user_states = {}

def get_bot():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        return None
    try:
        return telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    except Exception as e:
        print(f"❌ Error initializing Telegram Bot: {e}")
        return None

bot = get_bot()

# Helper to verify message sender
def is_authorized(user_id):
    if not TELEGRAM_USER_ID or TELEGRAM_USER_ID == "your_telegram_user_id_here":
        # If not configured, block by default for safety
        return False
    return str(user_id) == str(TELEGRAM_USER_ID)

# Registry for Strategy Pattern
PARSERS = {
    'popup': PopupParser(),
    'happyhour': HappyHourParser()
}

HANDLERS = {
    'popup': PopupHandler(),
    'happyhour': HappyHourHandler()
}

def send_mode_selection(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("🍷 Happy Hour Place", callback_data="mode_happyhour"),
        InlineKeyboardButton("📅 Calendar Pop-up Event", callback_data="mode_popup"),
        InlineKeyboardButton("💡 Other / General Info", callback_data="mode_other")
    )
    
    if bot:
        bot.send_message(
            chat_id,
            "👋 Welcome! What type of content would you like to add to Ofoodiez today?",
            reply_markup=markup
        )

if bot:
    # Handler for /start and /reset commands
    @bot.message_handler(commands=['start', 'reset', 'help'])
    def handle_commands(message):
        if not is_authorized(message.from_user.id):
            bot.reply_to(message, "🚫 Access Denied. You are not authorized to use this bot.")
            return
            
        chat_id = message.chat.id
        user_states[chat_id] = {'mode': None, 'pending_data': None, 'editing_field': None, 'edit_message_id': None, 'prompt_message_id': None}
        send_mode_selection(chat_id)

    @bot.message_handler(commands=['searchplace'])
    def handle_search_place(message):
        if not is_authorized(message.from_user.id): return
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Usage: `/searchplace <name>`\nExample: `/searchplace Leny`", parse_mode="Markdown")
            return
            
        query = args[1].lower()
        global _flask_app
        if not _flask_app: return
        
        with _flask_app.app_context():
            from database.models import HappyHourPlace
            places = HappyHourPlace.query.filter(HappyHourPlace.name.ilike(f"%{query}%")).limit(10).all()
            
            if not places:
                bot.reply_to(message, f"❌ No places found matching '{query}'.")
                return
                
            response = "🔍 **Search Results:**\n\n"
            for p in places:
                response += f"🆔 **ID:** {p.id}\n🍷 **Name:** {p.name}\n📍 **Address:** {p.address}\n---\n"
            
            response += "\nTo delete a place, use: `/deleteplace <ID>`"
            bot.reply_to(message, response, parse_mode="Markdown")

    @bot.message_handler(commands=['deleteplace'])
    def handle_delete_place(message):
        if not is_authorized(message.from_user.id): return
        
        args = message.text.split(maxsplit=1)
        if len(args) < 2 or not args[1].isdigit():
            bot.reply_to(message, "⚠️ Usage: `/deleteplace <ID>`\nExample: `/deleteplace 15`", parse_mode="Markdown")
            return
            
        place_id = int(args[1])
        global _flask_app
        if not _flask_app: return
        
        with _flask_app.app_context():
            from database.models import db, HappyHourPlace
            place = HappyHourPlace.query.get(place_id)
            if not place:
                bot.reply_to(message, f"❌ No place found with ID {place_id}.")
                return
                
            name = place.name
            db.session.delete(place)
            db.session.commit()
            bot.reply_to(message, f"✅ Successfully deleted '{name}' from the database.")

    # Callback Query Handler for selections
    @bot.callback_query_handler(func=lambda call: call.data.startswith('mode_'))
    def handle_mode_callbacks(call):
        if not is_authorized(call.from_user.id):
            bot.answer_callback_query(call.id, "🚫 Access Denied.")
            return

        chat_id = call.message.chat.id
        selected_mode = call.data.replace('mode_', '')
        
        if selected_mode == 'other':
            bot.edit_message_text(
                "💡 Mode set to: **Other**\nCurrently, custom text processing is not linked to database structures. Use /reset to switch back.",
                chat_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
            return

        user_states[chat_id] = {'mode': selected_mode, 'pending_data': None, 'editing_field': None, 'edit_message_id': None, 'prompt_message_id': None}
        
        mode_names = {
            'popup': '📅 Calendar Pop-up Event',
            'happyhour': '🍷 Happy Hour Place'
        }
        
        bot.edit_message_text(
            f"✅ Mode set to: **{mode_names.get(selected_mode)}**\n\n"
            "Please send the text details or upload a photo flyer. I will parse it using Gemini AI!",
            chat_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, f"Mode set to {selected_mode}")

    # Callback Query Handler for Approve/Edit/Discard buttons
    @bot.callback_query_handler(func=lambda call: call.data in [
        'action_approve', 'action_edit', 'action_discard', 'action_back_to_confirm',
        'action_update_duplicate', 'action_save_new'
    ])
    def handle_action_callbacks(call):
        if not is_authorized(call.from_user.id):
            bot.answer_callback_query(call.id, "🚫 Access Denied.")
            return

        chat_id = call.message.chat.id
        state = user_states.get(chat_id)
        
        if not state or not state.get('pending_data'):
            bot.send_message(chat_id, "⚠️ No pending data found. Send details first or start over with /reset.")
            bot.answer_callback_query(call.id)
            return

        active_mode = state['mode']
        pending = state['pending_data']
        
        if call.data == 'action_back_to_confirm':
            show_confirmation_message(chat_id, call.message.message_id, active_mode, pending)
            bot.answer_callback_query(call.id)
            return
            
        if call.data == 'action_edit':
            markup = InlineKeyboardMarkup()
            markup.row_width = 2
            
            if active_mode == 'popup':
                fields = ['title', 'date', 'time', 'location', 'location_link', 'instagram_username', 'instagram_link', 'description']
            else:
                fields = ['name', 'name_hebrew', 'address', 'city', 'google_maps_link', 'opening_hours', 'description', 'recommended', 'instagram_username', 'instagram_link', 'reservation_link']
            
            buttons = [InlineKeyboardButton(f"✏️ {f.replace('_', ' ').title()}", callback_data=f"edit_field_{f}") for f in fields]
            markup.add(*buttons)
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="action_back_to_confirm"))
            
            bot.edit_message_reply_markup(
                chat_id,
                call.message.message_id,
                reply_markup=markup
            )
            bot.answer_callback_query(call.id)
            return

        global _flask_app
        if not _flask_app:
            bot.edit_message_text("❌ App error: Flask context is missing.", chat_id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        handler = HANDLERS.get(active_mode)
        if not handler:
            bot.edit_message_text(f"❌ Error: No handler found for mode '{active_mode}'.", chat_id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return

        if call.data == 'action_approve':
            # Check for duplicates before approving for Happy Hour
            if active_mode == 'happyhour':
                duplicate = handler.check_duplicate(_flask_app, pending)
                if duplicate:
                    state['duplicate_id'] = duplicate.get('id')
                    markup = InlineKeyboardMarkup()
                    markup.row_width = 1
                    markup.add(
                        InlineKeyboardButton("🔄 Update Existing Place", callback_data="action_update_duplicate"),
                        InlineKeyboardButton("➕ Save as New Row Anyway", callback_data="action_save_new"),
                        InlineKeyboardButton("❌ Cancel / Discard", callback_data="action_discard")
                    )
                    bot.edit_message_text(
                        f"⚠️ **Duplicate Found!**\n\nA place named '{duplicate.get('Name')}' already exists in the database (ID: {duplicate.get('id')}).\n\n"
                        f"**Existing Address:** {duplicate.get('Address')}\n"
                        f"**New Address:** {pending.get('address')}\n\n"
                        "What would you like to do?",
                        chat_id,
                        call.message.message_id,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                    bot.answer_callback_query(call.id)
                    return

            # If no duplicate, or it's a popup, proceed as normal
            call.data = 'action_save_new'

        if call.data == 'action_update_duplicate':
            bot.edit_message_text("💾 Updating existing database row...", chat_id, call.message.message_id)
            duplicate_id = state.get('duplicate_id')
            if not duplicate_id:
                bot.edit_message_text("❌ Error: Lost track of duplicate ID.", chat_id, call.message.message_id)
                bot.answer_callback_query(call.id)
                return
                
            success = handler.update(_flask_app, duplicate_id, pending)
            if success:
                bot.edit_message_text(
                    f"🎉 **Success!**\n\nThe place '{pending.get('name')}' has been updated!",
                    chat_id,
                    call.message.message_id,
                    parse_mode="Markdown"
                )
                user_states[chat_id] = {'mode': None, 'pending_data': None}
            else:
                bot.edit_message_text(
                    "❌ **Error:** Failed to update database. Please check server logs.",
                    chat_id,
                    call.message.message_id,
                    parse_mode="Markdown"
                )

        elif call.data == 'action_save_new':
            bot.edit_message_text("💾 Uploading and saving details to database...", chat_id, call.message.message_id)
            success = handler.save(_flask_app, pending)
            
            title_key = 'title' if active_mode == 'popup' else 'name'
            if success:
                bot.edit_message_text(
                    f"🎉 **Success!**\n\nThe item '{pending.get(title_key)}' is now saved!",
                    chat_id,
                    call.message.message_id,
                    parse_mode="Markdown"
                )
                user_states[chat_id] = {'mode': None, 'pending_data': None}
            else:
                bot.edit_message_text(
                    "❌ **Error:** Failed to save to database. Please check server logs.",
                    chat_id,
                    call.message.message_id,
                    parse_mode="Markdown"
                )

        elif call.data == 'action_discard':
            bot.edit_message_text(
                "🗑️ **Discarded.**\n\nNo changes were made. You can send new flyer details or type /reset to change the mode.",
                chat_id,
                call.message.message_id,
                parse_mode="Markdown"
            )
            state['pending_data'] = None
            
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_field_'))
    def handle_edit_field(call):
        if not is_authorized(call.from_user.id):
            bot.answer_callback_query(call.id, "🚫 Access Denied.")
            return

        chat_id = call.message.chat.id
        state = user_states.get(chat_id)
        if not state or not state.get('pending_data'):
            bot.answer_callback_query(call.id, "No pending data found.")
            return
            
        field_to_edit = call.data.replace('edit_field_', '')
        state['editing_field'] = field_to_edit
        state['edit_message_id'] = call.message.message_id
        
        prompt_msg = bot.send_message(
            chat_id,
            f"Please send the new text for **{field_to_edit.replace('_', ' ').title()}**:",
            parse_mode="Markdown"
        )
        state['prompt_message_id'] = prompt_msg.message_id
        bot.answer_callback_query(call.id)

    # Handler for photo uploads
    @bot.message_handler(content_types=['photo'])
    def handle_photo(message):
        if not is_authorized(message.from_user.id):
            bot.reply_to(message, "🚫 Access Denied.")
            return

        chat_id = message.chat.id
        state = user_states.get(chat_id)
        
        if not state or not state.get('mode'):
            bot.reply_to(message, "⚠️ No mode selected. Please select a mode first.")
            send_mode_selection(chat_id)
            return

        active_mode = state['mode']
        parser = PARSERS.get(active_mode)
        
        if not parser:
            bot.reply_to(message, f"❌ Active mode '{active_mode}' is not supported for flyer parsing yet.")
            return

        processing_msg = bot.reply_to(message, "⏳ Downloading photo and parsing flyer details with Gemini AI...")
        
        try:
            # Download the photo with custom timeout
            import requests
            file_info = bot.get_file(message.photo[-1].file_id)
            url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            downloaded_file = response.content
            
            # Determine extension/mime-type
            ext = os.path.splitext(file_info.file_path)[1].lower()
            mime_type = "image/jpeg"
            if ext == ".png":
                mime_type = "image/png"
            elif ext == ".webp":
                mime_type = "image/webp"

            # Parse image
            parsed_data = parser.parse_image(downloaded_file, mime_type)
            state['pending_data'] = parsed_data
            
            if active_mode == 'popup' and not parsed_data.get('date'):
                state['editing_field'] = 'date'
                state['edit_message_id'] = processing_msg.message_id
                
                bot.edit_message_text(
                    "✅ Flyer parsed, but I couldn't find the date.",
                    chat_id,
                    processing_msg.message_id
                )
                
                prompt_msg = bot.send_message(
                    chat_id,
                    "⚠️ Please reply with the **date** for this event (e.g., YYYY-MM-DD or DD.MM):",
                    parse_mode="Markdown"
                )
                state['prompt_message_id'] = prompt_msg.message_id
                return
            
            # Format and display confirmation message
            show_confirmation_message(chat_id, processing_msg.message_id, active_mode, parsed_data)
            
        except Exception as e:
            bot.edit_message_text(
                f"❌ **Error parsing photo:**\n\n{str(e)}\n\nPlease try again or use /reset.",
                chat_id,
                processing_msg.message_id
            )

    # Handler for text messages
    @bot.message_handler(func=lambda message: True)
    def handle_text(message):
        if not is_authorized(message.from_user.id):
            bot.reply_to(message, "🚫 Access Denied.")
            return

        chat_id = message.chat.id
        state = user_states.get(chat_id)
        
        if not state or not state.get('mode'):
            send_mode_selection(chat_id)
            return

        if state.get('editing_field'):
            # Update the field with the new text
            field = state['editing_field']
            state['pending_data'][field] = message.text
            state['editing_field'] = None
            
            try:
                bot.delete_message(chat_id, message.message_id)
                if state.get('prompt_message_id'):
                    bot.delete_message(chat_id, state['prompt_message_id'])
            except:
                pass
                
            edit_msg_id = state.get('edit_message_id')
            if edit_msg_id:
                show_confirmation_message(chat_id, edit_msg_id, state['mode'], state['pending_data'])
            else:
                processing_msg = bot.reply_to(message, "✅ Field updated.")
                show_confirmation_message(chat_id, processing_msg.message_id, state['mode'], state['pending_data'])
            return

        active_mode = state['mode']
        parser = PARSERS.get(active_mode)
        
        if not parser:
            bot.reply_to(message, f"❌ Active mode '{active_mode}' is not supported yet.")
            return

        processing_msg = bot.reply_to(message, "⏳ Parsing details with Gemini AI...")
        
        try:
            # Parse text
            parsed_data = parser.parse_text(message.text)
            state['pending_data'] = parsed_data
            
            if active_mode == 'popup' and not parsed_data.get('date'):
                state['editing_field'] = 'date'
                state['edit_message_id'] = processing_msg.message_id
                
                bot.edit_message_text(
                    "✅ Text parsed, but I couldn't find the date.",
                    chat_id,
                    processing_msg.message_id
                )
                
                prompt_msg = bot.send_message(
                    chat_id,
                    "⚠️ Please reply with the **date** for this event (e.g., YYYY-MM-DD or DD.MM):",
                    parse_mode="Markdown"
                )
                state['prompt_message_id'] = prompt_msg.message_id
                return
            
            # Format and display confirmation message
            show_confirmation_message(chat_id, processing_msg.message_id, active_mode, parsed_data)
            
        except Exception as e:
            bot.edit_message_text(
                f"❌ **Error parsing text:**\n\n{str(e)}\n\nPlease try again or use /reset.",
                chat_id,
                processing_msg.message_id
            )

def show_confirmation_message(chat_id, message_id, mode, data):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("✅ Approve & Upload", callback_data="action_approve"),
        InlineKeyboardButton("✏️ Edit Fields", callback_data="action_edit")
    )
    markup.add(InlineKeyboardButton("❌ Discard", callback_data="action_discard"))
    
    if mode == 'popup':
        msg_text = (
            "🔍 **Extracted Pop-up Details:**\n\n"
            f"🏷️ **Title**: {data.get('title')}\n"
            f"📅 **Date**: {data.get('date')}\n"
            f"⏰ **Time**: {data.get('time')}\n"
            f"📍 **Location**: {data.get('location')}\n"
            f"🗺️ **Maps Link**: {data.get('location_link') or 'None'}\n"
            f"💬 **Insta Tag**: {data.get('instagram_username') or 'None'}\n"
            f"🔗 **Insta Link**: {data.get('instagram_link') or 'None'}\n"
            f"📝 **Description**: {data.get('description')}\n\n"
            "Would you like to approve and publish this to the website?"
        )
    else:  # happyhour or default
        msg_text = (
            "🔍 **Extracted Happy Hour Details:**\n\n"
            f"🏷️ **Name**: {data.get('name')}\n"
            f"🔤 **Hebrew**: {data.get('name_hebrew') or '—'}\n"
            f"📍 **Address**: {data.get('address')}\n"
            f"🏙️ **City**: {data.get('city') or '—'}\n"
            f"🗺️ **Maps**: {data.get('google_maps_link') or '—'}\n"
            f"⏰ **Hours**: {data.get('opening_hours')}\n"
            f"📝 **Description**: {data.get('description')}\n"
            f"🎬 **Video**: {data.get('recommended') or '—'}\n"
            f"💬 **Insta**: {data.get('instagram_username') or '—'}\n"
            f"🔗 **Insta Link**: {data.get('instagram_link') or '—'}\n"
            f"🎟️ **Reservation**: {data.get('reservation_link') or '—'}\n"
            f"✡️ **Kosher**: {'Yes' if data.get('kosher') else 'No'}\n\n"
            "Would you like to approve and publish this?"
        )
        
    if bot:
        bot.edit_message_text(
            msg_text,
            chat_id,
            message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

def run_bot(app):
    """Start the bot thread with the Flask app context."""
    global _flask_app, bot
    _flask_app = app
    
    if not bot:
        print("⚠️ Telegram Bot Token is not configured. Bot listener cannot start.")
        return
        
    if not validate_config():
        print("⚠️ Telegram Bot starting aborted due to missing configuration.")
        return
        
    print("🤖 Telegram Bot initialized successfully and starting listener thread...")
    import time
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Telegram Bot polling crashed: {e}. Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    # Standard standalone run for debugging
    from app import app as flask_app
    validate_config()
    run_bot(flask_app)
