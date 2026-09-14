# SMTP 이메일 알림. 외부 설정이 없으면 같은 응답 형태로 시뮬레이션.

import os
import smtplib
import time
from email.message import EmailMessage


MAX_ATTEMPTS = 3


def send_email(message: str) -> dict:
    host, recipient = os.getenv("SMTP_HOST"), os.getenv("ALERT_EMAIL_TO")
    if not host or not recipient:
        return {"channel": "email", "status": "simulated", "attempts": 0, "detail": "SMTP_HOST 또는 ALERT_EMAIL_TO 미설정"}
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM", recipient)
    username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            email = EmailMessage(); email["Subject"] = "[Mobius] 위험 경보"; email["From"] = sender; email["To"] = recipient; email.set_content(message)
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(email)
            return {"channel": "email", "status": "sent", "attempts": attempt, "detail": ""}
        except Exception as error:
            if attempt == MAX_ATTEMPTS:
                return {"channel": "email", "status": "failed", "attempts": attempt, "detail": str(error)}
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError("unreachable")


def dispatch(message: str) -> dict:
    delivery = send_email(message)
    return {"status": delivery["status"], "deliveries": [delivery]}
