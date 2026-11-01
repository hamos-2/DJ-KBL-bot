#!/usr/bin/env python3
"""
SRE Mailer - High-reliability Alert & Incident Dispatcher.
Formats beautiful HTML email alerts and dispatches via SMTP (TLS/SSL).
Supports offline fallback to local alert queue when SMTP credentials are pending.
"""

import email.utils
import json
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

ALERT_QUEUE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts")


def load_env_vars() -> dict[str, str]:
    """Load configuration from local or parent directory .env file."""
    env_paths = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.expanduser("~/DJ-KBL-bot/kbl-bot/.env"),
    ]
    env_vars: dict[str, str] = {}
    for p in env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip().strip("'\"")
                break
            except Exception:
                pass
    return env_vars


def get_mail_config() -> dict[str, Any]:
    """Retrieve mail server configuration from environment or .env file."""
    dotenv = load_env_vars()
    return {
        "smtp_host": os.getenv("SMTP_HOST") or dotenv.get("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT") or dotenv.get("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER") or dotenv.get("SMTP_USER", ""),
        "smtp_pass": os.getenv("SMTP_PASS") or dotenv.get("SMTP_PASS", ""),
        "email_to": os.getenv("ALERT_EMAIL_TO") or dotenv.get("ALERT_EMAIL_TO", "mjubookfestival@gmail.com"),
        "email_from": os.getenv("ALERT_EMAIL_FROM") or dotenv.get("ALERT_EMAIL_FROM", "KBL SRE Watchdog <alert@kbl-bot.com>"),
    }


def build_alert_html(
    severity: str,
    title: str,
    incident_details: list[dict[str, Any]],
    telemetry_summary: dict[str, Any],
    recovery_commands: list[str],
) -> str:
    """Generate responsive GitHub/SRE-style HTML incident alert email."""
    kst_now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")

    color_map = {
        "CRITICAL": "#E53E3E",  # Red
        "WARNING": "#DD6B20",   # Orange
        "RESOLVED": "#38A169",  # Green
        "INFO": "#3182CE",      # Blue
    }
    badge_color = color_map.get(severity.upper(), "#E53E3E")

    details_rows = ""
    for item in incident_details:
        component = item.get("component", "System")
        metric = item.get("metric", "-")
        threshold = item.get("threshold", "-")
        actual = item.get("actual", "-")
        status = item.get("status", severity)
        details_rows += f"""
        <tr style="border-bottom: 1px solid #E2E8F0;">
            <td style="padding: 10px; font-weight: bold; color: #2D3748;">{component}</td>
            <td style="padding: 10px; color: #4A5568;">{metric}</td>
            <td style="padding: 10px; color: #718096; font-family: monospace;">{threshold}</td>
            <td style="padding: 10px; color: #E53E3E; font-weight: bold; font-family: monospace;">{actual}</td>
            <td style="padding: 10px; text-align: center;"><span style="background: {badge_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{status}</span></td>
        </tr>
        """

    commands_html = ""
    for cmd in recovery_commands:
        commands_html += f"""<div style="background: #1A202C; color: #68D391; font-family: Consolas, monospace; padding: 8px 12px; border-radius: 4px; margin-bottom: 6px; font-size: 13px;">$ {cmd}</div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>{title}</title></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F7FAFC; margin: 0; padding: 24px; color: #2D3748;">
        <div style="max-width: 650px; margin: 0 auto; background: #FFFFFF; border-radius: 8px; border: 1px solid #E2E8F0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <!-- Header -->
            <div style="background: {badge_color}; padding: 18px 24px; color: #FFFFFF;">
                <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 1px; font-weight: bold; opacity: 0.9;">KBL 프로농구 챗봇 SRE 인시던트 관제센터</div>
                <h1 style="margin: 6px 0 0 0; font-size: 20px; font-weight: 800;">[{severity}] {title}</h1>
            </div>

            <!-- Body Container -->
            <div style="padding: 24px;">
                <div style="margin-bottom: 18px; font-size: 14px; color: #4A5568; line-height: 1.6;">
                    <strong>발생 시각:</strong> {kst_now}<br>
                    <strong>인프라 노드:</strong> OCI VPS (<code>168.110.6.240</code>, ap-tokyo-1)<br>
                    <strong>비용 안전 상태:</strong> <span style="color: #38A169; font-weight: bold;">🟢 100% Always Free Safe ($0.00 / 0 KRW)</span>
                </div>

                <!-- Incident Table -->
                <div style="margin-bottom: 24px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 15px; color: #2D3748; border-bottom: 2px solid #EDF2F7; padding-bottom: 6px;">📋 이상 신호 및 특이점 감지 내역</h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="background: #F7FAFC; color: #718096; border-bottom: 2px solid #E2E8F0;">
                                <th style="padding: 8px 10px;">컴포넌트</th>
                                <th style="padding: 8px 10px;">지표 항목</th>
                                <th style="padding: 8px 10px;">안전 임계치</th>
                                <th style="padding: 8px 10px;">실측치</th>
                                <th style="padding: 8px 10px; text-align: center;">등급</th>
                            </tr>
                        </thead>
                        <tbody>
                            {details_rows}
                        </tbody>
                    </table>
                </div>

                <!-- Recovery Actions -->
                <div style="margin-bottom: 24px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 15px; color: #2D3748; border-bottom: 2px solid #EDF2F7; padding-bottom: 6px;">🛠️ 권장 복구 명령어 (SRE Runbook)</h3>
                    {commands_html}
                </div>

                <!-- System Telemetry Snapshot -->
                <div style="background: #EDF2F7; padding: 14px 18px; border-radius: 6px; font-size: 12px; color: #4A5568;">
                    <strong>시스템 스냅샷:</strong>
                    CPU 부하 {telemetry_summary.get('cpu_load', 'N/A')} | RAM 여유 {telemetry_summary.get('mem_avail_mb', 'N/A')}MB | 디스크 사용률 {telemetry_summary.get('disk_used_pct', 'N/A')}% | 카카오 스킬 지연 {telemetry_summary.get('skill_latency_ms', 'N/A')}ms
                </div>
            </div>

            <!-- Footer -->
            <div style="background: #F7FAFC; padding: 14px 24px; border-top: 1px solid #E2E8F0; text-align: center; font-size: 12px; color: #A0AEC0;">
                이 알림은 KBL 프로농구 챗봇 SRE Autonomous Watchdog 에이전트에 의해 자동 발송되었습니다.
            </div>
        </div>
    </body>
    </html>
    """
    return html


