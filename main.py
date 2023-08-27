import os
from threading import Thread
import io

import requests
import soundfile as sf
import pyloudnorm as pyln
from telebot import TeleBot, types
from flask import Flask, request

from replit import Database

app = Flask(__name__)
db = Database(os.environ['REPLIT_DB_URL'])
bot = TeleBot(db['tg_bot_token'])


def handle_telegram():
    if request.content_type == 'application/json' and (
            update := types.Update.de_json(request.stream.read().decode('utf-8'))
    ).message and update.message.chat.id in db['admin_ids']:
        thread = Thread(target=bot.process_new_updates, args=([update],))
        thread.start()

    return ''


def _normalize_audio(audio_bytes: bytes, fileformat: str = 'mp3'):
    data, rate = sf.read(io.BytesIO(audio_bytes))
    loudness = pyln.Meter(rate).integrated_loudness(data)
    if -20 < loudness:
        target_loudness = loudness
    elif -40 < loudness:
        target_loudness = loudness + 15
    else:
        target_loudness = loudness + 20

    loudness_normalized_audio = pyln.normalize.loudness(data, loudness, target_loudness)

    normalized_audio = io.BytesIO()
    sf.write(normalized_audio, loudness_normalized_audio, rate, format=fileformat)
    return normalized_audio.getvalue()


@bot.message_handler(content_types=['voice'])
def normalize_audio(m: types.Message):
    log_m_text = 'Программа скоро должна отправить новую версию голосового сообщения...'
    log_m_id = bot.send_message(
        m.chat.id,
        log_m_text
    ).message_id

    download_url = f'https://api.telegram.org/file/bot{bot.token}/{bot.get_file(m.voice.file_id).file_path}'

    for text in [
        '\nУ программы возникли небольшие трудности со скачиваением голосового сообщения, которое вы отправили. '
        'Придется еще немного подождать.',
        '\nПрограмма все еще пытается скачать голосовое сообщение. Пожалуйста, подождите еще чуть-чуть.',
        '\nПопытавшись три раза, программа не смогла скачать голосовое сообщение. '
        'Просим прощения за доставленные неудобства'
    ]:
        try:
            voice_buffer = io.BytesIO()
            for chunk in requests.get(download_url, timeout=60).iter_content(1024):
                voice_buffer.write(chunk)
        except requests.exceptions.ReadTimeout:
            log_m_text += text
            bot.edit_message_text(log_m_text, m.chat.id, log_m_id)
        else:
            bot.send_voice(
                m.chat.id,
                _normalize_audio(
                    voice_buffer.getvalue()
                ),
                reply_to_message_id=m.message_id
            )
            bot.delete_message(m.chat.id, log_m_id)
            break


def set_up_flask_app(app_to_set_up: Flask):
    app_to_set_up.add_url_rule('/', 'handle_telegram', handle_telegram, methods=['POST'])


if __name__ == '__main__':
    set_up_flask_app(app)
    app.run()

