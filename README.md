# BEFAS Sabah Paneli — Otomatik Kurulum Rehberi

Bu klasördeki dosyalar, her hafta içi sabahı kendiliğinden güncellenen
bir web sitesi kurmanı sağlar. Kod yazmana gerek yok — sadece aşağıdaki
adımları takip et.

## 1) GitHub'da yeni bir repo oluştur

1. github.com'da oturum aç, sağ üstteki **+** işaretine tıkla → **New repository**.
2. İsim ver, örn. `sabah-paneli`.
3. **Public** seç (GitHub Pages'in ücretsiz sürümü public repo istiyor).
4. "Add a README file" kutucuğunu **işaretleme** (biz zaten kendi README'imizi ekleyeceğiz).
5. **Create repository** butonuna bas.

## 2) Bu klasördeki dosyaları yükle

1. Az önce oluşturduğun repo sayfasında **"uploading an existing file"** linkine tıkla
   (veya "Add file" → "Upload files").
2. Bu klasördeki **tüm dosya ve klasörleri** (`build_panel.py`, `template.html`,
   `requirements.txt`, `index.html`, `README.md` ve `.github` klasörünün tamamı)
   sürükleyip bırak.
   - `.github` klasörünü yüklerken tarayıcı bazen gizli klasörleri göstermeyebilir;
     böyle bir durumda GitHub Desktop uygulamasını kullanmak (ücretsiz, kolay) daha
     rahat olur — istersen o adımları da anlatırım.
3. Sayfanın altındaki **Commit changes** butonuna bas.

## 3) GitHub Actions'a yazma izni ver

1. Repo içinde **Settings** sekmesine git.
2. Sol menüden **Actions → General**.
3. En altta **"Workflow permissions"** bölümünde **"Read and write permissions"**
   seçeneğini işaretle, **Save**'e bas.
   (Bu, botun her sabah `index.html`'i güncelleyip commit atabilmesi için gerekli.)

## 4) GitHub Pages'i aç

1. Yine **Settings** içinde sol menüden **Pages**.
2. **"Build and deployment"** altında **Source: Deploy from a branch** seç.
3. Branch olarak **main**, klasör olarak **/ (root)** seç, **Save**.
4. Birkaç dakika sonra sayfanın üstünde şu şekilde bir adres belirir:
   `https://<kullanici-adin>.github.io/sabah-paneli/`
   İşte sabah paneli bu adreste yaşayacak.

## 5) İlk çalıştırmayı elle tetikle (test için)

1. Repo içinde **Actions** sekmesine git.
2. Soldaki **"Sabah panelini güncelle"** işine tıkla.
3. Sağ üstteki **"Run workflow"** butonuna bas, tekrar **Run workflow** de.
4. ~1 dakika içinde yeşil tik görürsen her şey çalışıyor demektir — siteni
   yenileyip güncel verilerle geldiğini görebilirsin.
5. Kırmızı çarpı görürsen işin üstüne tıklayıp hata mesajını bana yapıştır,
   birlikte düzeltiriz (TEFAS/BİST tarafında zaman zaman küçük değişiklikler
   olabiliyor, bu normal).

## Sonrası

Artık hiçbir şey yapmana gerek yok. Her hafta içi sabahı (05:30 TRT) bot
kendiliğinden çalışıp veriyi güncelleyecek. Yeni bir fon eklemek ya da
karşılaştırma değiştirmek istersen `build_panel.py` dosyasının en üstündeki
`FUND_CODES` ve `COMPARE_PAIRS` listelerini düzenlemen yeterli — o kısmı
benimle birlikte de yapabiliriz.
