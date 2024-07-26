import os
import smtplib
import sys
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread
from typing import Optional

import cv2
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.log import logger

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    template_dir = os.path.join(
        sys._MEIPASS,
        "arknights_mower",
        "__init__",
        "templates",
        "email",
    )
else:
    template_dir = os.path.join(
        os.getcwd(),
        "arknights_mower",
        "templates",
        "email",
    )

env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape())

task_template = env.get_template("task.html")
maa_template = env.get_template("maa.html")
recruit_template = env.get_template("recruit_template.html")
recruit_rarity = env.get_template("recruit_rarity.html")
report_template = env.get_template("report_template.html")


class Email:
    def __init__(self, body, subject, attach_image):
        conf = config.conf
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "html"))
        msg["Subject"] = subject
        msg["From"] = conf.account
        msg["To"] = ", ".join(conf.recipient)

        if attach_image is not None:
            img = cv2.cvtColor(attach_image, cv2.COLOR_RGB2BGR)
            _, attachment = cv2.imencode(
                ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            )
            image_content = MIMEImage(attachment.tobytes())
            image_content.add_header(
                "Content-Disposition", "attachment", filename="image.jpg"
            )
            msg.attach(image_content)
        self.msg = msg

        if conf.custom_smtp_server.enable:
            self.smtp_server = conf.custom_smtp_server.server
            self.port = conf.custom_smtp_server.ssl_port
            self.encryption = conf.custom_smtp_server.encryption
        else:
            self.smtp_server = "smtp.qq.com"
            self.port = 465
            self.encryption = "tls"

    def send(self):
        if self.encryption == "starttls":
            s = smtplib.SMTP(self.smtp_server, self.port, timeout=10)
            s.starttls()
        else:
            s = smtplib.SMTP_SSL(self.smtp_server, self.port, timeout=10)
        conf = config.conf
        s.login(conf.account, conf.pass_code)
        recipient = conf.recipient or [conf.account]
        s.send_message(self.msg, conf.account, recipient)
        s.quit()


def send_message_sync(body="", subject="", attach_image=None):
    conf = config.conf
    if subject == "":
        subject = body.split("\n")[0].strip()
    subject = conf.mail_subject + subject

    if conf.mail_enable:
        email = Email(body, subject, attach_image)
        try:
            email.send()
        except Exception as e:
            logger.exception(e)
            logger.error("邮件发送失败：" + str(e))

    if conf.pushplus.enable:
        url = "http://www.pushplus.plus/send"

        try:
            response = requests.post(
                url,
                json={
                    "token": conf.pushplus.token,
                    "title": subject,
                    "content": body,
                    "template": "html",
                },
            ).json()
            if response["code"] != 200:
                logger.error(f"PushPlus通知发送失败：{response['msg']}")
        except Exception as e:
            logger.error("PushPlus通知发送失败：" + str(e))


def send_message(body="", subject="", attach_image: Optional[tp.Image] = None):
    """异步发送邮件

    Args:
        body: 邮件内容
        subject: 邮件标题
        attach_image: 图片附件
    """
    Thread(target=send_message_sync, args=(body, subject, attach_image)).start()
