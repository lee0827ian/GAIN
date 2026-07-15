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

import yfinance as yf  # noqa: E402  — CA 설정 이후에 import해야 함

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


def main():
    print("고노고 신호등 — 프레임워크 v0.2 실시간 판독")
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
