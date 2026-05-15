# Paratika Payment Provider for Odoo 19

[![Odoo 19](https://img.shields.io/badge/Odoo-19.0-green.svg)](https://odoo.com)
[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)

> 🇹🇷 Paratika ödeme altyapısı ile Odoo 19 entegrasyonu. **Kategori bazlı ödeme akışı** ve gelişmiş taksit yönetimi.

---

## ✨ Özellikler

### 🔹 Temel Ödeme Özellikleri
- ✅ Hosted Payment Page (HPP) entegrasyonu
- ✅ Direct POST 3D Secure desteği
- ✅ Direct POST MOTO (Mail/Telefon sipariş)
- ✅ Kart tokenizasyonu ile tek tıkla ödeme
- ✅ Ön-otorizasyon (pre-auth) ve post-otorizasyon
- ✅ Tam/kısmi iade (refund) desteği
- ✅ Çoklu para birimi (TRY, USD, EUR, GBP)

### 🔹 🆕 Kategori Bazlı Ödeme Akışı

# 1. Modülü Odoo addons dizinine kopyalayın
cp -r payment_paratika /path/to/odoo/addons/

# 2. Gereksinimleri yükleyin
pip install requests>=2.28.0

# 3. Odoo'yu güncelleyin
./odoo-bin -u payment_paratika -d your_database --stop-after-init

# 4. Veya UI'dan: Apps → Update Apps List → "Paratika" ara → Install

Konfigürasyon
1. Ödeme Sağlayıcı Ayarları
Ayarlar → Websiteler → Ödeme Sağlayıcıları → Paratika → Düzenle

Ödeme Sağlayıcı → Paratika → Kategori Ayarları sekmesi

# Örnek: Sadece Elektronik kategorisinde göster
Provider.paratika_category_restriction = 'allow'
Provider.paratika_allowed_category_ids = [(6, 0, [electronics_category_id])]

# Örnek: Kategori bazlı taksit
Provider.paratika_enable_category_installments = True
Provider.paratika_category_installment_ids = [
    (0, 0, {
        'category_id': electronics_category_id,
        'allowed_installments': '1,2,3',  # Max 3 taksit
        'default_installment': '1',
        'commission_rate': 2.5,  # %2.5 komisyon
    })
]

Test Kartları (Paratika Sandbox)

Ziraat Bankası:
  VISA: 4546711234567894
  MasterCard: 5401341234567891
  Expiry: 12/2026
  CVV: 000
  3D Şifre: a

Akbank:
  VISA: 4355084355084358
  MasterCard: 5571135571135575
  Expiry: 12/2030
  CVV: 000
  3D Şifre: a

Genel Test:
  Başarılı: responseCode = '00'
  Red: responseCode = '05'
  Sistem Hatası: responseCode = '99'
  
  
  
