import os, time, requests
import smtplib
from email.mime.text import MIMEText
from typing import Dict

class NotificationManager:
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.alert_email = os.getenv("ALERT_EMAIL")
        
        # Rate limiting: { "alert_type:cid": last_timestamp }
        self.last_sent: Dict[str, float] = {}
        self.cooldown = 60 # seconds

    def _should_notify(self, key: str) -> bool:
        now = time.time()
        if key in self.last_sent and (now - self.last_sent[key] < self.cooldown):
            return False
        self.last_sent[key] = now
        return True

    def send_telegram(self, message: str):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"[!] Telegram Error: {e}")

    def send_email(self, subject: str, message: str):
        if not self.smtp_user or not self.alert_email:
            return
        
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = self.smtp_user
        msg['To'] = self.alert_email
        
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
        except Exception as e:
            print(f"[!] Email Error: {e}")

    def notify(self, alert_type: str, camera_id: str, details: str):
        key = f"{alert_type}:{camera_id}"
        if not self._should_notify(key):
            return

        msg = f"🔔 *SECUREVU ALERT*\n\n*Type:* {alert_type.upper()}\n*Camera:* {camera_id}\n*Details:* {details}\n*Time:* {time.ctime()}"
        
        # Dispatch to all active channels
        self.send_telegram(msg)
        self.send_email(f"SecureVu Alert: {alert_type}", msg)

# Singleton instance
notifier = NotificationManager()
