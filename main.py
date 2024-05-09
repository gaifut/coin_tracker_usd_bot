import asyncio
import logging
import os

import requests
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('BOT_TOKEN')
URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
CONVERT_TO_CURRENCY = 'USD'
GREATER_THAN_ZERO = 'Значение должно быть больше 0.'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


class Form(StatesGroup):
    input_symbol = State()
    input_min_value = State()
    input_max_value = State()
    more_pairs = State()


@dp.message_handler(commands=['start'], state='*')
async def start(message: types.Message, state: FSMContext):
    await state.reset_state()
    await Form.input_symbol.set()
    await message.reply(
        'Введите буквенный символ криптовалюты латиницей '
        f'для сравнения с {CONVERT_TO_CURRENCY}. '
        'Например: BTC'
    )


@dp.message_handler(state=Form.input_symbol)
async def input_symbol(message: types.Message, state: FSMContext):
    symbol = message.text.strip().upper()

    if not symbol.isascii():
        await message.reply(
            'Введенные данные не являются разрешенным символом. '
            'Пожалуйста, введите символ криптовалюты латиницей.'
        )
        return

    async with state.proxy() as data:
        data.setdefault('pairs', [])
        data['pairs'].append({'symbol': symbol})
    await Form.next()
    await message.reply(
        f'Введите минимальное пороговое значение {message.text.upper()}, '
        'о достижении которого вы хотите получить уведомление.'
    )


@dp.message_handler(state=Form.input_min_value)
async def input_min_value(message: types.Message, state: FSMContext):
    try:
        input_value = float(message.text)
        if input_value <= 0:
            await message.reply(GREATER_THAN_ZERO)
            return
        async with state.proxy() as data:
            pairs = data['pairs']
            pairs[-1]['input_min'] = float(message.text)
        await Form.next()
        await message.reply('Теперь введите максимальное пороговое значение:')
    except ValueError:
        await message.reply('Введите число.')


@dp.message_handler(state=Form.input_max_value)
async def input_max_value(message: types.Message, state: FSMContext):
    try:
        input_value = float(message.text)
        if input_value <= 0:
            await message.reply(GREATER_THAN_ZERO)
            return
        async with state.proxy() as data:
            pairs = data['pairs']
            pairs[-1]['input_max'] = float(message.text)
            await message.reply('Пара успешно добавлена!')
            await Form.more_pairs.set()
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton('Да'), types.KeyboardButton('Нет'))
            await message.answer(
                'Вы хотите добавить еще одну пару? Да/Нет', reply_markup=markup
            )
    except ValueError:
        await message.reply('Введите число.')


@dp.message_handler(
        lambda message: message.text.lower() in ['да', 'нет'],
        state=Form.more_pairs
    )
async def process_add_more_pairs(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if message.text.lower() == 'да':
            await Form.input_symbol.set()
            await message.reply(
                'Введите 3ех буквенный символ криптовалюты латиницей '
                f'для сравнения с {CONVERT_TO_CURRENCY}. '
            )
        else:
            pairs = data.get('pairs', [])
            if pairs:
                await process_user_inputs(state, message)


@dp.message_handler(commands=['help'], state='*')
async def help_command(message: types.Message):
    help_message = (
        f'Этот бот отслеживает пары крпитовалюта/{CONVERT_TO_CURRENCY}.\n\n'
        'Команды бота:\n'
        '/start - для добавления новой пары в любой момент.\n'
        '/help - Помощь/информация по использованию бота.'
    )
    await message.reply(help_message)


async def process_user_inputs(state, message):
    async with state.proxy() as data:
        pairs = data.get('pairs', [])
        while pairs:
            for pair in pairs:
                symbol = pair['symbol']
                input_min = pair.get('input_min')
                input_max = pair.get('input_max')
                current_value = get_crypto_price(symbol)

                if current_value is None:
                    await message.reply(
                        f'Введенная криптовалюта ({symbol}) не найдена.'
                    )
                    pairs.remove(pair)
                    continue

                if input_min is not None and current_value <= input_min:
                    await message.reply(
                        f'Текущще значние {symbol} = {current_value}. '
                        'Это меньше или равно заданному '
                        f'минимуму {input_min}. '
                        'Бот прекратил отслеживание данной валютной пары.'
                    )
                    pairs.remove(pair)
                if input_max is not None and current_value >= input_max:
                    await message.reply(
                        f'Текущще значние {symbol} = {current_value}. '
                        'Это больше или равно заданному '
                        f'максимуму {input_max}. '
                        'Бот прекратил отслеживание данной валютной пары.'
                    )
                    pairs.remove(pair)
            await asyncio.sleep(10)


def get_crypto_price(symbol):
    try:
        data = requests.get(
            URL,
            params={
                'symbol': f'{symbol}',
                'convert': f'{CONVERT_TO_CURRENCY}',
            },
            headers={
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': API_KEY,
            }
        ).json()
        extract_price = (
            data['data'][f'{symbol}']['quote'][CONVERT_TO_CURRENCY]['price']
        )
        logging.info(
            f'The current price of {symbol} '
            f'in {CONVERT_TO_CURRENCY} is: {extract_price}'
        )
        return extract_price
    except Exception as e:
        logging.error(f'An error occurred: {e}')


async def main():
    await dp.skip_updates()
    await dp.start_polling()

if __name__ == '__main__':
    asyncio.run(main())
