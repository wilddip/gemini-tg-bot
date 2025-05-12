I18N = {
    'generating': {
        'en': '🤖 Generating...',
        'ru': '🤖 Генерирую...'
    },
    'error': {
        'en': '⚠️⚠️⚠️\nSomething went wrong!\nPlease try to change your prompt!',
        'ru': '⚠️⚠️⚠️\nЧто-то пошло не так!\nПопробуй изменить запрос!'
    },
    'history_cleared': {
        'en': 'Your history has been cleared',
        'ru': 'Вся история очищена'
    },
    'only_private': {
        'en': 'This command is only for private chat!',
        'ru': 'Эта команда только для лички!'
    },
    'now_using': {
        'en': 'Now you are using ',
        'ru': 'Теперь ты используешь '
    },
    'welcome': {
        'en': 'Welcome! You can ask me questions now.',
        'ru': 'Добро пожаловать! Можешь задавать вопросы.'
    },
    'add_after_flash': {
        'en': 'Please add what you want to say after /flash. For example: /flash Who is john lennon?',
        'ru': 'Добавь текст после /flash. Например: /flash Кто такой Джон Леннон?'
    },
    'add_after_pro': {
        'en': 'Please add what you want to say after /pro. For example: /pro Who is john lennon?',
        'ru': 'Добавь текст после /pro. Например: /pro Кто такой Джон Леннон?'
    },
    'loading_pic': {
        'en': '🤖 Loading picture...',
        'ru': '🤖 Загружаю картинку...'
    }
}

def get_text(key, lang):
    lang = (lang or 'en').split('-')[0]
    return I18N.get(key, {}).get(lang, I18N.get(key, {}).get('en', '')) 