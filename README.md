# Akademik İlan Takip Telegram Botu

Türkiye'deki resmî akademik personel ilanlarını kaynak bazında tarayan, koşulları aday profiliyle karşılaştıran ve yalnızca yetkili Telegram kullanıcılarına bildirim gönderen Python 3.12+ uygulaması.

## Özellikler

- Resmî Gazete, ilan.gov.tr ve üniversite duyuru sayfaları için genişletilebilir kaynak kaydı
- HTML/PDF metni, kaynak/ilan/son başvuru tarihi, içerik özeti ve tekrar tespiti
- Son başvuru tarihi geçmiş kayıtları yeni ilan olarak bildirmez
- OpenAI ile şemalı, temkinli uygunluk analizi; eşdeğer bölüm adı varsayımı yapmaz
- `/start`, `/tara`, `/sonilanlar`, `/uygun`, `/durum`, `/yardim` komutları
- Erişim/CAPTCHA/HTTP hatalarını tarama sonucundan ayrı raporlar
- Yerelde SQLite, üretim zamanlayıcısında Firestore

## Hızlı kurulum

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
pytest
```

`.env` içine `TELEGRAM_BOT_TOKEN` ve `AUTHORIZED_TELEGRAM_IDS` ekleyin. Yerelde test mesajı için:

```powershell
python -m akademik_ilan_takip.cli telegram-test --chat-id 123456789
python -m akademik_ilan_takip.cli scan --database-backend local
python -m akademik_ilan_takip.bot
```

Botu önce Telegram'da açıp `/start` gönderin; bot yalnızca `AUTHORIZED_TELEGRAM_IDS` içindeki kimliklerden gelen komutlara cevap verir. Kimliği öğrenmek için geçici olarak loglara bakmak yerine güvenli bir yönetici komutu eklemeyin; Telegram'ın `getUpdates` çıktısındaki `chat.id` değerini yalnızca yerel geliştirme sırasında inceleyin.

## GitHub Actions ve sırlar

`.github/workflows/telegram-test.yml` yalnızca elle çalışır ve seçilen `TELEGRAM_TEST_CHAT_ID`'ye doğrulama mesajı yollar. `scan.yml` her saat ve `workflow_dispatch` ile tarar. GitHub Actions sürekli Telegram komutu dinleyemez: komutlar için ayrı, sürekli çalışan `python -m akademik_ilan_takip.bot` polling servisini (Docker/VM/Cloud Run gibi) kullanın.

Repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `AUTHORIZED_TELEGRAM_IDS`
- `FIREBASE_SERVICE_ACCOUNT_JSON` (tek satır JSON)
- `OPENAI_API_KEY` (isteğe bağlı)

`telegram-test.yml` için ayrıca `TELEGRAM_TEST_CHAT_ID` repository variable'ı gerekir. `scan.yml` üretimde `DATABASE_BACKEND=firestore` kullanır; Firestore kimliği yoksa başarısız taramayı başarılı göstermez ve workflow hata verir.

## Kaynak eklemek

`config/sources.json` içindeki her kayıt resmî bir başlangıç sayfasıdır. Yeni üniversiteler `kind: "notice_page"` ve resmî duyuru URL'si eklenerek alınır. Genel tarayıcı yalnızca ilan anahtar kelimelerini taşıyan resmî bağlantıları izler; CAPTCHA, 401/403/429 ve şüpheli erişim yanıtlarını atlatmaya çalışmaz, hata olarak kaydeder. İlk kurulumda kaynak listesini kurumların güncel resmî duyuru adresleriyle düzenli olarak genişletin.

## Mimari ve sınırlamalar

GitHub Actions'ın dosya sistemi kalıcı değildir; bu nedenle saatlik üretim taraması Firestore olmadan çalıştırılmaz. SQLite sadece yerel geliştirme/test içindir. OpenAI anahtarı yoksa ilan metninden eğitim eşdeğerliği çıkarılmaz; kayıt `human_review` olarak işaretlenir. ALES/YDS puanı belirtilmemiş aday için bu koşullar kesin uygunluk sayılmaz.

Gerçek ilan taraması kaynakların sayfa yapısına bağlıdır. Tarama raporu her kaynak için başarı, bulunmuş bağlantı sayısı ve hatayı bildirir; erişilemeyen kaynaklar “başarılı” sayılmaz.
