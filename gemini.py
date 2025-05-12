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

async def send_text_in_segments(bot: TeleBot, chat_id: int, text_content: str, initial_reply_to_id: int, lang: str):
    if not text_content.strip():
        return

    paragraphs = split_by_paragraphs(text_content)
    current_segment = ""
    last_sent_msg_id = initial_reply_to_id

    for i, p_text in enumerate(paragraphs):
        potential_segment = current_segment + ("\n\n" if current_segment else "") + p_text
        escaped_potential_segment = escape(potential_segment)

        if len(escaped_potential_segment) > TG_MAX_LENGTH:
            if current_segment.strip():
                try:
                    sent_msg = await bot.send_message(chat_id, escape(current_segment), reply_to_message_id=last_sent_msg_id, parse_mode="MarkdownV2")
                    last_sent_msg_id = sent_msg.message_id
                except Exception as e_send_seg:
                    if "parse markdown" in str(e_send_seg).lower():
                        sent_msg = await bot.send_message(chat_id, current_segment, reply_to_message_id=last_sent_msg_id)
                        last_sent_msg_id = sent_msg.message_id
                    else:
                        print(f"Err in send_text_in_segments: {e_send_seg}")
            current_segment = p_text
            if len(escape(current_segment)) > TG_MAX_LENGTH:
                try:
                    sent_msg = await bot.send_message(chat_id, escape(current_segment), reply_to_message_id=last_sent_msg_id, parse_mode="MarkdownV2")
                    last_sent_msg_id = sent_msg.message_id
                except Exception as e_send_long_p:
                    print(f"Err sending too-long paragraph in send_text_in_segments: {e_send_long_p}")
                current_segment = "" 
        else:
            current_segment = potential_segment
    
    if current_segment.strip():
        try:
            await bot.send_message(chat_id, escape(current_segment), reply_to_message_id=last_sent_msg_id, parse_mode="MarkdownV2")
        except Exception as e_send_final_seg:
            if "parse markdown" in str(e_send_final_seg).lower():
                await bot.send_message(chat_id, current_segment, reply_to_message_id=last_sent_msg_id)
            else:
                print(f"Err in send_text_in_segments (final): {e_send_final_seg}")

async def gemini_stream(bot: TeleBot, usr_msg: Message, query_text: str, model_key: str, img_bytes: bytes = None):
    try:
        lang = getattr(usr_msg.from_user, 'language_code', 'en')
        active_msg = await bot.reply_to(usr_msg, get_text('generating', lang))

        uid = str(usr_msg.from_user.id)
        chat_storage = gemini_chat_dict if model_key == model_1 else gemini_pro_chat_dict
        chat_session = chat_storage.get(uid)
        if not chat_session:
            chat_session = client.aio.chats.create(model=model_key, config={'tools': [search_tool]})
            chat_storage[uid] = chat_session

        content_for_gemini = [query_text, Image.open(io.BytesIO(img_bytes))] if img_bytes else [query_text]
        gemini_response_stream = await chat_session.send_message_stream(content_for_gemini)

        buffer = ""
        last_update_time = time.time()
        update_interval = conf.get("streaming_update_interval", 0.5)

        async for chunk in gemini_response_stream:
            if hasattr(chunk, 'text') and chunk.text:
                buffer += chunk.text
                current_time = time.time()

                if len(escape(buffer)) > TG_MAX_LENGTH:
                    try:
                        active_msg = await bot.send_message(
                            active_msg.chat.id,
                            escape(buffer),
                            reply_to_message_id=active_msg.message_id,
                            parse_mode="MarkdownV2"
                        )
                        buffer = ""
                        last_update_time = current_time
                    except Exception as e_overflow:
                        if "parse markdown" in str(e_overflow).lower():
                            active_msg = await bot.send_message(
                                active_msg.chat.id,
                                buffer,
                                reply_to_message_id=active_msg.message_id
                            )
                            buffer = ""
                            last_update_time = current_time
                        else:
                            print(f"Error creating new message on overflow: {e_overflow}")
                
                elif buffer and current_time - last_update_time >= update_interval:
                    try:
                        await bot.edit_message_text(
                            escape(buffer),
                            chat_id=active_msg.chat.id,
                            message_id=active_msg.message_id,
                            parse_mode="MarkdownV2"
                        )
                        last_update_time = current_time
                    except Exception as e_update:
                        if "parse markdown" in str(e_update).lower():
                            await bot.edit_message_text(
                                buffer,
                                chat_id=active_msg.chat.id,
                                message_id=active_msg.message_id
                            )
                            last_update_time = current_time
                        elif "message is too long" in str(e_update).lower():
                            try:
                                active_msg = await bot.send_message(
                                    active_msg.chat.id,
                                    escape(buffer),
                                    reply_to_message_id=active_msg.message_id,
                                    parse_mode="MarkdownV2"
                                )
                                buffer = ""
                                last_update_time = current_time
                            except Exception as e_new_msg:
                                if "parse markdown" in str(e_new_msg).lower():
                                    active_msg = await bot.send_message(
                                        active_msg.chat.id,
                                        buffer,
                                        reply_to_message_id=active_msg.message_id
                                    )
                                    buffer = ""
                                    last_update_time = current_time
                                else:
                                    print(f"Error creating new message after too-long error: {e_new_msg}")
                        elif "message is not modified" not in str(e_update).lower():
                            print(f"Update error: {e_update}")

        if buffer:
            try:
                await bot.edit_message_text(
                    escape(buffer),
                    chat_id=active_msg.chat.id,
                    message_id=active_msg.message_id,
                    parse_mode="MarkdownV2"
                )
            except Exception as e_final:
                if "parse markdown" in str(e_final).lower():
                    await bot.edit_message_text(
                        buffer,
                        chat_id=active_msg.chat.id,
                        message_id=active_msg.message_id
                    )
                elif "message is too long" in str(e_final).lower():
                    try:
                        await bot.send_message(
                            active_msg.chat.id,
                            escape(buffer),
                            reply_to_message_id=active_msg.message_id,
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e_final_new:
                        if "parse markdown" in str(e_final_new).lower():
                            await bot.send_message(
                                active_msg.chat.id,
                                buffer,
                                reply_to_message_id=active_msg.message_id
                            )
                        else:
                            print(f"Error sending final new message: {e_final_new}")
                elif "message is not modified" not in str(e_final).lower():
                    print(f"Final update error: {e_final}")

    except Exception as e:
        traceback.print_exc()
        lang = getattr(usr_msg.from_user, 'language_code', 'en')
        error_text = str(e)
        if 'google.genai.errors.ServerError' in error_text or 'INTERNAL' in error_text:
            await bot.reply_to(usr_msg, f"{get_text('error', lang)} [Gemini 500]")
        else:
            await bot.reply_to(usr_msg, f"{get_text('error', lang)} {error_text}")
