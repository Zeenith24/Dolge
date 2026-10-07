"""
Outgoing email. Providers, in order of preference:
  1. Resend HTTP API   (RESEND_API_KEY)  - recommended: works on hosts that block SMTP ports
  2. Any SMTP server   (SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD)
With neither configured, messages are only printed to the server log (handy for local testing).
"""
import html as htmllib
import json
import smtplib
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage

from . import settings as S


def _send_resend(to: str, subject: str, html: str, text: str):
    body = json.dumps({"from": S.MAIL_FROM, "to": [to], "subject": subject, "html": html, "text": text}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=body, method="POST", headers={
        "Authorization": f"Bearer {S.RESEND_API_KEY}", "Content-Type": "application/json",
        "User-Agent": "dolge-reel-studio/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def _send_smtp(to: str, subject: str, html: str, text: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = S.MAIL_FROM, to, subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(S.SMTP_HOST, S.SMTP_PORT, timeout=15) as smtp:
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        if S.SMTP_USER:
            smtp.login(S.SMTP_USER, S.SMTP_PASSWORD)
        smtp.send_message(msg)


def _deliver(to: str, subject: str, html: str, text: str):
    try:
        if S.RESEND_API_KEY:
            _send_resend(to, subject, html, text)
        elif S.SMTP_HOST:
            _send_smtp(to, subject, html, text)
        else:
            print(f"\n[mail not configured] To: {to}\nSubject: {subject}\n{text}\n")
    except urllib.error.HTTPError as exc:
        print(f"[mail] send to {to} failed: HTTP {exc.code} {exc.read()[:200]!r}")
    except Exception as exc:  # never let email problems break a request
        print(f"[mail] send to {to} failed: {exc!r}")


def send_async(to: str, subject: str, html: str, text: str):
    threading.Thread(target=_deliver, args=(to, subject, html, text), daemon=True).start()


def _layout(title: str, body_html: str, button_label: str, url: str) -> str:
    return f"""<div style="font-family:Courier New,monospace;background:#fff8f5;padding:24px">
  <div style="max-width:480px;margin:auto;background:#fffdf0;border:2px solid #1e1b19;border-radius:8px;padding:24px">
    <h2 style="margin:0 0 12px;color:#1e1b19">{title}</h2>
    <div style="color:#1e1b19;font-size:14px;line-height:1.5">{body_html}</div>
    <p style="margin:24px 0"><a href="{url}" style="background:#ae3115;color:#fff;padding:12px 20px;border:2px solid #1e1b19;border-radius:6px;text-decoration:none;font-weight:bold">{button_label}</a></p>
    <p style="font-size:12px;color:#59413c">Or paste this link into your browser:<br>{url}</p>
  </div></div>"""


def send_verification(to: str, name: str, url: str):
    safe = htmllib.escape(name)
    text = f"Hi {name},\n\nConfirm your email to start making reels:\n{url}\n\nThis link expires in {S.VERIFY_TTL_HOURS} hours. If you didn't sign up, ignore this email."
    html = _layout("Confirm your email", f"<p>Hi {safe},</p><p>Confirm your email address to start making reels. The link works for {S.VERIFY_TTL_HOURS} hours.</p>", "Confirm email", url)
    send_async(to, "Confirm your email for Dolge", html, text)


def send_password_reset(to: str, name: str, url: str):
    safe = htmllib.escape(name)
    text = f"Hi {name},\n\nReset your password here:\n{url}\n\nThis link expires in {S.RESET_TTL_MINUTES} minutes. If you didn't ask for this, ignore this email; your password stays the same."
    html = _layout("Reset your password", f"<p>Hi {safe},</p><p>Someone asked to reset your password. The link works for {S.RESET_TTL_MINUTES} minutes. If that wasn't you, ignore this email.</p>", "Choose a new password", url)
    send_async(to, "Reset your Dolge password", html, text)
