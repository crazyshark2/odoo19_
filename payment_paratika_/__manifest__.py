# -*- coding: utf-8 -*-
{
    'name': 'Paratika Payment Provider',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Paratika Payment Provider for Odoo 19 with Category-Based Payment Flow',
    'description': """
Paratika Payment Provider for Odoo 19
=====================================

🔹 ÖZELLİKLER
-------------
• Hosted Payment Page (HPP) entegrasyonu
• Direct POST 3D Secure desteği
• Direct POST MOTO (Mail/Telefon sipariş)
• ✅ Kategori bazlı ödeme yöntemi filtreleme
• ✅ Kategori bazlı taksit kuralları
• Taksitli ödeme ve komisyon hesaplama
• Ön-otorizasyon (pre-auth) ve post-otorizasyon
• Tam/kısmi iade (refund) desteği
• Kart tokenizasyonu ile tek tıkla ödeme
• SHA512 hash güvenlik doğrulaması
• Çoklu para birimi desteği (TRY, USD, EUR, GBP)

🔹 KATEGORİ BAZLI ÖDEME AKIŞI
-----------------------------
• Ürün kategorilerine göre ödeme yöntemi gösterme/gizleme
• Belirli kategoriler için özel taksit seçenekleri
• Kategoriye özel banka/poz önceliklendirme
• Sepet içeriğine dinamik ödeme yöntemi filtreleme
• AJAX tabanlı kategori-payment method eşleştirme

🔹 DESTEKLENEN BANKALAR
----------------------
Akbank, İş Bankası, Garanti BBVA, Yapı Kredi, QNB Finansbank, 
Halkbank, Vakıfbank, Ziraat Bankası, TEB, Denizbank, HSBC, 
Şekerbank, Alternatif Bank, ING, Kuveyt Türk, Albaraka Türk

🔹 GÜVENLİK
-----------
• Tüm callback'lerde SHA512 hash doğrulaması
• Session token bazlı tek kullanımlık oturumlar
• HTTPS zorunluluğu
• PCI-DSS uyumlu kart veri işleme

🔹 TEKNIK DETAYLAR
-----------------
• Odoo 19.0+ uyumlu
• Python 3.10+ gereksinimi
• PostgreSQL 14+ önerilir
• requests>=2.28.0 bağımlılığı

📞 DESTEK: info@resetbilisim.com | 0850 441 61 61
    """,
    'author': 'Reset Bilişim Teknolojileri',
    'contributors': ['Reset Bilişim Dev Team'],
    'website': 'https://www.resetbilisim.com',
    'license': 'LGPL-3',
    
    'depends': [
        'base',
        'payment',
        'website',
        'website_sale',
        'product',
        'sale',
    ],
    
    'external_dependencies': {
        'python': ['requests>=2.28.0'],
    },
    
    'data': [
        # Security
        'security/paratika_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/paratika_bank_data.xml',
        'data/payment_provider_data.xml',
        'data/ir_cron_data.xml',
        
        # Views
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/product_category_views.xml',
        'views/payment_templates.xml',
        'views/portal_templates.xml',
    ],
    
    'assets': {
        'web.assets_frontend': [
            'payment_paratika/static/src/css/paratika_payment.css',
            'payment_paratika/static/src/css/bank_selector.css',
            'payment_paratika/static/src/js/paratika_payment.js',
            'payment_paratika/static/src/js/category_payment_widget.js',
        ],
        'web.assets_backend': [
            'payment_paratika/static/src/css/paratika_payment.css',
        ],
    },
    
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}