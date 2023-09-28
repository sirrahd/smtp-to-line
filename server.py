#!/usr/bin/env python3

import asyncio
import base64
import cv2
import datetime
import email
import imutils
import itertools
import json
import logging
import os
import ssl
import tempfile
import time
import traceback

from aiosmtpd.controller import Controller as SMTPController
from aiosmtpd.handlers import Message as MessageHandler
from aiosmtpd.smtp import AuthResult, LoginPassword, SMTP

from distutils import util

from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage, ImageMessage

logging.basicConfig(encoding='utf-8', level=logging.ERROR)

class config:
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('SL_LINE_CHANNEL_ACCESS_TOKEN', None)
    LINE_USER_ID = os.environ.get('SL_LINE_USER_ID', None)
    MESSAGE_TEMPLATE = os.environ.get('SL_MESSAGE_TEMPLATE', '{subject}\nFrom: {sender}\n\n{text}')
    WEB_ROOT = os.environ.get('SL_WEB_ROOT', None)
    TRAEFIK_CERT_PATH = os.environ.get('SL_TRAEFIK_CERT_PATH', None)
    SSL_CERT_FILE = os.environ.get('SL_SSL_CERT_FILE', None)
    SSL_KEY_FILE = os.environ.get('SL_SSL_KEY_FILE', None)
    AUTH = os.environ.get('SL_AUTH', None)
    FAILURE_DELAY = int(os.environ.get('SL_FAILURE_DELAY', 10))
    DEBUG = util.strtobool(os.environ.get('SL_DEBUG', 'False'))

class Message:
    LINE_MSG_LIMIT = 5000

    def __init__(self, message):
        self.text = ''
        self.sender = decode_header(message.get('From', 'Unknown'))
        self.recipient = decode_header(message.get('To', 'Unknown'))
        self.subject = decode_header(message.get('Subject', ''))
        self.images = []
        self.attachments = []
        self.payload = []

        if not os.path.exists('data'):
            os.makedirs('data')
        self.file_path = tempfile.mkdtemp(prefix='', dir='data')
        os.chmod(self.file_path, 0o755)
        self.label = os.path.basename(self.file_path)
        if config.WEB_ROOT:
            self.web_path = os.path.join(config.WEB_ROOT, self.label)
            
        pprint('Received {} from {}'.format(self.label, self.sender))

        self.add_components(message)

    def add_components(self, message):
        full_message = os.path.join(self.file_path, 'full_message.txt')
        with open(full_message, 'w') as f:
            f.write(message.as_string())

        for part in message.walk():
            if part.get_content_type() == 'text/plain' and part.get_filename() == None:
                self.add_text(part)
            elif not config.WEB_ROOT:
                pass # Ignore remaining options if web URL not set
            elif part.get_content_type() == 'text/html' and part.get_filename() == None:
                self.add_html(part)
            elif part.get_content_type() in ['image/jpeg', 'image/png']:
                self.add_photo(part)
            elif part.get_filename() != None:
                self.add_attachment(part)
            else:
                pass

        self.formatted_message = config.MESSAGE_TEMPLATE.format(
            sender=self.sender,
            recipient=self.recipient,
            subject=self.subject,
            text=self.text
        ).strip()

        if len(self.formatted_message) > self.LINE_MSG_LIMIT and config.WEB_ROOT:
            self.attachments.append(os.path.join(self.web_path, 'full_message.txt'))
        self.formatted_message = self.formatted_message[:self.LINE_MSG_LIMIT].strip()

        self.payload.append(TextMessage(text=self.formatted_message))

        if self.attachments:
            attachment_msg = self.format_attachments()
            full_msg = self.formatted_message + '\n\n' + attachment_msg
            if len(full_msg) > self.LINE_MSG_LIMIT:
                self.payload.append(TextMessage(text=attachment_msg))
            else:
                self.payload[0] = TextMessage(text=full_msg)

        if self.images:
            self.payload.extend(self.images)

    def add_text(self, part):
        self.text += part.get_payload(decode=True).decode('utf-8').strip()

    def add_html(self, part):
        self.add_attachment(part, self.generate_filename(part, 'message.html'))

    def add_photo(self, part):
        filename = self.write_part(part)
        filepath = os.path.join(self.file_path, filename)
        fileurl = os.path.join(self.web_path, filename)
        image_size = os.stat(filepath).st_size
        if image_size > 10000000 or len(self.images) >= 3:
            self.attachments.append(fileurl)
        else:
            MAX_THUMB = 500
            image = cv2.imread(filepath)
            height, width = image.shape[:2]
            if height > MAX_THUMB or width > MAX_THUMB:
                preview_name = os.path.splitext(filename)[0] + 'p' + os.path.splitext(filename)[1]
                preview_path = os.path.join(self.file_path, preview_name)
                preview_url = os.path.join(self.web_path, preview_name)
                if height > width:
                    cv2.imwrite(preview_path, imutils.resize(image, height=MAX_THUMB))
                else:
                    cv2.imwrite(preview_path, imutils.resize(image, width=MAX_THUMB))
                self.images.append(ImageMessage(originalContentUrl=fileurl, previewImageUrl=preview_url))
            else:
                self.images.append(ImageMessage(originalContentUrl=fileurl, previewImageUrl=fileurl))
                    
    def add_attachment(self, part, filename_fallback=None):
        filename = self.write_part(part, filename_fallback)
        self.attachments.append(os.path.join(self.web_path, filename))

    def write_part(self, part, filename_fallback=None):
        filename = self.generate_filename(part, filename_fallback)
        path = os.path.join(self.file_path, filename)
        with open(path, 'wb') as f:
            f.write(part.get_payload(decode=True))

        return filename

    def generate_filename(self, part, fallback=None):
        return part.get_filename(fallback if fallback else '{}.{}'.format(len(self.images + self.attachments), part.get_content_subtype()))
    
    def format_attachments(self):
        text = 'Attachments:\n'
        for attachment in self.attachments:
            text += '📎 {}\n'.format(attachment)
        return(text.strip())

    def send(self):
        line_bot_api = MessagingApi(ApiClient(Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)))
        try:
            line_bot_api.push_message(
                PushMessageRequest(
                    to=config.LINE_USER_ID,
                    messages=self.payload
                )
            )
        except Exception as e:
            raise e

