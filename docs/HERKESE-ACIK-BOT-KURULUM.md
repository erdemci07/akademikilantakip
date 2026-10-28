# Herkese açık Telegram botu: /start ile otomatik abonelik

Bu güncelleme mevcut `akademikilantakip` botunun saatlik Github Actions taramasını korur. Kullanıcılar Telegram'da botu açıp **/start** dediğinde otomatik olarak kaydolur; bundan sonra yeni akademik ilanları ve her saatki tarama raporunu alırlar. OpenAI API gerekli değildir.

## Güvenlik ve sistem mimarisi

1. **Firebase Functions (Python) HTTPS webhook**, Telegram komutlarını gerçek zamanlı karşılar. Sadece `private` sohbetlere hizmet verir, Telegram `X-Telegram-Bot-Api-Secret-Token` başlığını sabit zamanlı karşılaştırır. 403/405 durumları günlüğe yazılmaz.
2. **Firestore** `akademik_ilan_takip_subscribers/{chat_id}` koleksiyonunda yalnız `chat_id`, `active`, tarih ve kayıt kaynağını tutar. Gruplar otomatik abone edilmez.
3. **GitHub Actions `Hourly Academic Listing Scan`**, aynı Firestore veritabanında `active=true` aboneleri bulur. Yeni ilanların gerçek bağlantılarını ve saatlik özeti her birine gönderir.
4. Mevcut `AUTHORIZED_TELEGRAM_IDS` kullanıcıları ilk çalışmada **bir defa** Firestore'a aktarılır. Sonradan `/dur` veya `/sil` yaptıklarında tekrar otomatik kaydedilmezler.
5. **/start**, **/devam**, **/dur**, **/sil**, **/yardim**, **/sonilanlar**, **/durum** komutları webhook üzerinden çalışır. `/tara` herkese açık değildir. Eski `python -m akademik_ilan_takip.bot` polling servisini aynı anda çalıştırmayın; webhook ile polling aynı anda çalışamaz.
6. Bot engellendiğinde tarama 400/403 bildirim hatasını kaydeder, ilgili aboneliği pasifleştirir ve diğer abonelere devam eder. Telegram'un 429 / 5xx yanıtlarında kısa geri deneme vardır.

## A. Kod paketini GitHub'a uygulama

GitHub deposu: `erdemci07/akademikilantakip`.

1. Paketi açıp **`public_patch` klasörünü** depo köküne yükleyin.
2. Ayrı gelen `apply-public-subscriptions.yml` dosyasını GitHub'da **`.github/workflows/apply-public-subscriptions.yml`** yoluna yükleyin.
3. GitHub Actions sekmesinden **Apply Public Telegram Subscribers Patch → Run workflow** çalıştırın.
4. Testler yeşil olduğunda değişiklikler `main` dalına commit edilecektir. `public_patch` staging klasörü otomatik silinir. Mevcut saatlik tarama, test ve Telegram secrets korunur.

## B. Firebase Functions dağıtımı

**Gerekenler:** Firebase projesinde Firestore çalışır olmalı ve **Blaze (faturalandırma açık)** planına yükseltilmiş olmalı. Firebase Cloud Functions'ın Blaze gerekliliği vardır; ücretsiz kullanım kotası olsa bile fatura riski sıfır değildir. Firebase / Google Cloud'da bütçe uyarısı ayarlayın.

Kullanılan mevcut GitHub secrets:
- `FIREBASE_SERVICE_ACCOUNT_JSON` (Firebase projesinin servis hesabı)
- `TELEGRAM_BOT_TOKEN` (BotFather tokeni)
- `AUTHORIZED_TELEGRAM_IDS` (eski yönetici abonelerini bir kereliğine aktarmak için, isteğe bağlı)

Yeni bir GitHub secret oluşturmak gerekmiyor: **TELEGRAM_WEBHOOK_SECRET** rastgele oluşturulup Firebase Secret Manager'da saklanır. Bot tokeni de Firebase Secret Manager'a taşınır. İki sır da repoya veya GitHub loglarına yazılmaz.

1. GitHub Actions → **Deploy Public Telegram Webhook → Run workflow**.
2. Bu workflow Firebase CLI'yi kurar, gerekli iki Secret Manager secret'ını ayarlar, yalnız `telegram-public-subscribers` Functions codebase'ini deploy eder.
3. Ardından otomatik olarak Telegram `setWebhook` çağrısı yapılır ve webhook URL'si ile yetkisiz isteklerin engellendiği doğrulanır.
4. **Olası izin hataları**: Firebase servis hesabında Functions deploy / Service Usage / IAM `actAs` / Cloud Build, Artifact Registry ve Secret Manager yetkileri bulunmalıdır. Bu yetkiler standart Firebase Admin SDK JSON dosyasında otomatik garanti edilmez. Başka Firebase projelerinin servis hesaplarını paylaşmayın.
5. Her deployda webhook sırrı yenilenir ve Telegram'a yeniden kaydedilir. Eski webhook'un kısa süreli yeniden deneme kayıtları olması normal olabilir.

## C. Kullanıcı testi

1. Bota Telegram'da `/start` yazın. Bot hemen abonelik onayı göndermeli.
2. `/dur` yazın, bildirim kapansın; `/devam` yazın, yeniden açılsın.
3. `/sonilanlar` ve `/durum` komutlarını deneyin.
4. Başka bir Telegram hesabından `/start` yazın; o hesabın da otomatik onay aldığını kontrol edin.
5. GitHub Actions → **Hourly Academic Listing Scan → Run workflow**. Yeni ilan varsa bağlantıları, ilan olmasa da saatlik raporu her iki hesaba göndermelidir.
6. Son olarak botu paylaşın: `https://t.me/BOT_KULLANICI_ADI` (kendi gerçek bot adınızı yazın).

## Bilinen sınırlar

- GitHub'ın `cron` zamanlaması tam dakikasında çalışmayı garanti etmez; zaman zaman gecikme olabilir. Kullanıcılara bildirim göndermek için saatlik tarama işinin başarıyla tamamlanması gerekir.
- Webhook abonelik komutlarını anında karşılar; yeni kullanıcı eski ilanların tamamını otomatik almaz. `/sonilanlar` ile yakın zamanda saklanan bazı kayıtlara erişir.
- Kapsam mevcut tarama kaynaklarıyla sınırlıdır; kod güncellemesi kendiliğinden Türkiye'nin tüm üniversitelerini eklemez.
- Önceki kodun mevcut `scan` işlemi, yeni ilanları kalıcı olarak kaydedip hemen gönderiyor. Geçici bir Telegram arızasında ayrıntılı teslim kuyruğu / teslim başına tekrar deneme geçmişi henüz yoktur. Daha fazla kullanıcı için kuyruklu dağıtım ve teslim takibi geliştirilmelidir.
- Google Cloud maliyetleri ve Firestore okuma/yazma sayısı abone sayısıyla artabilir. Botun herkesin kullanımına açılması ücretsiz ve limitsiz hizmet demek değildir.
- Telegram webhook'u aktifken `getUpdates` ile çalışan polling servisi kullanılamaz. Bu dosyalar dışında ek bir bot süreci çalıştırmayın.
