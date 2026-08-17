#!/usr/bin/env python3
"""Update QQQ/TQQQ signals, dashboard data, and optional email notification."""

from __future__ import annotations

import csv
import json
import math
import os
import smtplib
import ssl
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = DATA / "state.json"


@dataclass(frozen=True)
class Signal:
    date: str
    action: str
    qqq_close: float
    reference_high: float
    drawdown_percent: float

    @property
    def signal_id(self) -> str:
        return f"{self.date}:{self.action}"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fetch_yahoo(symbol: str, start: str) -> dict[str, float]:
    start_ts = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp()) + 86400
    params = urllib.parse.urlencode({
        "period1": start_ts,
        "period2": end_ts,
        "interval": "1d",
        "events": "div,splits",
        "includeAdjustedClose": "true",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 qqq-alert/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    adjusted = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
    closes = adjusted or result["indicators"]["quote"][0]["close"]
    prices = {}
    for timestamp, close in zip(timestamps, closes):
        if close is not None:
            date = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
            prices[date] = float(close)
    if len(prices) < 100:
        raise RuntimeError(f"Yahoo returned too little history for {symbol}: {len(prices)} rows")
    return prices


def replay(qqq: dict[str, float], tqqq: dict[str, float], drawdown: float, cost: float):
    dates = sorted(set(qqq) & set(tqqq))
    if len(dates) < 2:
        raise RuntimeError("No overlapping QQQ/TQQQ history")
    holding = "QQQ"
    peak = qqq[dates[0]]
    recovery = None
    wealth = 1.0
    wealth_peak = 1.0
    max_drawdown = 0.0
    daily_returns = []
    signals: list[Signal] = []
    curve = [{"date": dates[0], "value": wealth, "holding": holding}]

    for previous, current in zip(dates, dates[1:]):
        asset = qqq if holding == "QQQ" else tqqq
        daily_return = asset[current] / asset[previous] - 1.0
        wealth *= 1.0 + daily_return
        daily_returns.append(daily_return)
        wealth_peak = max(wealth_peak, wealth)
        max_drawdown = min(max_drawdown, wealth / wealth_peak - 1.0)

        if holding == "QQQ":
            peak = max(peak, qqq[current])
            current_drawdown = qqq[current] / peak - 1.0
            if current_drawdown <= -drawdown + 1e-12:
                recovery = peak
                holding = "TQQQ"
                wealth *= 1.0 - cost
                signals.append(Signal(current, "SWITCH_TO_TQQQ", qqq[current], peak, -current_drawdown * 100))
        else:
            assert recovery is not None
            if qqq[current] >= recovery:
                signals.append(Signal(current, "SWITCH_TO_QQQ", qqq[current], recovery, 0.0))
                holding = "QQQ"
                peak = qqq[current]
                recovery = None
                wealth *= 1.0 - cost

        curve.append({"date": current, "value": wealth, "holding": holding})

    years = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days / 365.2425
    mean = statistics.fmean(daily_returns)
    volatility = statistics.stdev(daily_returns)
    metrics = {
        "start": dates[0],
        "end": dates[-1],
        "observations": len(dates),
        "cagr_percent": (wealth ** (1 / years) - 1) * 100,
        "max_drawdown_percent": max_drawdown * 100,
        "sharpe_no_risk_free": mean / volatility * math.sqrt(252),
        "ending_multiple": wealth,
        "switch_count": len(signals),
    }
    if holding == "TQQQ":
        assert recovery is not None
        latest_peak = recovery
    else:
        latest_peak = peak
    status = {
        "as_of": dates[-1],
        "holding": holding,
        "qqq_close": qqq[dates[-1]],
        "reference_high": latest_peak,
        "current_drawdown_percent": (qqq[dates[-1]] / latest_peak - 1) * 100,
        "trigger_price": peak * (1 - drawdown) if holding == "QQQ" else None,
        "recovery_price": recovery,
    }
    return dates, signals, curve, metrics, status


def write_signals(signals: list[Signal]) -> None:
    path = DATA / "signals.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(signals[0]).keys()) if signals else [
            "date", "action", "qqq_close", "reference_high", "drawdown_percent"
        ])
        writer.writeheader()
        for signal in signals:
            writer.writerow(asdict(signal))


