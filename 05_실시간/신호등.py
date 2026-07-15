# 고노고 신호등 — 프레임워크 v0.2의 판독 규칙을 yfinance 실시간 데이터에 적용
# 실행: venv/Scripts/python.exe "고노고 글쓰기/05_실시간/신호등.py"
import os
import ssl
import sys
import tempfile

import certifi


def _corp_ca_bundle():
    """certifi 번들 + Windows 인증서 저장소(Zscaler 루트 포함) 합본을 %TEMP%에 생성.

    yfinance(curl_cffi)는 truststore.inject_into_ssl()이 안 먹혀서 CA 번들 자체를 교체해야 함.
    """
    path = os.path.join(tempfile.gettempdir(), "corp_ca_bundle.pem")
    with open(certifi.where(), "rb") as f:
        pem = f.read()
    extra = []
    for store in ("ROOT", "CA"):
        for cert, enc, _ in ssl.enum_certificates(store):
            if enc == "x509_asn":
                extra.append(ssl.DER_cert_to_PEM_cert(cert).encode())
    with open(path, "wb") as f:
        f.write(pem + b"\n" + b"".join(extra))
    return path


_BUNDLE = _corp_ca_bundle()
os.environ["CURL_CA_BUNDLE"] = _BUNDLE
os.environ["SSL_CERT_FILE"] = _BUNDLE
os.environ["REQUESTS_CA_BUNDLE"] = _BUNDLE
certifi.where = lambda: _BUNDLE  # curl_cffi가 import 시점에 certifi.where()를 읽는 경우 대비

import io  # noqa: E402
import json  # noqa: E402

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402  — CA 설정 이후에 import해야 함
from curl_cffi import requests as curl_requests  # noqa: E402  — urllib은 FRED에서 타임아웃

sys.stdout.reconfigure(encoding="utf-8")

TICKERS = {
    # L0 구조론
    "GC=F": "금",
    "DX-Y.NYB": "달러인덱스",
    "^TNX": "미10Y금리(x10)",
    "^TYX": "미30Y금리(x10)",
    "BTC-USD": "비트코인",
    "ETH-USD": "이더리움",
    # L1 거시
    "CL=F": "WTI",
    "^VIX": "VIX",
    "JPY=X": "USD/JPY",
    "KRW=X": "USD/KRW",
    "^GSPC": "S&P500",
    # L2/L3 미시
    "MU": "마이크론",
    "NVDA": "엔비디아",
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "IBM": "IBM",
    "MELI": "메르카도리브레",
}


def fetch(symbol):
    hist = yf.Ticker(symbol).history(period="7d")
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    last, prev = closes.iloc[-1], closes.iloc[-2]
    return last, (last / prev - 1) * 100


def judge(symbol, price):
    """프레임워크 v0.2 판독 규칙 → (신호, 코멘트)"""
    if symbol == "CL=F":
        if price < 60:
            return "🟡", "너무 낮음 — 오일머니→AI 위축 채널 감시"
        if price <= 74:
            return "🟢", "골디락스 존(60~74) — 상방 압력 소멸 구간"
        if price <= 80:
            return "🟡", "74 재돌파 — 인플레 서사 부활 감시"
        return "🔴", "80 안착 — 인플레 부활, 판독 뒤집힘 트리거①"
    if symbol == "^VIX":
        if price < 15:
            return "🟡", "안일(complacency) — 충격 시 낙폭 증폭 장치"
        if price <= 20:
            return "🟢", "중립"
        return "🔴", "공포 구간 — 청산 신호 관찰(패턴③ 청산=기회)"
    if symbol == "JPY=X":
        if price < 159.5:
            return "🔴", "엔 강세 반전 — 캐리 언와인드·연좌제 트리거②"
        if price <= 162.5:
            return "🟢", "MUFG 밴드(159.5~162.5) 내 — 캐리 우호"
        return "🟡", "엔 폭락 과속 — 인플레 기대 자극 감시"
    return "", ""


def _get(url):
    r = curl_requests.get(url, timeout=30, impersonate="chrome")  # FRED가 비브라우저 요청을 403 처리
    r.raise_for_status()
    return r.content


def fred_series(sid, start="2024-01-01"):
    """FRED fredgraph.csv — API 키 불필요."""
    raw = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}")
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().reset_index(drop=True)


def stablecoin_total():
    """DefiLlama — 스테이블코인 총 시총(단기채 수요 대리지표). 키 불필요."""
    data = json.loads(_get("https://stablecoins.llama.fi/stablecoincharts/all"))
    tot = lambda d: d["totalCirculating"]["peggedUSD"]  # noqa: E731
    return tot(data[-1]), (tot(data[-1]) / tot(data[-31]) - 1) * 100


