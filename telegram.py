import logging
import queue
from base64 import b64decode, b64encode
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
from tempfile import TemporaryFile
from typing import Any, Awaitable, Callable, Dict, List, Optional, Text

import requests
from rasa.core.channels.channel import InputChannel, OutputChannel, UserMessage
from rasa.shared.constants import INTENT_MESSAGE_PREFIX
from rasa.shared.core.constants import USER_INTENT_RESTART
from sanic import Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse
from telebot import TeleBot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    Update,
)

from voice_interface import synthesize_text, transcribe_audio

logger = logging.getLogger(__name__)


class TelegramOutput(TeleBot, OutputChannel):
    """Output channel for Telegram."""

    # skipcq: PYL-W0236
    @classmethod
    def name(cls) -> Text:
        return 'telegram'

    def __init__(self, access_token: Optional[Text]) -> None:
        super().__init__(access_token)
        self.users = defaultdict(UserHistory)

    async def _extract_text_from_voice(self, msg: Message) -> Text:
        bot_token = self.token
        file_id = msg.voice.file_id
        file_path_url = 'https://api.telegram.org/bot{}/getFile?file_id={}'.format(
            bot_token, file_id
        )
        file_path = requests.get(file_path_url)
        file_path = file_path.json().get('result').get('file_path')
        download_path = 'https://api.telegram.org/file/bot{}/{}'.format(
            bot_token, file_path
        )
        audio = requests.get(download_path, stream=True)
        encoded = b64encode(audio.raw.data)
        message = encoded.decode()
        text = transcribe_audio(message)
        return text.strip()

    async def _create_voice_response(self, text: Text) -> BytesIO:
        encoded = synthesize_text(text)
        if encoded is None:
            return None
        decode_string = b64decode(encoded)
        with TemporaryFile() as fp:
            fp.write(decode_string)
            fp.seek(0)
            return fp.read()

    async def send_text_message(
        self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        message_type = self.users[recipient_id].get()
        for message_part in text.strip().split('\n\n'):
            if message_type == 'audio':
                audio = await self._create_voice_response(text)
                if audio:
                    self.send_voice(recipient_id, BytesIO(audio))
            self.send_message(recipient_id, message_part)

    async def send_image_url(
        self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        self.send_photo(recipient_id, image)

    async def send_text_with_buttons(
        self,
        recipient_id: Text,
        text: Text,
        buttons: List[Dict[Text, Any]],
        button_type: Optional[Text] = 'inline',
        **kwargs: Any,
    ) -> None:
        """Sends a message with keyboard.

        For more information: https://core.telegram.org/bots#keyboards

        :button_type inline: horizontal inline keyboard

        :button_type vertical: vertical inline keyboard

        :button_type reply: reply keyboard
        """
        if button_type == 'inline':
            button_list = [
                [
                    InlineKeyboardButton(s['title'], callback_data=s['payload'])
                    for s in buttons
                ]
            ]
            reply_markup = InlineKeyboardMarkup(button_list)

        elif button_type == 'vertical':
            button_list = [
                [InlineKeyboardButton(s['title'], callback_data=s['payload'])]
                for s in buttons
            ]
            reply_markup = InlineKeyboardMarkup(button_list)

        elif button_type == 'reply':
            button_list = []
            for bttn in buttons:
                if isinstance(bttn, list):
                    button_list.append([KeyboardButton(s['title']) for s in bttn])
                else:
                    button_list.append([KeyboardButton(bttn['title'])])
            reply_markup = ReplyKeyboardMarkup(
                button_list, resize_keyboard=True, one_time_keyboard=True
            )
        else:
            logger.error(
                'Trying to send text with buttons for unknown '
                'button type {}'.format(button_type)
            )
            return

        message_type = self.users[recipient_id].get()
        if message_type == 'audio':
            audio = await self._create_voice_response(text)
            if audio:
                self.send_voice(recipient_id, BytesIO(audio))
        self.send_message(recipient_id, text, reply_markup=reply_markup)

    async def send_custom_json(
        self, recipient_id: Text, json_message: Dict[Text, Any], **kwargs: Any
    ) -> None:
        json_message = deepcopy(json_message)

        recipient_id = json_message.pop('chat_id', recipient_id)

        send_functions = {
            ('text',): 'send_message',
            ('photo',): 'send_photo',
            ('audio',): 'send_audio',
            ('document',): 'send_document',
            ('sticker',): 'send_sticker',
            ('video',): 'send_video',
            ('video_note',): 'send_video_note',
            ('animation',): 'send_animation',
            ('voice',): 'send_voice',
            ('media',): 'send_media_group',
            ('latitude', 'longitude', 'title', 'address'): 'send_venue',
            ('latitude', 'longitude'): 'send_location',
            ('phone_number', 'first_name'): 'send_contact',
            ('game_short_name',): 'send_game',
            ('action',): 'send_chat_action',
            (
                'title',
                'decription',
                'payload',
                'provider_token',
                'start_parameter',
                'currency',
                'prices',
            ): 'send_invoice',
        }

        for params in send_functions.keys():
            if all(json_message.get(p) is not None for p in params):
                args = [json_message.pop(p) for p in params]
                api_call = getattr(self, send_functions[params])
                api_call(recipient_id, *args, **json_message)


class TelegramInput(InputChannel):
    """Telegram input channel"""

    @classmethod
    def name(cls) -> Text:
        return 'telegram'

    @classmethod
    def from_credentials(cls, credentials: Optional[Dict[Text, Any]]) -> InputChannel:
        if not credentials:
            cls.raise_missing_credentials_exception()

        return cls(
            credentials.get('access_token'),
            credentials.get('verify'),
            credentials.get('webhook_url'),
        )

    def __init__(
        self,
        access_token: Optional[Text],
        verify: Optional[Text],
        webhook_url: Optional[Text],
        debug_mode: bool = True,
    ) -> None:
        self.access_token = access_token
        self.verify = verify
        self.webhook_url = webhook_url
        self.debug_mode = debug_mode

    @staticmethod
    def _is_location(message) -> bool:
        return message.location is not None

    @staticmethod
    def _is_user_message(message) -> bool:
        return message.text is not None

    @staticmethod
    def _is_button(message) -> bool:
        return message.callback_query is not None

    @staticmethod
    def _is_voice_message(message) -> bool:
        return message.voice is not None

    def blueprint(
        self, on_new_message: Callable[[UserMessage], Awaitable[Any]]
    ) -> Blueprint:
        telegram_webhook = Blueprint('telegram_webhook', __name__)
        out_channel = self.get_output_channel()

        @telegram_webhook.route('/', methods=['GET'])
        async def health(_: Request) -> HTTPResponse:
            return response.json({'status': 'ok'})

        @telegram_webhook.route('/set_webhook', methods=['GET', 'POST'])
        async def set_webhook(_: Request) -> HTTPResponse:
            s = out_channel.setWebhook(self.webhook_url)
            if s:
                logger.info('Webhook Setup Successful')
                return response.text('Webhook setup successful')
            else:
                logger.warning('Webhook Setup Failed')
                return response.text('Invalid webhook')

        @telegram_webhook.route('/webhook', methods=['GET', 'POST'])
        async def message(request: Request) -> Any:
            if request.method == 'POST':

                request_dict = request.json
                update = Update.de_json(request_dict)
                if not out_channel.get_me().username == self.verify:
                    logger.debug('Invalid access token, check it matches Telegram')
                    return response.text('failed')

                message_type = 'text'
                if self._is_button(update):
                    msg = update.callback_query.message
                    text = update.callback_query.data
                else:
                    msg = update.message
                    if self._is_user_message(msg):
                        text = msg.text.replace('/bot', '')
                    elif self._is_location(msg):
                        text = '{{"lng":{0}, "lat":{1}}}'.format(
                            msg.location.longitude, msg.location.latitude
                        )
                    elif self._is_voice_message(msg):
                        text = await out_channel._extract_text_from_voice(msg)
                        message_type = 'audio'
                    else:
                        return response.text('success')
                sender_id = str(msg.chat.id)
                metadata = self.get_metadata(request)
                out_channel.users[sender_id].put(message_type)

                try:
                    if text == (INTENT_MESSAGE_PREFIX + USER_INTENT_RESTART):
                        await on_new_message(
                            UserMessage(
                                text,
                                out_channel,
                                sender_id,
                                input_channel=self.name(),
                                metadata=metadata,
                            )
                        )
                        await on_new_message(
                            UserMessage(
                                '/start',
                                out_channel,
                                sender_id,
                                input_channel=self.name(),
                                metadata=metadata,
                            )
                        )
                    else:
                        await on_new_message(
                            UserMessage(
                                text,
                                out_channel,
                                sender_id,
                                input_channel=self.name(),
                                metadata=metadata,
                            )
                        )
                except Exception as e:
                    logger.error(f'Exception when trying to handle message.{e}')
                    logger.debug(e, exc_info=True)
                    if self.debug_mode:
                        raise

                return response.text('success')

        return telegram_webhook

    def get_output_channel(self) -> TelegramOutput:
        """Loads the telegram channel."""
        channel = TelegramOutput(self.access_token)
        channel.set_webhook(url=self.webhook_url)

        return channel


class UserHistory:
    def __init__(self):
        self.pending = queue.Queue()
        self.last = 'text'

    def get(self):
        if self.pending.empty():
            return self.last
        self.last = self.pending.get()
        return self.last

    def put(self, message_type):
        self.pending.put(message_type)

    def __repr__(self):
        return 'pending: {}, last: {}'.format(self.pending.queue, self.last)