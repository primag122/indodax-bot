# main.py
import requests
import time
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from keep_alive import keep_alive
import threading

# === KONFIGURASI TELEGRAM ===
TOKEN = '7848984256:AAGs2Y_4m1PkHt_M7g6EY2saarDxE_VN_5s'
CHAT_ID = '5508814337'

# === RIWAYAT ===
entry_record = {}
highest_price_record = {}
breakout_record = {}
history = {}


# === AMBIL DATA COINGECKO (HANYA SEKALI) ===
def ambil_data_coingecko():
  coingecko_tokens = set()
  for page in range(1, 6):
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=idr&per_page=250&page={page}"
    try:
      res = requests.get(url, timeout=10)
      if res.status_code != 200:
        break
      data = res.json()
      if not data:
        break
      coingecko_tokens.update(coin['symbol'].lower() for coin in data)
    except Exception as e:
      print("Gagal ambil data CoinGecko:", e)
      break
  return coingecko_tokens


coingecko_tokens = ambil_data_coingecko()


# === FUNGSI NOTIFIKASI TELEGRAM ===
def kirim_notif(pesan):
  try:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {'chat_id': CHAT_ID, 'text': pesan.encode("utf-8")}
    requests.post(url, data=data, timeout=10)
  except Exception as e:
    print("❌ Gagal kirim ke Telegram:", e)


# === FUNGSI PEMANTAUAN TOKEN ===
def pantau_token():
  url = "https://indodax.com/api/summaries"
  try:
    res = requests.get(url, timeout=10)
    data = res.json()["tickers"]
  except Exception as e:
    print("Gagal ambil data Indodax:", e)
    return

  current_time = time.strftime('%H:%M:%S')

  for symbol, info in data.items():
    try:
      token_symbol = symbol.split("_")[0].lower()
      if token_symbol not in coingecko_tokens:
        continue

      harga_terakhir = float(info["last"])
      harga_terendah = float(info["low"])
      harga_tertinggi = float(info["high"])
      volume = float(info["vol_idr"])

      # ✅ PATCH: Cek jika info["open"] bukan angka valid
      try:
        harga_buka = float(info["open"])
      except:
        print(f"Gagal proses token {symbol}: {info['open']}")
        continue

      harga_list = [harga_terakhir] * 30
      df = pd.DataFrame(harga_list, columns=['close'])
      df['rsi'] = RSIIndicator(df['close']).rsi()
      df['ema9'] = EMAIndicator(df['close'], window=9).ema_indicator()
      df['ema21'] = EMAIndicator(df['close'], window=21).ema_indicator()

      rsi = df['rsi'].iloc[-1]
      ema9 = df['ema9'].iloc[-1]
      ema21 = df['ema21'].iloc[-1]

      if symbol not in history:
        history[symbol] = []
      history[symbol].append({
          "time": current_time,
          "price": harga_terakhir,
          "volume": volume
      })
      if len(history[symbol]) > 30:
        history[symbol].pop(0)

      if len(history[symbol]) >= 2:
        harga_awal = history[symbol][0]["price"]
        persen_kenaikan = (harga_terakhir - harga_awal) / harga_awal * 100
        if 8 <= persen_kenaikan <= 15:
          kirim_notif(f"""
🚀 *Prediksi Naik*: {symbol.upper()}
Harga: Rp{harga_terakhir:,.0f}
Naik: {persen_kenaikan:.2f}% dari 30 menit lalu
RSI: {rsi:.2f}
⏰ {current_time}
""")

      if len(history[symbol]) >= 10:
        vol5 = pd.Series([h['volume'] for h in history[symbol][-5:]]).mean()
        vol_before = pd.Series([h['volume']
                                for h in history[symbol][:-5]]).mean()
        if vol5 > 1.5 * vol_before:
          kirim_notif(f"""
💥 *Volume Spike!* {symbol.upper()}
Volume melonjak dalam 5 menit terakhir!
Harga: Rp{harga_terakhir:,.0f}
RSI: {rsi:.2f}
⏰ {current_time}
""")

      persen_naik = (harga_terakhir - harga_terendah) / harga_terendah * 100
      range_price = harga_tertinggi - harga_terendah
      if (persen_naik >= 5 and volume > 10000000 and rsi < 60
          and harga_terakhir > ema9 > ema21):
        if symbol not in entry_record:
          entry_record[symbol] = harga_terakhir
          highest_price_record[symbol] = harga_terakhir
          breakout_record[symbol] = harga_tertinggi

          kirim_notif(f"""
✅ ENTRY SIGNAL
Token: {symbol.upper()}
Harga: Rp{harga_terakhir:,.0f}
Naik: {persen_naik:.2f}% dari harga terendah hari ini
Volume: Rp{volume:,.0f}
RSI: {rsi:.2f}
EMA9: {ema9:.4f}, EMA21: {ema21:.4f}
⏰ Waktu: {current_time}
""")

      if symbol in entry_record:
        entry_price = entry_record[symbol]
        if symbol not in highest_price_record:
          highest_price_record[symbol] = harga_terakhir
        if harga_terakhir > highest_price_record[symbol]:
          highest_price_record[symbol] = harga_terakhir
        max_price = highest_price_record[symbol]
        trigger_price = max_price * 0.95

        if harga_terakhir <= trigger_price and harga_terakhir > entry_price:
          profit = (harga_terakhir - entry_price) / entry_price * 100
          turun = (max_price - harga_terakhir) / max_price * 100
          kirim_notif(f"""
🚨 TRAILING STOP
Token: {symbol.upper()}
Entry: Rp{entry_price:,.0f}
Puncak: Rp{max_price:,.0f}
Sekarang: Rp{harga_terakhir:,.0f}
Profit: {profit:.2f}%
Turun dari puncak: {turun:.2f}%
⏰ Waktu: {current_time}
""")

      if persen_naik >= 5 and volume > 10000000 and harga_terakhir >= harga_tertinggi * 0.98:
        kirim_notif(f"""
📊 KONFIRMASI 2 TIMEFRAME
Token: {symbol.upper()}
Harga mendekati breakout kuat (HIGH hari ini)
Volume: Rp{volume:,.0f}
⏰ Waktu: {current_time}
""")

      if 0 < range_price / harga_terendah < 0.03:
        kirim_notif(f"""
⚠️ SIDEWAYS DETECTED
Token: {symbol.upper()}
Range pergerakan sempit ({range_price/harga_terendah*100:.2f}%)
⏰ Waktu: {current_time}
""")

      if symbol in entry_record:
        harga_entry = entry_record[symbol]
        if harga_terakhir < harga_entry and harga_buka < harga_terakhir:
          kirim_notif(f"""
📉 BULLISH DIVERGENCE
Token: {symbol.upper()}
Harga lebih rendah dari entry sebelumnya,
Namun menunjukkan candle hijau.
⏰ Waktu: {current_time}
""")

      if symbol in breakout_record:
        res_lama = breakout_record[symbol]
        if res_lama * 0.98 <= harga_terakhir <= res_lama * 1.01:
          kirim_notif(f"""
🔁 RETEST BREAKOUT
Token: {symbol.upper()}
Harga saat ini mendekati resistance lama: Rp{res_lama:,.0f}
Kemungkinan mantul dari area retest!
⏰ Waktu: {current_time}
""")

    except Exception as e:
      continue


# === JALANKAN DENGAN THREAD DI REPLIT ===
def run_bot():
  while True:
    pantau_token()
    time.sleep(60)


keep_alive()
threading.Thread(target=run_bot).start()