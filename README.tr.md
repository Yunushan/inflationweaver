# InflationWeaver

**Finansal zaman serileri için enflasyon düzeltmesi, alım gücü ve reel getiri analizi.**

InflationWeaver, yatırımın nominal artışının yanında enflasyondan sonra ne kadar kazandırdığını hesaplar. İlk kullanım alanı, 1986'dan itibaren doğrulanmış veriyle BIST 100 analizi ve ayrı tanımlanan TÜİK, ENAG veya açıkça oluşturulmuş TÜİK–ENAG hibritidir. Aynı motor hisse, endeks, döviz, değerli metal, kripto, fon, mevduat, tahvil, konut endeksi ve strateji özsermaye eğrilerini işleyebilir.

[English](README.md) · [Hesaplama yöntemi](docs/methodology.md) · [Veri kaynakları](docs/data-sources.md) · [1986 veri rehberi](docs/history-1986.md) · [Gereksinim eşlemesi](docs/requirements.md) · [Mimari](docs/architecture.md) · [0BSD lisansı](LICENSE)

## Kapsam ve veri durumu

**0.1.0**, Python/Polars hesaplama motoru, CLI, Parquet/DuckDB yerel depolama, FastAPI, TypeScript/Next.js arayüzü, TradingView Lightweight Charts, Pine Script v6 çıktısı, veri bağdaştırıcıları, testler ve GitHub Actions içeren çalıştırılabilir bir başlangıç sürümüdür.

| İşlev | Davranış |
| --- | --- |
| Enflasyon | Endeks seviyeleri, aylık bileşik enflasyon, baz tarihi ve açık örtüşmeye dayalı hibrit |
| Getiri | Nominal/reel getiri, CAGR, drawdown ve alım gücü |
| Karşılaştırma | Ortak tarihler ve ortak para biriminde varlık/benchmark analizi |
| Portföy | Sabit adetli portföyün değer ve reel performans eğrisi |
| Veri denetimi | Tarih, yinelenen kayıt, sonlu/pozitif değer, aylık oran sürekliliği, CPI eskiliği ve metadata |
| Entegrasyon | Python, CLI, REST, CSV/JSON raporları, Pine ve strateji özsermaye bağdaştırıcısı |

**Depoda gerçek 1986–2026 piyasa/enflasyon veritabanı bulunmaz.** Örnekler açıkça **sentetik demo** olarak işaretlenmiştir. Bunlar gerçek XU100, TÜİK veya ENAG verisi değildir. Gerçek analizi, kullanma hakkına sahip olduğunuz doğrulanmış tarihsel verilerle çalıştırmalısınız. ENAG'ın 1986 geçmişi bulunmadığı için geçmişe uzatılmış bir hibrit, resmî ENAG serisi olarak sunulmaz.

## Hızlı kurulum

Python **3.11+** gerekir. Arayüz için ayrıca Node.js **22.18+** ve npm kullanılır; doğrulama Node.js 24 ile yapılmıştır. Komutları depo kökünden çalıştırın:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
inflationweaver demo --out reports/demo
```

Windows PowerShell'de aktivasyon komutu `.venv\Scripts\Activate.ps1` olur. `requirements.lock`, doğrulanmış bağımlılık sürümlerini yeniden kurar. Uyumlu yeni bağımlılıklarla geliştirme için `python -m pip install -e '.[dev]'` esnek alternatiftir; PowerShell'de `".[dev]"` yazın ve sürüm değişikliğinden sonra denetimleri çalıştırın.

```bash
inflationweaver analyze \
  --asset examples/data/demo_asset.csv \
  --inflation examples/data/demo_cpi.csv \
  --base-date 2023-01-01 \
  --synthetic \
  --out reports/analysis