def judge_mom(name, mom):
    """물가 MoM 판독 — 프레임워크 L1-1."""
    if mom < 0:
        return "🟢", f"{name} 마이너스 — '더 벗을것도 없다', 인상 서사 소멸"
    if mom <= 0.25:
        return "🟢", "디스인플레 경로 유지 (JP모간 이상적 시나리오 0.20~0.25 이내)"
    if mom <= 0.35:
        return "🟡", "물가 반등 조짐 — 다음 지표까지 판단 보류"
    return "🔴", "물가 재가속 — 인상 서사 부활, 판독 뒤집힘 트리거③"


def fred_block():
    print()
    print("[L0/L1 거시 — FRED·DefiLlama]")
    print(f"{'지표':<14}{'값':>12}  신호 코멘트")
    print("-" * 78)
    try:
        cpi = fred_series("CPIAUCSL")
        mom = (cpi["value"].iloc[-1] / cpi["value"].iloc[-2] - 1) * 100
        sig, cmt = judge_mom("CPI", mom)
        print(f"{'CPI MoM':<14}{mom:>+11.2f}%  {sig} {cmt} ({cpi['date'].iloc[-1]}분)")
    except Exception as e:
        print(f"{'CPI MoM':<14}{'조회 실패':>12}  ({type(e).__name__})")
    try:
        ppi = fred_series("PPIFIS")
        mom = (ppi["value"].iloc[-1] / ppi["value"].iloc[-2] - 1) * 100
        sig, cmt = judge_mom("PPI", mom)
        print(f"{'PPI MoM':<14}{mom:>+11.2f}%  {sig} {cmt} ({ppi['date'].iloc[-1]}분)")
    except Exception as e:
        print(f"{'PPI MoM':<14}{'조회 실패':>12}  ({type(e).__name__})")
    try:
        dgs2 = fred_series("DGS2", "2026-01-01")
        two = dgs2["value"].iloc[-1]
        month_ago = dgs2["value"].iloc[-22] if len(dgs2) > 22 else dgs2["value"].iloc[0]
        target = fred_series("DFEDTARU", "2026-01-01")["value"].iloc[-1]
        gap = two - target
        if gap > 0.10:
            sig, cmt = "🔴", f"2년물이 기준금리+{gap:.2f}%p — 시장이 인상 프라이싱 중"
        elif gap < -0.20:
            sig, cmt = "🟢", f"2년물이 기준금리{gap:.2f}%p — 인하 프라이싱"
        else:
            sig, cmt = "🟢", "정책 기대 중립 — 인상 서사 미프라이싱"
        print(f"{'미2Y(이 년)':<13}{two:>11.2f}%  {sig} {cmt} (1M {month_ago - two:+.2f}%p→)")
        print(f"{'기준금리상단':<13}{target:>11.2f}%")
    except Exception as e:
        print(f"{'미2Y/기준금리':<13}{'조회 실패':>12}  ({type(e).__name__})")
    try:
        curve = fred_series("T10Y2Y", "2026-01-01")["value"].iloc[-1]
        print(f"{'2s10s 커브':<13}{curve:>+10.2f}%p  {'🟢' if curve > 0 else '🟡'} {'정상화' if curve > 0 else '역전 — 플래트닝 감시'}")
    except Exception as e:
        print(f"{'2s10s 커브':<13}{'조회 실패':>12}  ({type(e).__name__})")
    try:
        mcap, chg30 = stablecoin_total()
        sig = "🟢" if chg30 > 0 else "🟡"
        print(f"{'스테이블 시총':<13}{mcap / 1e9:>10.0f}B$  {sig} 30일 {chg30:+.1f}% — L0 단기채 쉬프트 {'진행' if chg30 > 0 else '정체'}")
    except Exception as e:
        print(f"{'스테이블 시총':<13}{'조회 실패':>12}  ({type(e).__name__})")


def main():
    print("고노고 신호등 — 프레임워크 v0.2 실시간 판독")
    fred_block()
    print()
    print("[시장 실시간 — yfinance]")
    print(f"{'지표':<12}{'현재가':>14}{'전일比':>9}  신호 코멘트")
    print("-" * 78)
    for symbol, name in TICKERS.items():
        try:
            row = fetch(symbol)
        except Exception as e:
            print(f"{name:<12}{'조회 실패':>14}         ({type(e).__name__})")
            continue
        if row is None:
            print(f"{name:<12}{'데이터 없음':>14}")
            continue
        price, chg = row
        signal, comment = judge(symbol, price)
        print(f"{name:<12}{price:>14,.2f}{chg:>+8.2f}%  {signal} {comment}")


if __name__ == "__main__":
    main()
