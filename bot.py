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

# --- SİNYAL HAFIZASI (Aynı mumda tekrar bildirim atmaması için) ---
son_sinyal_mumu = None

# --- 1. MANUEL ANALİZ KOMUTU (/analiz) ---
@bot.message_handler(commands=['analiz'])
def btc_analiz_gonder(message):
    bot.reply_to(message, "⏳ Veriler çekiliyor ve analiz ediliyor...")
    try:
        url = "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT"
        cevap = requests.get(url).json()
        
        son_fiyat = float(cevap['lastPrice'])
        en_yuksek = float(cevap['highPrice'])
        en_dusuk = float(cevap['lowPrice'])
        
        pivot = (en_yuksek + en_dusuk + son_fiyat) / 3
        direnc_1 = (pivot * 2) - en_dusuk
        destek_1 = (pivot * 2) - en_yuksek
        
        # Stop-Loss hesaplaması (Mevcut desteğin %2 altı olarak ayarlandı)
        stop_loss = destek_1 * 0.98
        
        analiz_mesaji = (
            f"📊 *BTC/USDT HIZLI ANALİZ* 📊\n\n"
            f"💵 *Anlık Fiyat:* {son_fiyat:,.2f} $\n"
            f"📈 *24s Yüksek:* {en_yuksek:,.2f} $\n"
            f"📉 *24s Düşük:* {en_dusuk:,.2f} $\n\n"
            f"🧱 *Direnç:* {direnc_1:,.2f} $\n"
            f"🛡️ *Destek:* {destek_1:,.2f} $\n"
            f"🛑 *Stop-Loss:* {stop_loss:,.2f} $"
        )
        bot.reply_to(message, analiz_mesaji, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"⚠️ Veri çekilemedi. Hata: {e}")


# --- 2. KENDİ WAVETREND (WT) MOTORUMUZ ---
def binance_veri_cek(symbol="BTCUSDT", interval="4h", limit=1000):
    """Binance üzerinden son mum verilerini çeker (Limit 1000 yapılarak TradingView ile eşitlendi)"""
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    res = requests.get(url)
    data = res.json()
    
    # Verileri bir tabloya (DataFrame) dönüştürüyoruz
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
    global son_sinyal_mumu
    """Belirli aralıklarla çalışıp kesişme olup olmadığını kontrol eder"""
    try:
        df = binance_veri_cek("BTCUSDT", "4h", 1000)
        wt1, wt2 = wt_hesapla(df)
        
        # Son kapanan mum (-2) ve bir önceki mumu (-3) kontrol ediyoruz
        onceki_wt1, onceki_wt2 = wt1.iloc[-3], wt2.iloc[-3]
        guncel_wt1, guncel_wt2 = wt1.iloc[-2], wt2.iloc[-2]
        kapanis_fiyati = df['close'].iloc[-2]
        mum_zamani = df['timestamp'].iloc[-2] # Sinyalin saat kimliği
        
        # Eğer bu 4 saatlik mumda zaten sinyal gönderdiysek tekrar etme
        if mum_zamani == son_sinyal_mumu:
            return
        
        # YUKARI KESİŞME (AL SİNYALİ) - Sadece -14'ün altındaysa
        if onceki_wt1 <= onceki_wt2 and guncel_wt1 > guncel_wt2 and guncel_wt1 < -14:
            mesaj = (f"🟢 *WT AL SİNYALİ (4s)* 🟢\n\n"
                     f"🔹 *Parite:* BTC/USDT\n"
                     f"💵 *Kapanış Fiyatı:* {kapanis_fiyati:,.2f} $\n"
                     f"📊 *WT Seviyesi:* {guncel_wt1:.2f}\n"
                     f"🎯 *Kriter:* -14 Altında Kesişim Yakalandı")
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mesaj, parse_mode='Markdown')
            son_sinyal_mumu = mum_zamani # Sinyali hafızaya al
            
        # AŞAĞI KESİŞME (SAT SİNYALİ) - Sadece -14'ün üzerindeyse
        elif onceki_wt1 >= onceki_wt2 and guncel_wt1 < guncel_wt2 and guncel_wt1 > -14:
            mesaj = (f"🔴 *WT SAT SİNYALİ (4s)* 🔴\n\n"
                     f"🔹 *Parite:* BTC/USDT\n"
                     f"💵 *Kapanış Fiyatı:* {kapanis_fiyati:,.2f} $\n"
                     f"📊 *WT Seviyesi:* {guncel_wt1:.2f}\n"
                     f"🎯 *Kriter:* -14 Üzerinde Kesişim Yakalandı")
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mesaj, parse_mode='Markdown')
            son_sinyal_mumu = mum_zamani # Sinyali hafızaya al
            
    except Exception as e:
        print(f"Tarama sırasında hata oluştu: {e}")

# Arka planda zamanlayıcıyı çalıştıran döngü
def zamanlayici_baslat():
    # Piyasayı her 15 dakikada bir taramasını söylüyoruz (isteğe göre değiştirilebilir)
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
    return "Bot Aktif ve Kendi Analizini Yapıyor!"


if __name__ == '__main__':
    # Telegram ve Zamanlayıcıyı aynı anda arka planda başlatıyoruz
    threading.Thread(target=telegram_dinle, daemon=True).start()
    threading.Thread(target=zamanlayici_baslat, daemon=True).start()
    
    print("Profesyonel Analiz Motoru Başlatıldı!")
    
    # Render'ın port ataması
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, host='0.0.0.0')