```

Komut seçeneklerini `inflationweaver --help` ve `inflationweaver <komut> --help` ile görebilirsiniz.

## Veri biçimi

CSV için zorunlu sütunlar `date,value` şeklindedir. Ondalık ayıracı nokta, tarihler ISO `YYYY-MM-DD` olmalıdır. `YYYY-MM` dönemleri ayın ilk gününe dönüştürülür. CPI seviyesi ile aylık/yıllık enflasyon oranı aynı veri türü değildir. Aylık oran zincirlemesi eksik ayları reddeder. CPI seviyesi analizinde ise geriye doğru eşleme ve yaş sınırı kullanılır; sınır içindeki tek eksik ay kabul edilebilir. Kaynak sıklığını ayrıca denetleyin.

```csv
date,value,available_date
2023-01-01,100.0,2023-02-03
2023-02-01,102.0,2023-03-03
2023-03-01,104.5,2023-04-03
```

Bu sayılar ve yayın tarihleri yalnızca biçim örneğidir. `available_date`, gözlem ayını değil verinin gerçekten erişilebilir olduğu günü gösterir. Yayın tarihine göre geriye dönük test için bu sütun her gözleme eklenmelidir. Daha sonra revize edilmiş değerler, sadece yayın tarihi eklenerek geçmişte bilinen değerlere dönüşmez.

```bash
inflationweaver import \
  --file examples/data/demo_asset.csv \
  --id DEMO_XU100 \
  --kind price \
  --currency TRY \
  --synthetic
```

Gerçek veri için kendi dosyanızı ve kimliğinizi kullanın; `--synthetic` eklemeyin. CSV dışa aktarımlarının metadata dosyaları SHA-256 özeti taşır. Bu özet değişikliği saptar; kaynağın doğruluğunu bağımsız biçimde kanıtlamaz.

| Kaynak | Desteklenen yol | Kullanıcının sağlaması gereken |
| --- | --- | --- |
| TÜİK | CSV; doğrulanmış kod için EVDS uyumluluk bağdaştırıcısı | Seviye serisi, eski bazların bağlantıları ve yayın tarihleri |
| ENAG | CSV | Doğrulanmış aylık E-TÜFE değişimleri veya belgeli seviye serisi |
| FRED | API | Anahtar, seri kimliği, birim ve veri sürümü politikası |
| OECD | Boyut filtreleriyle SDMX CSV | Gerçek sorgu URL'si ve tek seri seçimi |
| TCMB EVDS | EVDS2 tek seri uyumluluk bağdaştırıcısı | API anahtarı, seri kodu ve hizmetin güncel sözleşmesinin doğrulanması |
| Piyasa verisi | CSV | Lisanslı/izinli geçmiş, para birimi ve şirket işlemleri düzeltmeleri |

FRED/OECD/EVDS bağdaştırıcıları güncel veri sürümünü getirir. Bunlar kapsamlı ALFRED veya geçmiş veri sürümü arşivi yerine geçmez. Tüm piyasalara ücretsiz otomatik geçmiş veri indirme iddiası yoktur.

## Desteklenen varlıklar

| Grup | Örnekler | Dikkat edilmesi gereken |
| --- | --- | --- |
| Türkiye endeksleri | XU100, XU030, XBANK | Fiyat/getiri ayrımı ve tarihsel ölçek |
| BIST hisseleri | THYAO, TUPRS, ASELS, ISCTR | Bölünme, sermaye artırımı ve temettü |
| Enflasyon | TÜİK, ENAG, ABD CPI | Seviye/aylık değişim ve tüketim sepeti |
| Döviz | USD/TRY, EUR/TRY | Kur yönü ve ortak para birimine çeviri |
| Metaller | Gram/ons altın, gümüş | Ağırlık birimi ve kotasyon para birimi |
| ABD endeksleri | S&P 500, Nasdaq 100, Dow Jones | Fiyat/toplam getiri ve gerekli kur dönüşümü |
| Kripto | BTC, ETH | Borsa, saat, para birimi ve geçmiş kapsamı |
| Fon/ETF | SPY, QQQ, TEFAS fonları | NAV, dağıtımlar, giderler ve kuruluş tarihi |
| Faiz/tahvil | Mevduat, devlet tahvili | Faiz oranı yerine yatırım değer/toplam getiri eğrisi |
| Gayrimenkul | Türkiye konut fiyat endeksi | Tek konut yatırımının net getirisiyle farklılık |

Türkiye'deki alım gücü için yabancı para varlığını önce **TRY'ye çevirin**, sonra seçtiğiniz Türkiye CPI serisiyle düzeltin. USD fiyatı doğrudan Türkiye CPI'sine bölmek Türkiye alım gücünü ölçmez. Vergi, komisyon, spread ve gelirlerin sonuçta yer alması için giriş değer eğrisine dahil edilmesi gerekir.

## Hesaplama mantığı

```text
nominal büyüme = varlığın bugünkü değeri / baz tarihteki değeri
enflasyon katsayısı = bugünkü CPI / baz tarihteki CPI
reel büyüme = nominal büyüme / enflasyon katsayısı
reel getiri = reel büyüme - 1
```

Varlık %50 artarken fiyatlar %25 artarsa reel getiri **%20** olur: `1.50 / 1.25 - 1`. %50'den %25 çıkarmak doğru bileşik sonuç değildir. Aylık enflasyonlar çarpılarak bileşiklenir; yıllık manşet oranlar aylık oran gibi kullanılamaz.

## 1986'dan itibaren XU100

[Borsa İstanbul kaydı](https://www.borsaistanbul.com/en/index/xu100), XU100 başlangıç tarihini **1 Ocak 1986** olarak verir. Bu referans tarihi, o gün alım satım gözlemi olduğu anlamına gelmez. Verinizde bulunan gerçek bir gözlem seçilmelidir.

1986 analizi için doğrulanmış XU100 geçmişi, aynı ölçeğe getirilmiş endeks değerleri ve kesintisiz uygun CPI geçmişi gerekir. Endekslerin 1997/2020 ölçek değişimleri ile 2005 TL dönüşümü birbirinden ayrı işlemlerdir. Eksik dönemler tahminle doldurulmaz. [Tarihsel veri rehberi](docs/history-1986.md) bu kontrolleri açıklar.

TÜİK–ENAG hibriti, tanımlı tarihten önce TÜİK'i ve sonra ENAG'ı kullanır; ortak gözlemde ardıl seri ölçeklenir. Sepet ve yöntem değişikliği görünür tutulmalıdır. Analitik bir senaryo olan bu seri, “1986'dan beri ENAG” olarak adlandırılamaz.

## Arayüz ve API

```bash
inflationweaver serve
```

API dokümantasyonu: <http://127.0.0.1:8000/docs>. Sağlık, katalog, seri, analiz, karşılaştırma ve sabit adetli portföy uçları sunulur.

```bash
cd web
npm ci
npm run dev
```

Arayüz: <http://localhost:3000>. CSV yükleme, CPI modu, baz tarihi, grafikler, metrikler, karşılaştırma ve dışa aktarma içerir. Örnek veri görünür biçimde sentetik olarak gösterilir. API adresini değiştirmek için `web/.env.example` dosyasındaki değişkeni kullanın.

## TradingView çıktısı

```bash
inflationweaver pine \
  --inflation examples/data/demo_cpi.csv \
  --symbol BIST:XU100 \
  --synthetic \
  --out reports/inflationweaver.pine
