import io
import time
import traceback
import sys
from PIL import Image
from telebot.types import Message
from md2tgmd import escape
from telebot import TeleBot
from config import conf
from google import genai
from i18n import get_text

gemini_chat_dict = {}
gemini_pro_chat_dict = {}
default_model_dict = {}

model_1 = conf["model_1"]
model_2 = conf["model_2"]

TG_MAX_LENGTH = 4000
search_tool = {'google_search': {}}
client = genai.Client(api_key=sys.argv[2])

def split_by_paragraphs(text: str) -> list[str]:
    return text.split("\n\n")

async def gemini_stream(bot: TeleBot, usr_msg: Message, query_text: str, model_key: str, img_bytes: bytes = None):
    try:
        lang = getattr(usr_msg.from_user, 'language_code', 'en')
        active_telegram_msg = await bot.reply_to(usr_msg, get_text('generating', lang))

        uid = str(usr_msg.from_user.id)
        chat_storage = gemini_chat_dict if model_key == model_1 else gemini_pro_chat_dict
        chat_session = chat_storage.get(uid)
        if not chat_session:
            chat_session = client.aio.chats.create(model=model_key, config={'tools': [search_tool]})
            chat_storage[uid] = chat_session

        content_for_gemini = [query_text, Image.open(io.BytesIO(img_bytes))] if img_bytes else [query_text]
        gemini_response_stream = await chat_session.send_message_stream(content_for_gemini)

        accumulated_response_text = ""
        is_first_response_segment = True
        
        last_prog_update_ts = time.time()
        prog_update_interval = conf.get("streaming_update_interval", 0.5)

        async for chunk in gemini_response_stream:
            if hasattr(chunk, 'text') and chunk.text:
                accumulated_response_text += chunk.text
                current_ts = time.time()

                if current_ts - last_prog_update_ts >= prog_update_interval:
                    if accumulated_response_text.strip():
                        escaped_buffer_for_edit = escape(accumulated_response_text)
                        if len(escaped_buffer_for_edit) < TG_MAX_LENGTH:
                            try:
                                await bot.edit_message_text(
                                    escaped_buffer_for_edit,
                                    chat_id=active_telegram_msg.chat.id,
                                    message_id=active_telegram_msg.message_id,
                                    parse_mode="MarkdownV2"
                                )
                                last_prog_update_ts = current_ts
                            except Exception as e_stream_edit:
                                if "parse markdown" in str(e_stream_edit).lower():
                                    await bot.edit_message_text(
                                        accumulated_response_text,
                                        chat_id=active_telegram_msg.chat.id,
                                        message_id=active_telegram_msg.message_id
                                    )
                                    last_prog_update_ts = current_ts
                                elif "message is not modified" not in str(e_stream_edit).lower():
                                    print(f"Stream edit err: {e_stream_edit}")
                
                response_paragraphs = split_by_paragraphs(accumulated_response_text)
                current_segment_text = ""
                
                for paragraph_content in response_paragraphs:
                    potential_segment_text = current_segment_text + ("\n\n" if current_segment_text else "") + paragraph_content
                    
                    if len(escape(potential_segment_text)) > TG_MAX_LENGTH:
                        if current_segment_text.strip():
                            try:
                                if is_first_response_segment:
                                    await bot.edit_message_text(
                                        escape(current_segment_text),
                                        chat_id=active_telegram_msg.chat.id,
                                        message_id=active_telegram_msg.message_id,
                                        parse_mode="MarkdownV2"
                                    )
                                    is_first_response_segment = False
                                else:
                                    active_telegram_msg = await bot.send_message(
                                        active_telegram_msg.chat.id,
                                        escape(current_segment_text),
                                        reply_to_message_id=active_telegram_msg.message_id,
                                        parse_mode="MarkdownV2"
                                    )
                                last_prog_update_ts = time.time()
                            except Exception as e_main_send:
                                if "parse markdown" in str(e_main_send).lower():
                                    if is_first_response_segment:
                                        await bot.edit_message_text(current_segment_text, chat_id=active_telegram_msg.chat.id, message_id=active_telegram_msg.message_id)
                                        is_first_response_segment = False
                                    else:
                                        active_telegram_msg = await bot.send_message(active_telegram_msg.chat.id, current_segment_text, reply_to_message_id=active_telegram_msg.message_id)
                                    last_prog_update_ts = time.time()
                                else:
                                    print(f"Main send/edit err: {e_main_send}")
                        current_segment_text = paragraph_content
                    else:
                        current_segment_text = potential_segment_text
                
                accumulated_response_text = current_segment_text
        
        if accumulated_response_text.strip():
            try:
                await bot.edit_message_text(
                    escape(accumulated_response_text),
                    chat_id=active_telegram_msg.chat.id,
                    message_id=active_telegram_msg.message_id,
                    parse_mode="MarkdownV2"
                )
            except Exception as e_final:
                if "parse markdown" in str(e_final).lower():
                    await bot.edit_message_text(accumulated_response_text, chat_id=active_telegram_msg.chat.id, message_id=active_telegram_msg.message_id)
                elif "message is too long" in str(e_final).lower():
                    if not is_first_response_segment:
                         await bot.send_message(active_telegram_msg.chat.id, escape(accumulated_response_text), reply_to_message_id=active_telegram_msg.message_id, parse_mode="MarkdownV2")
                    else: 
                         print(f"Final part too long for initial msg: {e_final}")
                elif "message is not modified" not in str(e_final).lower():
                     print(f"Final edit err: {e_final}")

    except Exception as e:
        traceback.print_exc()
        lang = getattr(usr_msg.from_user, 'language_code', 'en')
        await usr_msg.reply_to(f"{get_text('error', lang)} {str(e)}")
