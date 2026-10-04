import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

BASE = "https://fapi.binance.com"
st.set_page_config(page_title="Crypto Momentum Scanner", page_icon="🚀", layout="wide")
st.title("🚀 Crypto Momentum Scanner")
st.caption("Binance USDT-M Perpetual Futures • 15M • LONG + SHORT")

@st.cache_data(ttl=300)
def get_symbols():
    r = requests.get(f"{BASE}/fapi/v1/exchangeInfo", timeout=15)
    r.raise_for_status()
    return [s["symbol"] for s in r.json()["symbols"]
            if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
            and s["contractType"] == "PERPETUAL"]

@st.cache_data(ttl=60)
def get_24h():
    r = requests.get(f"{BASE}/fapi/v1/ticker/24hr", timeout=15)
    r.raise_for_status()
    return {x["symbol"]: x for x in r.json()}

@st.cache_data(ttl=45)
def candles(symbol, interval, limit=120):
    r = requests.get(f"{BASE}/fapi/v1/klines",
                     params={"symbol": symbol, "interval": interval, "limit": limit},
                     timeout=12)
    r.raise_for_status()
    cols=["open_time","open","high","low","close","volume","close_time",
          "quote_volume","trades","taker_base","taker_quote","ignore"]
    df=pd.DataFrame(r.json(), columns=cols)
    for c in ["open","high","low","close","volume","quote_volume"]:
        df[c]=pd.to_numeric(df[c], errors="coerce")
    return df

def ema(s,n=21):
    return s.ewm(span=n, adjust=False).mean()

def atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyse(symbol):
    try:
        d4,d1,d15=candles(symbol,"4h"),candles(symbol,"1h"),candles(symbol,"15m")
        x,p=d15.iloc[-2],d15.iloc[-3]
        e4,e1,e15=ema(d4.close),ema(d1.close),ema(d15.close)
        a15=atr(d15)

        b4=d4.close.iloc[-2]>e4.iloc[-2] and e4.iloc[-2]>e4.iloc[-3]
        s4=d4.close.iloc[-2]<e4.iloc[-2] and e4.iloc[-2]<e4.iloc[-3]
        b1=d1.close.iloc[-2]>e1.iloc[-2] and e1.iloc[-2]>e1.iloc[-3]
        s1=d1.close.iloc[-2]<e1.iloc[-2] and e1.iloc[-2]<e1.iloc[-3]

        base=d15.volume.iloc[-22:-2].mean()
        vr=float(x.volume/base) if base>0 else 0
        vol=vr>=1.5
        ph=d15.high.iloc[-22:-2].max()
        pl=d15.low.iloc[-22:-2].min()
        breakout=x.close>ph
        breakdown=x.close<pl

        swing_low=d15.low.iloc[-7:-2].min()
        swing_high=d15.high.iloc[-7:-2].max()
        long_sweep=x.low<swing_low and x.close>swing_low
        short_sweep=x.high>swing_high and x.close<swing_high

        ls=(15 if b4 else 0)+(15 if b1 else 0)+(20 if breakout else 0)
        ls+=(10 if x.close>e15.iloc[-2] else 0)+(15 if vol else (7 if vr>=1.2 else 0))
        ls+=(15 if long_sweep else 0)+(10 if x.close>p.close else 0)

        ss=(15 if s4 else 0)+(15 if s1 else 0)+(20 if breakdown else 0)
        ss+=(10 if x.close<e15.iloc[-2] else 0)+(15 if vol else (7 if vr>=1.2 else 0))
        ss+=(15 if short_sweep else 0)+(10 if x.close<p.close else 0)

        direction="🟢 LONG" if ls>=ss else "🔴 SHORT"
        score=max(ls,ss)
        trigger=("Breakout" if breakout else "Liquidity Sweep" if long_sweep else "Momentum") if ls>=ss else \
                ("Breakdown" if breakdown else "Liquidity Sweep" if short_sweep else "Momentum")

        sig=[]
        if breakout:sig.append("🚀 Breakout")
        if breakdown:sig.append("📉 Breakdown")
        if vol:sig.append("🔥 Volume Spike")
        if long_sweep:sig.append("💧 Long Sweep")
        if short_sweep:sig.append("💧 Short Sweep")
        return {"Coin":symbol,"Direction":direction,"Score":int(score),
                "4H":"Bull" if b4 else ("Bear" if s4 else "Neutral"),
                "1H":"Bull" if b1 else ("Bear" if s1 else "Neutral"),
                "15M Setup":trigger,"Volume":f"{vr:.1f}x",
                "Signals":" ".join(sig) if sig else "—"}
    except Exception:
        return None

with st.sidebar:
    st.header("⚙️ Scanner")
    min_score=st.slider("Minimum score",40,100,60)
    max_coins=st.slider("Coins to scan",20,200,80)
    refresh=st.selectbox("Auto refresh (minutes)",[5,10,15,30],index=2)
    st.divider()
    st.write("🔥 Volume Spike = 15M volume ≥ 1.5× recent average")
    st.write("🚀 Breakout = 15M close above prior 20-candle high")
    st.write("📉 Breakdown = 15M close below prior 20-candle low")
    st.write("💧 Sweep = wick takes prior swing and closes back inside")

if st_autorefresh:
    st_autorefresh(interval=refresh*60*1000,key="refresh")
else:
    st.warning("Install streamlit-autorefresh for automatic refresh.")

symbols=get_symbols()
tick=get_24h()
ranked=sorted([s for s in symbols if s in tick],
              key=lambda s:float(tick[s].get("quoteVolume",0)),reverse=True)[:max_coins]

progress=st.progress(0)
rows=[]
for i,s in enumerate(ranked):
    x=analyse(s)
    if x and x["Score"]>=min_score:
        x["24h %"]=f'{float(tick[s].get("priceChangePercent",0)):.2f}%'
        x["24h Vol"]=f'${float(tick[s].get("quoteVolume",0))/1e6:.1f}M'
        rows.append(x)
    progress.progress((i+1)/len(ranked))
progress.empty()

st.caption(f"Last scan: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} • Scanned {len(ranked)} liquid USDT perpetuals")

df=pd.DataFrame(rows)
if df.empty:
    st.warning("No setup above selected score. Lower the score or wait for next scan.")
else:
    df=df.sort_values(["Score","24h Vol"],ascending=[False,False])
    longs=df[df.Direction=="🟢 LONG"]
    shorts=df[df.Direction=="🔴 SHORT"]
    a,b,c,d=st.columns(4)
    a.metric("Setups",len(df)); b.metric("🟢 LONG",len(longs))
    c.metric("🔴 SHORT",len(shorts)); d.metric("🔥 Volume Spike",int(df.Signals.str.contains("Volume Spike").sum()))
    cols=["Coin","Direction","Score","4H","1H","15M Setup","Volume","Signals","24h %","24h Vol"]
    st.subheader("🏆 Top Momentum Setups")
    st.dataframe(df[cols].head(25),use_container_width=True,hide_index=True)
    c1,c2=st.columns(2)
    with c1:
        st.subheader("🟢 Top LONG")
        st.dataframe(longs[cols].head(10),use_container_width=True,hide_index=True)
    with c2:
        st.subheader("🔴 Top SHORT")
        st.dataframe(shorts[cols].head(10),use_container_width=True,hide_index=True)

st.info("⚠️ Rule-based momentum scanner; not a guaranteed prediction or trading recommendation.")