```

Oluşan dosyayı Pine Editor'e yapıştırıp grafiğe ekleyin. CPI geçmişi dosyanın içine gömülür; Pine bu projenin API'sinden veya ENAG sitesinden serbestçe veri çekmez. Veri değişince çıktıyı yeniden üretin. Standart günlük, haftalık ve aylık grafikler desteklenir; gün içi ve standart dışı grafikler reddedilir. Üretilen sözleşmeler yerel olarak denetlenir; canlı TradingView derlemesinin doğrulandığı iddia edilmez. Ayrıntılar [TradingView rehberindedir](docs/tradingview.md).

## Güncelleme ve doğrulama

```bash
inflationweaver update --manifest examples/update-manifest.json
python -m pytest
python -m ruff check .
python -m build
```

Örnek manifest yalnızca sentetik dosyaları yükler. Gerçek güncellemeler için doğru kaynak tanımları, gerekiyorsa anahtarlar, kullanım hakları ve kalıcı hedef gerekir. GitHub Actions test ve demo/rapor üretimini otomatikleştirir. Kodun klonlanması tek başına güncel bir tarihsel veritabanı sağlamaz.

```bash
cd web
npm run typecheck
npm test
npm run build
```

Paylaşılan dağıtımlar için kimlik doğrulama, TLS, istek sınırları, kontrollü CORS ve depolama eklenmelidir. Ayrıntılar [SECURITY.md](SECURITY.md) ve [CONTRIBUTING.md](CONTRIBUTING.md) içinde yer alır.

## Lisans

Projenin birinci taraf kodu ve dokümantasyonu **0BSD** ile lisanslanmıştır: © 2026 **Yunus ÇOĞAL**. Kullanım, kopyalama, değiştirme ve dağıtım ticari amaç dahil serbesttir; tam metin [LICENSE](LICENSE) dosyasındadır.

Bu lisans, dış veri kaynaklarını ve bağımlılıkları yeniden lisanslamaz. TradingView Lightweight Charts'ın kendi lisansı ve atıf koşulları korunur. Piyasa verisi, endeksler ve sağlayıcı API'leri için ilgili kullanım şartları geçerlidir.