def deliver_email(subject: str, body: str) -> None:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_TO_EMAIL"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing email settings: " + ", ".join(missing))
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("ALERT_FROM_EMAIL", os.environ["SMTP_USERNAME"])
    message["To"] = os.environ["ALERT_TO_EMAIL"]
    message.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    if os.getenv("SMTP_USE_STARTTLS", "false").lower() == "true":
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)


def send_email(signal: Signal, status: dict) -> None:
    to_tqqq = signal.action == "SWITCH_TO_TQQQ"
    subject = "QQQ 回撤提醒：考虑换成 TQQQ" if to_tqqq else "QQQ 恢复前高：考虑换回 QQQ"
    action = "QQQ → TQQQ" if to_tqqq else "TQQQ → QQQ"
    body = f"""QQQ/TQQQ 换仓信号

日期：{signal.date}
建议动作：{action}
QQQ 收盘价：${signal.qqq_close:.2f}
记录前高：${signal.reference_high:.2f}
回撤幅度：{signal.drawdown_percent:.2f}%
当前模型状态：{status['holding']}

该邮件为规则提醒，不构成投资建议，也不会自动下单。
"""
    deliver_email(subject, body)


def send_test_email(status: dict) -> None:
    body = f"""QQQ/TQQQ 邮件提醒测试成功。

数据日期：{status['as_of']}
当前模型状态：{status['holding']}
QQQ 收盘价：${status['qqq_close']:.2f}

这是一封手动测试邮件，不是新的换仓信号。
"""
    deliver_email("QQQ/TQQQ Alert：测试邮件成功", body)


def build_dashboard(payload: dict) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    (DOCS / "index.html").write_text(template.replace("__DASHBOARD_DATA__", data), encoding="utf-8", newline="\n")


def main() -> None:
    config = load_json(CONFIG_PATH, {})
    previous_state = load_json(STATE_PATH, {})
    drawdown = float(config.get("drawdown_percent", 10.0)) / 100
    cost = float(config.get("transaction_cost_percent", 0.1)) / 100
    start = config.get("history_start", "2010-02-11")
    qqq = fetch_yahoo("QQQ", start)
    tqqq = fetch_yahoo("TQQQ", start)
    dates, signals, curve, metrics, status = replay(qqq, tqqq, drawdown, cost)
    latest_signal = signals[-1] if signals else None

    write_signals(signals)
    write_json(DATA / "latest.json", {"status": status, "metrics": metrics})
    years = int(config.get("dashboard_years", 10))
    cutoff_year = int(dates[-1][:4]) - years
    dashboard_curve = [row for row in curve if int(row["date"][:4]) >= cutoff_year]
    payload = {
        "config": config,
        "status": status,
        "metrics": metrics,
        "signals": [asdict(s) for s in signals[-30:]][::-1],
        "curve": dashboard_curve,
    }
    build_dashboard(payload)

    current_signal_id = latest_signal.signal_id if latest_signal else None
    previous_date = previous_state.get("last_processed_date", "")
    is_new = (
        bool(previous_state)
        and latest_signal is not None
        and current_signal_id != previous_state.get("last_signal_id")
        and latest_signal.date >= previous_date
    )
    send_initial = os.getenv("SEND_INITIAL_ALERT", "false").lower() == "true"
    email_enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    if email_enabled and os.getenv("SEND_TEST_EMAIL", "false").lower() == "true":
        send_test_email(status)
    if latest_signal and email_enabled and (is_new or (not previous_state and send_initial)):
        send_email(latest_signal, status)

    write_json(STATE_PATH, {
        "last_processed_date": dates[-1],
        "last_signal_id": current_signal_id,
        "holding": status["holding"],
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    print(json.dumps({"status": status, "metrics": metrics, "new_signal": is_new}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
