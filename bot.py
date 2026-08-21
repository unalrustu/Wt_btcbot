import os
import time
import threading
import requests
import pandas as pd
import telebot
import schedule
from flask import Flask

# Telegram Bot Bilgileriniz
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8853302939:AAFSfbXJyJ9M6wCZ9HB0mJmp3kn_tOd6yRg')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '7497063079')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# --- PARİTE LİSTESİ VE HAFIZA ---
# Takip etmek istediğimiz ürünler (XAUT eklendi)
PARITELER = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "XAUTUSDT"]

# Her paritenin kendi son sinyal mumunu tutmak için sözlük (hafıza)
son_sinyal_mumleri = {}

# --- 1. ÇOKLU MANUEL ANALİZ KOMUTU (/analiz) ---
@bot.message_handler(commands=['analiz'])
def coklu_analiz_gonder(message):
    bot.reply_to(message, "⏳ 5 ürün için veriler çekiliyor ve analiz ediliyor...")
    try:
        toplam_mesaj = "📊 *5'Lİ PİYASA HIZLI ANALİZ* 📊\n\n"
        
        for sembol in PARITELER:
            url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={sembol}"
            cevap = requests.get(url).json()
            
            # Sembol adını daha şık gösterelim (örn: BTCUSDT -> BTC/USDT)
            coin_adi = sembol.replace("USDT", "/USDT")
            
            son_fiyat = float(cevap['lastPrice'])
            en_yuksek = float(cevap['highPrice'])
            en_dusuk = float(cevap['lowPrice'])
            
            pivot = (en_yuksek + en_dusuk + son_fiyat) / 3
            direnc_1 = (pivot * 2) - en_dusuk
            destek_1 = (pivot * 2) - en_yuksek
            stop_loss = destek_1 * 0.98
            
            toplam_mesaj += (
                f"🔹 *{coin_adi}*\n"
                f"💵 Fiyat: {son_fiyat:,.2f} $\n"
                f"🧱 Direnç: {direnc_1:,.2f} $ | 🛡️ Destek: {destek_1:,.2f} $\n"
                f"🛑 Stop-Loss: {stop_loss:,.2f} $\n"
                f"-----------------------------------\n"
            )
            
        bot.reply_to(message, toplam_mesaj, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"⚠️ Veri çekilemedi. Hata: {e}")


# --- 2. KENDİ WAVETREND (WT) MOTORUMUZ (ÇOKLU) ---
def binance_veri_cek(symbol, interval="4h", limit=1000):
    """Binance üzerinden seçilen paritenin mum verilerini çeker"""
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    res = requests.get(url)
    data = res.json()
    
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    return df

def wt_hesapla(df, n1=10, n2=21):
    """WaveTrend formülünün matematiksel hesaplaması"""
    ap = (df['high'] + df['low'] + df['close']) / 3
    esa = ap.ewm(span=n1, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=n1, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    wt1 = ci.ewm(span=n2, adjust=False).mean()
    wt2 = wt1.rolling(window=4).mean()
    return wt1, wt2

def piyasayi_tara():
    """Tüm pariteleri tek tek tarayıp kesişme olup olmadığını kontrol eder"""
    for sembol in PARITELER:
        try:
            df = binance_veri_cek(sembol, "4h", 1000)
            wt1, wt2 = wt_hesapla(df)
            
            onceki_wt1, onceki_wt2 = wt1.iloc[-3], wt2.iloc[-3]
            guncel_wt1, guncel_wt2 = wt1.iloc[-2], wt2.iloc[-2]
            kapanis_fiyati = df['close'].iloc[-2]
            mum_zamani = df['timestamp'].iloc[-2]
            
            coin_adi = sembol.replace("USDT", "/USDT")
            
            # Bu parite için bu mumda zaten sinyal atıldı mı?
            if son_sinyal_mumleri.get(sembol) == mum_zamani:
                continue
            
            # YUKARI KESİŞME (AL SİNYALİ) - Sadece -14'ün altındaysa
            if onceki_wt1 <= onceki_wt2 and guncel_wt1 > guncel_wt2 and guncel_wt1 < -14:
                mesaj = (f"🟢 *WT AL SİNYALİ (4s)* 🟢\n\n"
                         f"🔹 *Parite:* {coin_adi}\n"
                         f"💵 *Kapanış Fiyatı:* {kapanis_fiyati:,.2f} $\n"
                         f"📊 *WT Seviyesi:* {guncel_wt1:.2f}\n"
                         f"🎯 *Kriter:* -14 Altında Kesişim Yakalandı")
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mesaj, parse_mode='Markdown')
                son_sinyal_mumleri[sembol] = mum_zamani
                
            # AŞAĞI KESİŞME (SAT SİNYALİ) - Sadece -14'ün üzerindeyse
            elif onceki_wt1 >= onceki_wt2 and guncel_wt1 < guncel_wt2 and guncel_wt1 > -14:
                mesaj = (f"🔴 *WT SAT SİNYALİ (4s)* 🔴\n\n"
                         f"🔹 *Parite:* {coin_adi}\n"
                         f"💵 *Kapanış Fiyatı:* {kapanis_fiyati:,.2f} $\n"
                         f"📊 *WT Seviyesi:* {guncel_wt1:.2f}\n"
                         f"🎯 *Kriter:* -14 Üzerinde Kesişim Yakalandı")
                bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mesaj, parse_mode='Markdown')
                son_sinyal_mumleri[sembol] = mum_zamani
                
        except Exception as e:
            print(f"{sembol} taranırken hata oluştu: {e}")

# Arka planda zamanlayıcıyı çalıştıran döngü
def zamanlayici_baslat():
    schedule.every(15).minutes.do(piyasayi_tara)
    while True:
        schedule.run_pending()
        time.sleep(1)

# Telegram komutlarını dinleyen döngü
def telegram_dinle():
    bot.infinity_polling()

# Render'ın zorunlu kıldığı Web Sunucusu (Dummy Server)
@app.route('/')
def ana_sayfa():
    return "5'li Parite Botu Aktif ve Çalışıyor!"


if __name__ == '__main__':
    threading.Thread(target=telegram_dinle, daemon=True).start()
    threading.Thread(target=zamanlayici_baslat, daemon=True).start()
    
    print("5'li Parite Analiz Motoru Başlatıldı!")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, host='0.0.0.0')