class Handler(MessageHandler):
    async def handle_exception(self, e):
        if config.DEBUG:
            pprint('An error occurred: {} {}'.format(type(e).__name__, e))
            print(traceback.format_exc())
        time.sleep(config.FAILURE_DELAY)
        return '451 The command has been aborted due to a server error'

    def handle_message(self, message):
        m = Message(message)
        m.send()

class Controller(SMTPController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def factory(self):
        return SMTP(
            self.handler,
            hostname=self.hostname,
            tls_context=self.create_context(),
            enable_SMTPUTF8=True,
            authenticator=Authenticator(),
            auth_required=bool(config.AUTH)
        )
    
    def create_context(self):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        if config.TRAEFIK_CERT_PATH:
            with open(config.TRAEFIK_CERT_PATH) as f:
                resolvers_data = json.loads(f.read())
            
            certificate = resolvers_data['letsencrypt']['Certificates'][0]['certificate']
            key = resolvers_data['letsencrypt']['Certificates'][0]['key']

            with open('cert.pem', 'wb') as f:
                f.write(base64.b64decode(certificate))

            with open('key.pem', 'wb') as f:
                f.write(base64.b64decode(key))

            context.load_cert_chain('cert.pem', 'key.pem')
        
        elif config.SSL_CERT_FILE:
            if config.SSL_KEY_FILE:
                context.load_cert_chain(config.SSL_CERT_FILE, config.SSL_KEY_FILE)
            else:
                context.load_cert_chain(config.SSL_CERT_FILE)

        else:
            return None

        return context

class Authenticator:
    def __init__(self):
        self.fake_auth = not config.AUTH
        self.fail_nothandled = AuthResult(success=False, handled=False)
        self.success = AuthResult(success=True)

    def __call__(self, server, session, envelope, mechanism, auth_data):
        if self.fake_auth:
            return self.success
        
        if mechanism not in ("LOGIN", "PLAIN"):
            return self.fail_nothandled
        if not isinstance(auth_data, LoginPassword):
            return self.fail_nothandled
        username = auth_data.login.decode('utf-8')
        password = auth_data.password.decode('utf-8')
        
        result = self.validate(username, password)
        if result == self.success:
            pprint('Login from {}@{}'.format(username, session.host_name))
        else:
            pprint('Failed login from {}'.format(session.host_name))
            time.sleep(config.FAILURE_DELAY)

        return result
    
    def validate(self, username, password):
        if (username, password) in self.authpairs():
            return self.success
        else:
            return self.fail_nothandled

    def authpairs(self):
        a, b = itertools.tee(config.AUTH.split())
        next(b, None)
        return zip(a, b)

def pprint(message):
    print('[{}] {}'.format(datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S'), message))

def decode_header(text):
    text = email.header.decode_header(text)

    output = []
    for word in text:
        word = word[0]
        if type(word) == bytes:
            word = word.decode('utf-8')
        output.append(word)

    return ''.join(output)

async def amain():
    controller = Controller(
        Handler(), 
        hostname='0.0.0.0'
    )
    controller.start()
    pprint('Listening on {}:{}'.format(controller.hostname, controller.port))

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(amain())
    try:
        loop.run_forever()
    except:
        pprint('Shutting down')