import os
import threading
import requests
import telebot
from flask import Flask, request

# Telegram Bot Bilgileriniz
TELEGRAM_BOT_TOKEN = '8853302939:AAFSfbXJyJ9M6wCZ9HB0mJmp3kn_tOd6yRg'
TELEGRAM_CHAT_ID = '7497063079'

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# --- 1. TELEGRAM KOMUT DİNLEYİCİSİ (/analiz) ---
@bot.message_handler(commands=['analiz'])
def btc_analiz_gonder(message):
    bot.reply_to(message, "⏳ Veriler çekiliyor ve analiz ediliyor...")
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        cevap = requests.get(url).json()
        
        son_fiyat = float(cevap['lastPrice'])
        en_yuksek = float(cevap['highPrice'])
        en_dusuk = float(cevap['lowPrice'])
        
        # Pivot Hesaplaması
        pivot = (en_yuksek + en_dusuk + son_fiyat) / 3
        direnc_1 = (pivot * 2) - en_dusuk
        destek_1 = (pivot * 2) - en_yuksek
        stop_loss = destek_1 * 0.99
        
        analiz_mesaji = (
            f"📊 *BTC/USDT HIZLI ANALİZ* 📊\n\n"
            f"💵 *Anlık Fiyat:* {son_fiyat:,.2f} $\n"
            f"📈 *24s Yüksek:* {en_yuksek:,.2f} $\n"
            f"📉 *24s Düşük:* {en_dusuk:,.2f} $\n\n"
            f"🧱 *Direnç:* {direnc_1:,.2f} $\n"
            f"🛡️ *Destek:* {destek_1:,.2f} $\n"
            f"🛑 *Stop Loss:* {stop_loss:,.2f} $"
        )
        bot.reply_to(message, analiz_mesaji, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, "⚠️ Veri çekilemedi. Lütfen tekrar deneyin.")

# --- 2. TRADINGVIEW WEBHOOK DİNLEYİCİSİ ---
@app.route('/webhook', methods=['POST'])
def webhook_karsila():
    veri = request.json
    if veri:
        parite = veri.get('parite', 'Bilinmiyor')
        yon = veri.get('yon', '-')
        fiyat = veri.get('fiyat', '-')
        wt_seviye = veri.get('wt_seviyesi', '-')
        
        mesaj = (f"🚨 *YENİ WT SİNYALİ* 🚨\n\n"
                 f"🔹 *Parite:* {parite} (4s)\n"
                 f"🧭 *Yön:* {yon}\n"
                 f"📊 *WT Seviyesi:* {wt_seviye}\n"
                 f"💵 *Kapanış Fiyatı:* {fiyat} $")
        
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mesaj, parse_mode='Markdown')
        return "Başarılı", 200
        
    return "Veri alınamadı", 400

# Botu arka planda sürekli çalıştıracak fonksiyon
def telegram_bot_calistir():
    bot.infinity_polling()

if __name__ == '__main__':
    # Telegram botunu dinlemek için ayrı bir işlem (thread) başlatıyoruz
    threading.Thread(target=telegram_bot_calistir, daemon=True).start()
    
    print("Sistem bulut uyumlu olarak aktif edildi! Sinyaller bekleniyor...")
    
    # BULUT UYUMLU PORT AYARI
    # Render gibi platformlar kendi portlarını atarlar, bunu otomatik algılıyoruz:
    port = int(os.environ.get("PORT", 5000))
    app.run(port=port, host='0.0.0.0')