# Kapsamlı tarama güncellemesi — devreye alma notları

Bu paket **mevcut projeye uygulanacak dosya değişikliklerini** içerir. Bot tokeni veya başka secret içermez.

## Ne değişiyor?

- `config/sources.json` iki kaynaktan 14 kaynak girişine genişletildi: 13 resmî kaynak ve 1 üçüncü taraf keşif kaynağı. Her kaynağın erişimi ve gerçek ilan işleme başarısı GitHub Actions ortamında ayrıca ölçülmelidir; bu liste Türkiye'nin tüm üniversitelerini kapsamaz.
- Kaynak hataları birbirini durdurmaz. Bir duyuruya erişim hatası diğer duyuruların toplanmasını engellemez. Erişilemeyen PDF bağlantısı doğrulanmış resmî PDF olarak gösterilmez.
- Telegram mesajlarında resmî PDF, duyuru ve varsa açıkça belirtilmiş başvuru bağlantıları ayrı gösterilir. Resmî doğrulama yoksa uyarı düşer.
- OpenAI API gerekli değildir; anahtar yoksa ilanlar `human_review` olarak işaretlenir.
- Yeni duyuruların başvuru tarihi belirsizse bilgi kesin olarak sunulmaz. Kesin uygunluk iddiasında bulunulmaz.
- Basit belge düzeyinde tekrar denetimi uygulanır. Aynı belgenin farklı sitelerdeki aynen aynı resmî PDF URL'si varsa tek kayda indirgenir.

## Bilinen sınırlar / bir sonraki sprint

- Bu sürüm duyuru/PDF **belgesi bazında** çalışır. Çok kadrolu PDF'lerin güvenilir **satır bazlı ayrıştırılması henüz yoktur**.
- Aynı ilanın farklı URL'lerdeki kopyalarını semantik olarak birleştirme, ilan iptal/değişiklik takibi ve başvuru açık olduğunun kesin doğrulanması ayrıca geliştirilmeli.
- Resmî Gazete için son üç günün `Çeşitli İlânlar` HTML/PDF arşivini deneyen bir tarayıcı eklendi; erişim kısıtları ve PDF indeks yapısındaki değişiklikler yüzünden başarı garantisi vermez. ilan.gov.tr için hâlâ özel sayfalama adaptörü gerekir.
- Memurlar.net üçüncü taraf ilanları resmî kaynak olarak gösterilmez.
- GitHub Actions'ın saatlik işinin çalışması için Firestore servis hesabı `FIREBASE_SERVICE_ACCOUNT_JSON` secret olarak tanımlanmalıdır. `AUTHORIZED_TELEGRAM_IDS` ve `TELEGRAM_BOT_TOKEN` da secret olarak bulunmalıdır.
- Botun Telegram komutlarını sürekli dinlemesi ayrıca bir polling/webhook servisi ister.
- `test.yml` depoya yazıldıktan sonra testler ve lint GitHub'da tekrar çalıştırılmalı. Bu dosyalar GitHub'a otomatik gönderilmedi, çünkü GitHub entegrasyonu yazma yetkisi için 403 döndürdü.

## GitHub Actions

Mevcut `.github/workflows/test.yml` ve `.github/workflows/scan.yml` korunur. Mevcut scan işi her saat çalışır ve Firestore gerektirir. 403 kaynak hataları raporda görünür. Mevcut CLI kısmi kaynak başarısızlığında exit=1 döndürür; rapor gönderilmiş olsa da job kırmızı görünebilir.