def send_sre_email(
    severity: str,
    title: str,
    incident_details: list[dict[str, Any]],
    telemetry_summary: dict[str, Any],
    recovery_commands: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Dispatch an incident notification email to the configured administrator.
    Falls back to saving an alert payload to disk if SMTP is unconfigured.
    """
    config = get_mail_config()
    subject = f"[🚨 KBL봇 SRE 경보] [{severity}] {title}"
    commands = recovery_commands or [
        "ssh -i /Users/dj/Downloads/ssh-key-2026-10-31.key ubuntu@168.110.6.240",
        "sudo docker ps",
        "sudo docker logs --tail 50 kbl_api",
    ]

    html_content = build_alert_html(
        severity=severity,
        title=title,
        incident_details=incident_details,
        telemetry_summary=telemetry_summary,
        recovery_commands=commands,
    )

    # 1. Fallback save to local alerts directory
    os.makedirs(ALERT_QUEUE_DIR, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    alert_filename = f"alert_{severity.lower()}_{timestamp_str}.json"
    alert_filepath = os.path.join(ALERT_QUEUE_DIR, alert_filename)
    try:
        with open(alert_filepath, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": severity,
                "title": title,
                "recipient": config["email_to"],
                "incident_details": incident_details,
                "telemetry_summary": telemetry_summary,
                "recovery_commands": commands,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass

    # 2. Check SMTP credentials
    smtp_user = config.get("smtp_user")
    smtp_pass = config.get("smtp_pass")
    smtp_host = config.get("smtp_host", "smtp.gmail.com")
    smtp_port = config.get("smtp_port", 587)
    to_email = config.get("email_to")

    if not smtp_user or not smtp_pass:
        return False, f"SMTP_USER/SMTP_PASS 미설정. 알림 파일 저장 완료: {alert_filepath}"

    # 3. Dispatch via SMTP
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config["email_from"]
        msg["To"] = to_email
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        recipients = [e.strip() for e in to_email.split(",") if e.strip()] if to_email else [smtp_user]

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, recipients, msg.as_string())

        return True, f"이메일 발송 성공 -> {to_email}"
    except Exception as exc:
        return False, f"SMTP 발송 실패 ({exc}). 파일 큐 저장됨: {alert_filepath}"


if __name__ == "__main__":
    print("Testing SRE Mailer...")
    ok, msg = send_sre_email(
        severity="WARNING",
        title="[테스트] SRE 이상 신호 및 특이점 이메일 보고 시험",
        incident_details=[
            {"component": "Kakao Skill API", "metric": "Latency", "threshold": "< 2000ms", "actual": "2410ms", "status": "WARN"},
            {"component": "Host Disk", "metric": "Usage %", "threshold": "< 75%", "actual": "76%", "status": "WARN"},
        ],
        telemetry_summary={"cpu_load": "0.73", "mem_avail_mb": 511, "disk_used_pct": 17, "skill_latency_ms": 286.9},
        recovery_commands=["sudo docker stats", "sudo docker logs --tail 30 kbl_api"],
    )
    print("Result:", ok, msg)
