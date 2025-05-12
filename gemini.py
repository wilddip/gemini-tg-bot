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
            escaped_final_text = escape(accumulated_response_text)
            if len(escaped_final_text) <= TG_MAX_LENGTH:
                try:
                    await bot.edit_message_text(
                        escaped_final_text,
                        chat_id=active_telegram_msg.chat.id,
                        message_id=active_telegram_msg.message_id,
                        parse_mode="MarkdownV2"
                    )
                except Exception as e_final_fit:
                    if "parse markdown" in str(e_final_fit).lower():
                        await bot.edit_message_text(accumulated_response_text, chat_id=active_telegram_msg.chat.id, message_id=active_telegram_msg.message_id)
                    elif "message is not modified" not in str(e_final_fit).lower():
                        print(f"Final (fit) edit err: {e_final_fit}")
            else:
                part_for_edit = ""
                remaining_text_for_new_msgs = accumulated_response_text
                
                temp_paras = split_by_paragraphs(accumulated_response_text)
                for k_idx in range(len(temp_paras), 0, -1):
                    potential_edit_part = "\n\n".join(temp_paras[:k_idx])
                    if len(escape(potential_edit_part)) <= TG_MAX_LENGTH:
                        part_for_edit = potential_edit_part
                        remaining_text_for_new_msgs = "\n\n".join(temp_paras[k_idx:])
                        break
                
                if part_for_edit.strip():
                    try:
                        await bot.edit_message_text(
                            escape(part_for_edit),
                            chat_id=active_telegram_msg.chat.id,
                            message_id=active_telegram_msg.message_id,
                            parse_mode="MarkdownV2"
                        )
                        if is_first_response_segment: is_first_response_segment = False
                    except Exception as e_edit_pfe:
                        if "parse markdown" in str(e_edit_pfe).lower():
                            await bot.edit_message_text(part_for_edit, chat_id=active_telegram_msg.chat.id, message_id=active_telegram_msg.message_id)
                            if is_first_response_segment: is_first_response_segment = False
                        elif "message is not modified" not in str(e_edit_pfe).lower():
                            print(f"Error editing final split part: {e_edit_pfe}")
                    
                    if remaining_text_for_new_msgs.strip():
                        await send_text_in_segments(bot, active_telegram_msg.chat.id, remaining_text_for_new_msgs, active_telegram_msg.message_id, lang)
                else: 
                    target_reply_id = usr_msg.message_id if is_first_response_segment else active_telegram_msg.message_id
                    if accumulated_response_text.strip():
                         await send_text_in_segments(bot, active_telegram_msg.chat.id, accumulated_response_text, target_reply_id, lang)

    except Exception as e:
        traceback.print_exc()
        lang = getattr(usr_msg.from_user, 'language_code', 'en')
        await bot.reply_to(usr_msg, f"{get_text('error', lang)} {str(e)}")
