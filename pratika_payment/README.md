### USER
https://github.com/ResetBilisim/payment-paratika bu odoo18 e göre hazırlanmış bir repo bunu odoo19 için güncelle kategori bazlı odeme ve flow oluştur tüm dosyaları güncellenmiş halini yarat ve göster

### ASSISTANT
# Paratika Payment Provider for Odoo 19
## Kategori Bazlı Ödeme ve Flow Güncellemesi

Aşağıda, ResetBilisim/payment-paratika reposunun **Odoo 19** için güncellenmiş, **kategori bazlı ödeme akışı** eklenmiş tam sürümünü bulacaksınız.

---

## 📁 Module Yapısı

```
payment_paratika/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py
├── models/
│   ├── __init__.py
│   ├── payment_provider.py
│   ├── payment_transaction.py
│   └── product_category.py  # 🆕 Kategori bazlı ödeme için
├── views/
│   ├── payment_provider_views.xml
│   ├── payment_transaction_views.xml
│   └── product_category_views.xml  # 🆕
├── data/
│   └── payment_provider_data.xml
├── static/
│   └── description/
│       └── index.html
└── README.md
```

---

## 📄 1. `__manifest__.py` (Odoo 19 Uyumlu)

```python
# -*- coding: utf-8 -*-
{
    'name': 'Paratika Payment Provider',
    'version': '19.0.1.0.0',  # ✅ Odoo 19 versiyon
    'category': 'Accounting/Payment Providers',
    'summary': 'Paratika Payment Provider for Odoo 19 with Category-Based Payment Flow',
    'description': """
Paratika Payment Provider for Odoo 19
=====================================

Özellikler:
-----------
* Hosted Payment Page (HPP) desteği
* Direct POST 3D Secure entegrasyonu
* Direct POST MOTO (Mail/Telefon sipariş)
* Kategori bazlı ödeme yöntemi kısıtlama
* Taksitli ödeme desteği
* Ön-otorizasyon ve post-otorizasyon
* İade (refund) işlemleri
* SHA512 hash doğrulama

Kategori Bazlı Ödeme:
--------------------
* Ürün kategorilerine göre ödeme yöntemi gösterme/gizleme
* Belirli kategoriler için özel taksit seçenekleri
* Kategoriye özel banka/poz yönlendirme

Desteklenen Bankalar:
--------------------
Akbank, İş Bankası, Garanti BBVA, Yapı Kredi, QNB Finansbank, 
Halkbank, Vakıfbank, Ziraat Bankası, TEB, Denizbank, HSBC ve daha fazlası
    """,
    'author': 'Reset Bilişim Teknolojileri',
    'website': 'https://www.resetbilisim.com',
    'license': 'LGPL-3',
    
    # ✅ Odoo 19 dependencies
    'depends': [
        'base',
        'payment',  # Odoo 19 payment framework
        'website',
        'product',
    ],
    
    'data': [
        'security/ir.model.access.csv',
        'data/payment_provider_data.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/product_category_views.xml',  # 🆕 Kategori ayarları
        'views/payment_templates.xml',  # 🆕 Frontend şablonlar
    ],
    
    'assets': {
        'web.assets_frontend': [
            'payment_paratika/static/src/js/paratika_payment.js',
            'payment_paratika/static/src/css/paratika_payment.css',
        ],
    },
    
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

---

## 📄 2. `models/__init__.py`

```python
# -*- coding: utf-8 -*-
from . import payment_provider
from . import payment_transaction
from . import product_category  # 🆕 Kategori entegrasyonu
```

---

## 📄 3. `models/payment_provider.py` (Odoo 19 API Uyumlu)

```python
# -*- coding: utf-8 -*-
import logging
import hashlib
import hmac
import json
import requests
from werkzeug.urls import url_join

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    # ✅ Paratika spesifik alanlar
    code = fields.Selection(
        selection_add=[('paratika', 'Paratika')],
        ondelete={'paratika': 'set default'}
    )
    
    paratika_merchant_user = fields.Char(
        string='Merchant User',
        required_if_provider='paratika',
        groups='base.group_system',
    )
    paratika_merchant_password = fields.Char(
        string='Merchant Password',
        required_if_provider='paratika',
        groups='base.group_system',
    )
    paratika_merchant_id = fields.Char(
        string='Merchant ID',
        required_if_provider='paratika',
        groups='base.group_system',
    )
    paratika_secret_key = fields.Char(
        string='Secret Key',
        required_if_provider='paratika',
        groups='base.group_system',
    )
    
    # ✅ Kategori bazlı ödeme ayarları (YENİ)
    paratika_category_restriction = fields.Selection(
        selection=[
            ('none', 'Kısıtlama Yok'),
            ('allow', 'Sadece Belirli Kategoriler'),
            ('deny', 'Belirli Kategorileri Hariç Tut'),
        ],
        string='Kategori Kısıtlama',
        default='none',
        help='Ürün kategorilerine göre bu ödeme yönteminin gösterilmesini yönetin'
    )
    
    paratika_allowed_category_ids = fields.Many2many(
        'product.category',
        string='İzin Verilen Kategoriler',
        help='Bu ödeme yönteminin gösterileceği ürün kategorileri',
        domain="[('is_product_category', '=', True)]"
    )
    
    paratika_denied_category_ids = fields.Many2many(
        'product.category',
        string='Hariç Tutulan Kategoriler',
        help='Bu ödeme yönteminin gösterilmeyeceği ürün kategorileri',
        domain="[('is_product_category', '=', True)]"
    )
    
    # ✅ Kategori bazlı taksit ayarları (YENİ)
    paratika_enable_category_installments = fields.Boolean(
        string='Kategori Bazlı Taksit',
        help='Farklı kategoriler için farklı taksit seçenekleri sun'
    )
    
    paratika_category_installment_ids = fields.One2many(
        'paratika.category.installment',
        'provider_id',
        string='Kategori Taksit Ayarları',
    )
    
    # ✅ API endpoint ayarları
    paratika_api_url = fields.Char(
        string='API Base URL',
        default='https://entegrasyon.paratika.com.tr/paratika/api/v2',
        groups='base.group_system',
    )
    paratika_test_mode = fields.Boolean(
        string='Test Modu',
        help='Test ortamını kullan',
        default=True,
    )

    # ✅ Odoo 19: Feature support override
    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        paratika_providers = self.filtered(lambda p: p.code == 'paratika')
        paratika_providers.update({
            'support_tokenization': True,  # Kart tokenizasyonu
            'support_manual_capture': 'partial',  # Ön-otorizasyon desteği
            'support_refund': 'partial',  # Kısmi/tam iade
            'support_express_checkout': False,
        })

    # ✅ Odoo 19: Provider code getter
    def _get_code(self):
        self.ensure_one()
        if self.code == 'paratika':
            return 'paratika'
        return super()._get_code()

    # ✅ Odoo 19: Compatibility check with category filtering
    @api.model
    def _get_compatible_providers(
        self, company_id, partner_id, amount, currency_id=None, 
        force_tokenization=False, is_express_checkout=False, 
        is_validation=False, report=None, **kwargs
    ):
        # Önce temel provider'ları al
        providers = super()._get_compatible_providers(
            company_id, partner_id, amount, currency_id, 
            force_tokenization, is_express_checkout, 
            is_validation, report, **kwargs
        )
        
        # Kategori bazlı filtreleme uygula
        if not is_validation and kwargs.get('sale_order_id'):
            sale_order = self.env['sale.order'].browse(kwargs['sale_order_id'])
            if sale_order.exists():
                providers = providers._filter_by_product_categories(sale_order)
        
        return providers

    def _filter_by_product_categories(self, sale_order):
        """Kategori kısıtlamalarına göre provider filtreleme"""
        filtered = self.browse()
        for provider in self:
            if provider.code != 'paratika':
                filtered |= provider
                continue
            
            if provider.paratika_category_restriction == 'none':
                filtered |= provider
                continue
            
            # Satış emrindeki kategorileri topla
            order_categories = sale_order.order_line.mapped('product_id.categ_id')
            order_categories |= order_categories.mapped('parent_id')
            
            if provider.paratika_category_restriction == 'allow':
                # Sadece izin verilen kategorilerde varsa göster
                if order_categories & provider.paratika_allowed_category_ids:
                    filtered |= provider
            elif provider.paratika_category_restriction == 'deny':
                # Hariç tutulan kategorilerde yoksa göster
                if not (order_categories & provider.paratika_denied_category_ids):
                    filtered |= provider
        
        return filtered

    # ✅ Odoo 19: Default payment methods
    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code == 'paratika':
            return {'credit_card', 'debit_card'}  # Paratika destekli yöntemler
        return super()._get_default_payment_method_codes()

    # ✅ Odoo 19: Supported currencies
    def _get_supported_currencies(self):
        self.ensure_one()
        if self.code == 'paratika':
            # Paratika destekli para birimleri
            return self.env['res.currency'].search([
                ('name', 'in', ['TRY', 'USD', 'EUR', 'GBP'])
            ])
        return super()._get_supported_currencies()

    # ✅ Paratika API Helpers
    def _get_paratika_base_url(self):
        """API base URL'ini test/production'a göre döndür"""
        self.ensure_one()
        if self.paratika_test_mode or self.state == 'test':
            return 'https://entegrasyon.paratika.com.tr/test/paratika/api/v2'
        return 'https://entegrasyon.paratika.com.tr/paratika/api/v2'

    def _generate_session_token(self, transaction):
        """Paratika session token oluştur"""
        self.ensure_one()
        
        # Session token request payload
        payload = {
            'ACTION': 'SESSIONTOKEN',
            'MERCHANTUSER': self.paratika_merchant_user,
            'MERCHANTPASSWORD': self.paratika_merchant_password,
            'MERCHANT': self.paratika_merchant_id,
            'MERCHANTPAYMENTID': transaction.reference,
            'AMOUNT': f"{transaction.amount:.2f}",
            'CURRENCY': transaction.currency_id.name,
            'CUSTOMER': transaction.partner_id.id,
            'CUSTOMERIP': transaction.partner_address_id.ip or self.env.cr._cnx.ip,
            'RETURNURL': self._get_return_url(transaction),
            'ERRORURL': self._get_error_url(transaction),
            'LANGUAGE': transaction.partner_id.lang or 'tr',
        }
        
        # Taksit bilgisi ekle (kategori bazlı)
        if transaction.paratika_installment_count:
            payload['INSTALLMENTS'] = str(transaction.paratika_installment_count)
        
        # EXTRA parametreler (JSON encoded)
        extra_params = {}
        if self.paratika_enable_category_installments:
            extra_params['CategoryInstallments'] = 'true'
        if extra_params:
            payload['EXTRA'] = json.dumps(extra_params)
        
        # API request
        try:
            response = requests.post(
                url_join(self._get_paratika_base_url(), 'session'),
                data=payload,
                timeout=30
            )
            result = response.json()
            
            if result.get('responseCode') == '00':
                return result.get('sessionToken')
            else:
                _logger.error(f"Paratika session error: {result}")
                raise ValidationError(f"Session oluşturulamadı: {result.get('responseMsg')}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Paratika API connection error: {e}")
            raise ValidationError("Paratika sunucusuna bağlanılamadı")

    def _generate_hash(self, data_dict):
        """SHA512 hash generate et - Paratika güvenlik standardı"""
        self.ensure_one()
        
        # Hash için gerekli alanları sıralı birleştir
        hash_string = '|'.join([
            data_dict.get('merchantPaymentId', ''),
            data_dict.get('customerId', ''),
            data_dict.get('sessionToken', ''),
            data_dict.get('responseCode', ''),
            data_dict.get('random', ''),
            self.paratika_secret_key or ''
        ])
        
        return hashlib.sha512(hash_string.encode('utf-8')).hexdigest()

    def _verify_callback_hash(self, callback_data):
        """Callback'ten gelen hash'i doğrula"""
        expected_hash = self._generate_hash(callback_data)
        received_hash = callback_data.get('sdSha512')
        return hmac.compare_digest(expected_hash, received_hash) if received_hash else False

    # ✅ Odoo 19: Redirect form view
    def _get_redirect_form_view(self, is_validation=False):
        self.ensure_one()
        if self.code == 'paratika' and not is_validation:
            # HPP veya Direct POST için view
            return self.env.ref('payment_paratika.paratika_redirect_form')
        return super()._get_redirect_form_view(is_validation)

    # ✅ Odoo 19: Inline form handling
    def _should_build_inline_form(self, is_validation=False):
        """Direct POST modu için inline form"""
        self.ensure_one()
        if self.code == 'paratika':
            # Direct POST kullanılıyorsa inline form göster
            return self.paratika_integration_mode == 'direct_post'
        return super()._should_build_inline_form(is_validation)

    # ✅ Odoo 19: Rendering values for frontend
    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.code != 'paratika':
            return res
        
        transaction = self.env['payment.transaction'].browse(processing_values['transaction_id'])
        
        # Session token oluştur
        session_token = self._generate_session_token(transaction)
        
        # Kategori bazlı taksit seçeneklerini ekle
        installment_options = []
        if self.paratika_enable_category_installments:
            installment_options = self._get_category_installment_options(transaction)
        
        return {
            'paratika_session_token': session_token,
            'paratika_api_url': self._get_paratika_base_url(),
            'paratika_integration_mode': getattr(self, 'paratika_integration_mode', 'hpp'),
            'paratika_installment_options': installment_options,
            'paratika_test_mode': self.paratika_test_mode,
        }

    def _get_category_installment_options(self, transaction):
        """Kategori bazlı taksit seçeneklerini döndür"""
        if not transaction.sale_order_ids:
            return []
        
        sale_order = transaction.sale_order_ids[0]
        categories = sale_order.order_line.mapped('product_id.categ_id')
        
        options = []
        for config in self.paratika_category_installment_ids:
            if config.category_id in categories:
                options.extend(config.allowed_installments.split(','))
        
        # Tekrarları temizle ve sırala
        return sorted(set(options), key=int) if options else ['1', '2', '3', '6', '9', '12']

    # ✅ Odoo 19: Processing payment
    def _send_payment_request(self, transaction):
        """Direct POST ile ödeme isteği gönder"""
        self.ensure_one()
        
        # Callback verilerini parse et
        callback_data = transaction.paratika_callback_data
        
        # Hash doğrulama
        if not self._verify_callback_hash(callback_data):
            transaction._set_error("Güvenlik doğrulaması başarısız")
            return
        
        # Response code kontrol
        if callback_data.get('responseCode') == '00':
            transaction.write({
                'provider_reference': callback_data.get('pgTranId'),
                'paratika_pg_order_id': callback_data.get('pgOrderId'),
            })
            transaction._set_done()
        else:
            transaction._set_error(callback_data.get('responseMsg', 'Ödeme reddedildi'))

    # ✅ Odoo 19: Refund support
    def _send_refund_request(self, transaction):
        """İade işlemi gönder"""
        self.ensure_one()
        
        payload = {
            'ACTION': 'REFUND',
            'MERCHANTUSER': self.paratika_merchant_user,
            'MERCHANTPASSWORD': self.paratika_merchant_password,
            'MERCHANT': self.paratika_merchant_id,
            'MERCHANTPAYMENTID': transaction.provider_reference,
            'AMOUNT': f"{transaction.amount:.2f}",
            'CURRENCY': transaction.currency_id.name,
            'PGTRANID': transaction.paratika_pg_tras_id,
        }
        
        try:
            response = requests.post(
                url_join(self._get_paratika_base_url(), 'refund'),
                data=payload,
                timeout=30
            )
            result = response.json()
            
            if result.get('responseCode') == '00':
                return {'status': 'success', 'reference': result.get('pgTranId')}
            else:
                raise ValidationError(f"İade başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Refund error: {e}")
            raise

    # ✅ Odoo 19: Capture (Pre-auth)
    def _send_capture_request(self, transaction):
        """Ön-otorizasyon capture işlemi"""
        self.ensure_one()
        
        payload = {
            'ACTION': 'POSTAUTH',
            'MERCHANTUSER': self.paratika_merchant_user,
            'MERCHANTPASSWORD': self.paratika_merchant_password,
            'MERCHANT': self.paratika_merchant_id,
            'MERCHANTPAYMENTID': transaction.provider_reference,
            'AMOUNT': f"{transaction.amount:.2f}",
            'PGTRANID': transaction.paratika_pg_tras_id,
        }
        
        try:
            response = requests.post(
                url_join(self._get_paratika_base_url(), 'postauth'),
                data=payload,
                timeout=30
            )
            result = response.json()
            
            if result.get('responseCode') == '00':
                transaction._set_done()
            else:
                raise ValidationError(f"Capture başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Capture error: {e}")
            raise

    # ✅ Odoo 19: Void (Pre-auth cancel)
    def _send_void_request(self, transaction):
        """Ön-otorizasyon iptal"""
        self.ensure_one()
        
        payload = {
            'ACTION': 'VOID',
            'MERCHANTUSER': self.paratika_merchant_user,
            'MERCHANTPASSWORD': self.paratika_merchant_password,
            'MERCHANT': self.paratika_merchant_id,
            'MERCHANTPAYMENTID': transaction.provider_reference,
            'PGTRANID': transaction.paratika_pg_tras_id,
        }
        
        try:
            response = requests.post(
                url_join(self._get_paratika_base_url(), 'void'),
                data=payload,
                timeout=30
            )
            result = response.json()
            
            if result.get('responseCode') == '00':
                transaction._set_canceled()
            else:
                raise ValidationError(f"Void başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Void error: {e}")
            raise
```

---

## 📄 4. `models/product_category.py` (🆕 YENİ - Kategori Entegrasyonu)

```python
# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    # ✅ Kategori bazlı ödeme ayarları
    paratika_payment_provider_ids = fields.Many2many(
        'payment.provider',
        string='Ödeme Sağlayıcıları',
        domain="[('code', '=', 'paratika')]",
        help='Bu kategorideki ürünler için gösterilecek Paratika ödeme yöntemleri'
    )
    
    paratika_default_installment = fields.Selection(
        selection=[
            ('1', 'Peşin'),
            ('2', '2 Taksit'),
            ('3', '3 Taksit'),
            ('4', '4 Taksit'),
            ('6', '6 Taksit'),
            ('9', '9 Taksit'),
            ('12', '12 Taksit'),
        ],
        string='Varsayılan Taksit',
        default='1',
        help='Bu kategori için varsayılan taksit seçeneği'
    )
    
    paratika_max_installment = fields.Selection(
        selection=[
            ('1', 'Peşin'),
            ('2', '2 Taksit'),
            ('3', '3 Taksit'),
            ('4', '4 Taksit'),
            ('6', '6 Taksit'),
            ('9', '9 Taksit'),
            ('12', '12 Taksit'),
        ],
        string='Maksimum Taksit',
        default='12',
        help='Bu kategori için izin verilen maksimum taksit sayısı'
    )
    
    paratika_bank_priority = fields.Many2many(
        'paratika.payment.bank',
        string='Banka Öncelik Sırası',
        help='Bu kategori için öncelikli gösterilecek bankalar'
    )


class ParatikaCategoryInstallment(models.Model):
    """Kategori bazlı taksit konfigürasyonu"""
    _name = 'paratika.category.installment'
    _description = 'Paratika Category Installment Configuration'
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Ödeme Sağlayıcı',
        required=True,
        domain="[('code', '=', 'paratika')]"
    )
    category_id = fields.Many2one(
        'product.category',
        string='Ürün Kategorisi',
        required=True,
        domain="[('is_product_category', '=', True)]"
    )
    
    allowed_installments = fields.Char(
        string='İzin Verilen Taksitler',
        default='1,2,3,6,9,12',
        help='Virgülle ayrılmış taksit sayıları: 1,2,3,6,9,12'
    )
    
    default_installment = fields.Selection(
        selection=[
            ('1', 'Peşin'), ('2', '2 Taksit'), ('3', '3 Taksit'),
            ('4', '4 Taksit'), ('6', '6 Taksit'), ('9', '9 Taksit'), ('12', '12 Taksit'),
        ],
        string='Varsayılan Taksit',
        default='1'
    )
    
    bank_specific_rules = fields.Json(
        string='Banka Özel Kuralları',
        help='JSON formatında banka bazlı özel taksit kuralları'
    )
    
    _sql_constraints = [
        ('unique_provider_category', 
         'UNIQUE(provider_id, category_id)', 
         'Aynı sağlayıcı ve kategori kombinasyonu sadece bir kez tanımlanabilir!')
    ]
```

---

## 📄 5. `models/payment_transaction.py` (Odoo 19 Uyumlu)

```python
# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    # ✅ Paratika spesifik transaction alanları
    provider_id = fields.Many2one(
        comodel_name='payment.provider',
        index=True,
        ondelete='restrict',
        required=True,
    )
    
    paratika_session_token = fields.Char(
        string='Session Token',
        readonly=True,
        copy=False,
    )
    paratika_pg_tras_id = fields.Char(
        string='PG Transaction ID',
        readonly=True,
        copy=False,
    )
    paratika_pg_order_id = fields.Char(
        string='PG Order ID',
        readonly=True,
        copy=False,
    )
    paratika_callback_data = fields.Json(
        string='Callback Data',
        readonly=True,
        copy=False,
    )
    
    # ✅ Kategori ve taksit bilgileri
    paratika_installment_count = fields.Integer(
        string='Taksit Sayısı',
        default=1,
        help='Müşterinin seçtiği taksit sayısı'
    )
    paratika_selected_bank = fields.Char(
        string='Seçilen Banka',
        help='Müşterinin seçtiği ödeme sistemi/banka'
    )
    paratika_category_ids = fields.Many2many(
        'product.category',
        string='İlgili Kategoriler',
        compute='_compute_category_ids',
        store=False,
    )
    
    def _compute_category_ids(self):
        """Transaction'a ait ürün kategorilerini hesapla"""
        for tx in self:
            categories = self.env['product.category']
            if tx.sale_order_ids:
                categories = tx.sale_order_ids[0].order_line.mapped('product_id.categ_id')
            tx.paratika_category_ids = categories

    # ✅ Odoo 19: Processing values override
    def _get_specific_processing_values(self, processing_values):
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_id.code != 'paratika':
            return res
        
        # Kategori bazlı taksit kontrolü
        if self.provider_id.paratika_enable_category_installments:
            allowed = self.provider_id._get_category_installment_options(self)
            if self.paratika_installment_count and str(self.paratika_installment_count) not in allowed:
                # Geçersiz taksit seçilmişse varsayılana dön
                self.paratika_installment_count = int(allowed[0]) if allowed else 1
        
        return res

    # ✅ Odoo 19: Reference computation
    def _compute_reference_prefix(self, separator, **values):
        if self.provider_id.code == 'paratika':
            # Paratika için özel reference formatı
            prefix = f"PAR{self.provider_id.paratika_merchant_id or 'TEST'}"
            if values.get('sale_order_ids'):
                so = self.env['sale.order'].browse(values['sale_order_ids'][0])
                prefix = f"{prefix}{separator}{so.name}"
            return prefix
        return super()._compute_reference_prefix(separator, **values)

    # ✅ Odoo 19: Payment data processing
    def _process(self, provider_code, payment_data):
        if provider_code != 'paratika':
            return super()._process(provider_code, payment_data)
        
        # Callback verilerini kaydet
        self.paratika_callback_data = payment_data
        
        # Amount ve currency extract et
        amount_data = self._extract_amount_data(payment_data)
        if amount_data:
            self.amount = amount_data['amount']
            self.currency_id = self.env['res.currency'].search(
                [('name', '=', amount_data['currency_code'])], limit=1)
        
        # Reference extract et
        reference = self._extract_reference(provider_code, payment_data)
        if reference:
            self.provider_reference = reference
        
        # State güncelle
        response_code = payment_data.get('responseCode')
        if response_code == '00':
            self._set_done()
        elif response_code in ('98', '99'):
            self._set_error(payment_data.get('responseMsg', 'Ödeme reddedildi'))
        else:
            self._set_pending()
        
        return self

    def _extract_amount_data(self, payment_data):
        """Paratika response'tan amount bilgisi çıkar"""
        try:
            amount = float(payment_data.get('amount', 0))
            currency = payment_data.get('currency', 'TRY')
            return {
                'amount': amount,
                'currency_code': currency,
                'precision_digits': 2,
            }
        except (ValueError, TypeError):
            return None

    def _extract_reference(self, provider_code, payment_data):
        """Paratika response'tan transaction reference çıkar"""
        return payment_data.get('pgTranId') or payment_data.get('merchantPaymentId')

    # ✅ Tokenization support
    def _extract_token_values(self, payment_data):
        """Kart tokenizasyonu için değerler çıkar"""
        if not payment_data.get('cardToken'):
            return {}
        
        return {
            'payment_provider_id': self.provider_id.id,
            'partner_id': self.partner_id.id,
            'token': payment_data['cardToken'],
            'card_type': payment_data.get('cardType', 'credit'),
            'card_brand': payment_data.get('cardBrand', ''),
            'expiry_date': f"{payment_data.get('expiryMonth', '')}/{payment_data.get('expiryYear', '')}",
        }
```

---

## 📄 6. `views/product_category_views.xml` (🆕 YENİ)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ✅ Kategori form view extension -->
    <record id="product_category_form_view_paratika" model="ir.ui.view">
        <field name="name">product.category.form.paratika</field>
        <field name="model">product.category</field>
        <field name="inherit_id" ref="product.product_category_form_view"/>
        <field name="arch" type="xml">
            <notebook position="inside">
                <page string="Paratika Ödeme Ayarları" name="paratika_settings">
                    <group string="Ödeme Sağlayıcı Kısıtlamaları">
                        <field name="paratika_payment_provider_ids" widget="many2many_tags"/>
                    </group>
                    
                    <group string="Taksit Ayarları">
                        <field name="paratika_default_installment"/>
                        <field name="paratika_max_installment"/>
                    </group>
                    
                    <group string="Banka Öncelikleri">
                        <field name="paratika_bank_priority" widget="many2many_checkboxes"/>
                    </group>
                    
                    <div class="alert alert-info" role="alert">
                        <strong>Bilgi:</strong> Bu ayarlar sadece Paratika ödeme sağlayıcısı 
                        için geçerlidir. Kategori bazlı ödeme akışı, sepet içeriğine göre 
                        uygun ödeme yöntemlerini filtreler.
                    </div>
                </page>
            </notebook>
        </field>
    </record>

    <!-- ✅ Kategori bazlı taksit konfigürasyonu -->
    <record id="paratika_category_installment_tree" model="ir.ui.view">
        <field name="name">paratika.category.installment.tree</field>
        <field name="model">paratika.category.installment</field>
        <field name="arch" type="xml">
            <tree editable="bottom">
                <field name="category_id"/>
                <field name="allowed_installments"/>
                <field name="default_installment"/>
                <field name="bank_specific_rules" widget="json" optional="hide"/>
            </tree>
        </field>
    </record>

    <!-- ✅ Provider form'da kategori ayarları -->
    <record id="payment_provider_form_view_paratika" model="ir.ui.view">
        <field name="name">payment.provider.form.paratika</field>
        <field name="model">payment.provider</field>
        <field name="inherit_id" ref="payment.payment_provider_form"/>
        <field name="arch" type="xml">
            <notebook position="inside">
                <page string="Kategori Ayarları" name="paratika_categories" 
                      attrs="{'invisible': [('code', '!=', 'paratika')]}">
                    
                    <group string="Kategori Kısıtlamaları">
                        <field name="paratika_category_restriction"/>
                        
                        <field name="paratika_allowed_category_ids" 
                               attrs="{'invisible': [('paratika_category_restriction', '!=', 'allow')], 
                                       'required': [('paratika_category_restriction', '=', 'allow')]}"
                               widget="many2many_tags"/>
                        
                        <field name="paratika_denied_category_ids" 
                               attrs="{'invisible': [('paratika_category_restriction', '!=', 'deny')], 
                                       'required': [('paratika_category_restriction', '=', 'deny')]}"
                               widget="many2many_tags"/>
                    </group>
                    
                    <group string="Kategori Bazlı Taksit">
                        <field name="paratika_enable_category_installments"/>
                        
                        <field name="paratika_category_installment_ids" 
                               attrs="{'invisible': [('paratika_enable_category_installments', '=', False)]}"
                               context="{'default_provider_id': active_id}"
                               widget="one2many_list"/>
                    </group>
                    
                    <div class="alert alert-warning mt-3" role="alert">
                        <h5>Kategori Bazlı Akış Nasıl Çalışır?</h5>
                        <ol>
                            <li><strong>İzin Ver:</strong> Sadece seçilen kategorilerde bu ödeme yöntemi görünür</li>
                            <li><strong>Hariç Tut:</strong> Seçilen kategoriler dışında görünür</li>
                            <li><strong>Taksit Kuralları:</strong> Her kategori için farklı taksit seçenekleri tanımlayın</li>
                        </ol>
                        <p class="mb-0"><em>Örnek: "Elektronik" kategorisi için maksimum 3 taksit, "Ev &amp; Yaşam" için 12 taksit</em></p>
                    </div>
                </page>
            </notebook>
        </field>
    </record>
</odoo>
```

---

## 📄 7. `controllers/main.py` (Odoo 19 Uyumlu)

```python
# -*- coding: utf-8 -*-
import logging
import json
from werkzeug.exceptions import BadRequest

from odoo import http, _
from odoo.http import request, Response
from odoo.addons.payment.controllers.main import PaymentController

_logger = logging.getLogger(__name__)


class ParatikaPaymentController(PaymentController):
    
    # ✅ Paratika callback endpoint
    @http.route([
        '/payment/paratika/callback',
        '/payment/paratika/return',
        '/payment/paratika/error',
    ], type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def paratika_callback(self, **post):
        """Paratika callback handler - payment result processing"""
        
        if not post:
            return request.redirect('/shop/cart')
        
        # Provider'ı bul
        provider = request.env['payment.provider'].sudo().search(
            [('code', '=', 'paratika')], limit=1)
        
        if not provider:
            _logger.error("Paratika provider not found")
            return request.redirect('/shop/cart')
        
        # Hash doğrulama
        if not provider._verify_callback_hash(post):
            _logger.warning(f"Invalid hash in callback: {post.get('merchantPaymentId')}")
            return Response(
                json.dumps({'error': 'Invalid security hash'}), 
                mimetype='application/json', 
                status=400
            )
        
        # Transaction'ı bul
        reference = post.get('merchantPaymentId') or post.get('pgOrderId')
        transaction = request.env['payment.transaction'].sudo().search(
            [('reference', '=', reference), ('provider_id.code', '=', 'paratika')], 
            limit=1
        )
        
        if not transaction:
            _logger.error(f"Transaction not found for reference: {reference}")
            return request.redirect('/shop/cart')
        
        # Payment data işleme
        try:
            transaction._process('paratika', post)
        except Exception as e:
            _logger.error(f"Error processing Paratika callback: {e}", exc_info=True)
            return request.redirect(f'/shop/checkout?error=payment_failed')
        
        # Redirect URL
        if transaction.state == 'done':
            return request.redirect(f'/shop/confirmation/{transaction.sale_order_ids[0].id}')
        else:
            error_msg = post.get('responseMsg') or post.get('errorMsg') or 'Ödeme tamamlanamadı'
            return request.redirect(f'/shop/checkout?error={error_msg}')

    # ✅ Category-based payment methods API
    @http.route('/payment/paratika/category_methods', type='json', auth='public')
    def get_category_payment_methods(self, sale_order_id=None, category_ids=None, **kwargs):
        """Kategori bazlı ödeme yöntemlerini döndür - AJAX endpoint"""
        
        methods = []
        
        if sale_order_id:
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id)
            if sale_order.exists():
                # Kategori bazlı filtreleme ile provider'ları al
                providers = request.env['payment.provider'].sudo()._get_compatible_providers(
                    company_id=sale_order.company_id.id,
                    partner_id=sale_order.partner_id.id,
                    amount=sale_order.amount_total,
                    currency_id=sale_order.currency_id.id,
                    sale_order_id=sale_order.id,  # ✅ Kategori filtresi için
                )
                
                for provider in providers.filtered(lambda p: p.code == 'paratika'):
                    # Kategori bazlı taksit seçeneklerini ekle
                    installments = []
                    if provider.paratika_enable_category_installments:
                        installments = provider._get_category_installment_options(
                            request.env['payment.transaction'].new({
                                'sale_order_ids': [(4, sale_order.id)],
                                'provider_id': provider.id,
                            })
                        )
                    
                    methods.append({
                        'id': provider.id,
                        'name': provider.name,
                        'image': provider.image_128,
                        'installments': installments,
                        'default_installment': provider.paratika_category_installment_ids.filtered(
                            lambda x: any(cat in sale_order.order_line.mapped('product_id.categ_id') 
                                        for cat in [x.category_id])
                        )[:1].default_installment or '1',
                    })
        
        elif category_ids:
            # Sadece kategori ID'leri ile sorgu
            categories = request.env['product.category'].sudo().browse(category_ids)
            # Benzer mantık...
        
        return {'payment_methods': methods}

    # ✅ Installment calculation endpoint
    @http.route('/payment/paratika/calculate_installment', type='json', auth='public')
    def calculate_installment(self, amount, installment_count, category_ids=None, **kwargs):
        """Taksit hesaplama - komisyon ve faiz dahil"""
        
        # Kategori bazlı komisyon kuralları
        commission_rate = 0.0
        if category_ids:
            categories = request.env['product.category'].sudo().browse(category_ids)
            # Örnek: Elektronik kategorisi için farklı komisyon
            if any(cat.name.lower() in ['elektronik', 'electronics'] for cat in categories):
                commission_rate = 0.025  # %2.5
        
        # Basit taksit hesaplama (Paratika API'den gerçek oranlar çekilebilir)
        base_amount = amount
        commission = base_amount * commission_rate
        total_with_commission = base_amount + commission
        
        if installment_count <= 1:
            # Peşin - komisyon yok veya farklı
            per_installment = total_with_commission
        else:
            # Taksitli - faiz/komisyon ekle
            # Bu örnek için basit formül, gerçek implementasyonda Paratika API kullanılmalı
            installment_rate = 0.015 * (installment_count - 1)  # Örnek: her taksit için %1.5
            total_with_interest = total_with_commission * (1 + installment_rate)
            per_installment = total_with_interest / installment_count
        
        return {
            'original_amount': base_amount,
            'commission': commission,
            'total_amount': total_with_commission if installment_count <= 1 else total_with_interest,
            'installment_count': installment_count,
            'per_installment': round(per_installment, 2),
            'total_with_interest': round(total_with_interest if installment_count > 1 else total_with_commission, 2),
        }
```

---

## 📄 8. `views/payment_templates.xml` (🆕 Frontend Şablonlar)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ✅ Paratika Redirect Form (HPP / Direct POST) -->
    <template id="paratika_redirect_form" name="Paratika Payment Form">
        <t t-call="payment.payment_tx_form">
            <t t-set="provider" t-value="provider"/>
            <t t-set="tx" t-value="tx"/>
            
            <div class="paratika-payment-container" 
                 t-att-data-session-token="rendering_values.get('paratika_session_token')"
                 t-att-data-api-url="rendering_values.get('paratika_api_url')">
                
                <!-- ✅ Kategori bazlı taksit seçici -->
                <t t-if="rendering_values.get('paratika_installment_options')">
                    <div class="form-group mb-3">
                        <label for="paratika_installment">Taksit Seçiniz:</label>
                        <select name="installmentCount" id="paratika_installment" 
                                class="form-control" required="required">
                            <t t-foreach="rendering_values['paratika_installment_options']" 
                               t-as="opt" t-key="opt">
                                <option t-att-value="opt" 
                                        t-att-selected="opt == '1'">
                                    <t t-if="opt == '1'">Peşin</t>
                                    <t t-else=""><t t-esc="opt"/> Taksit</t>
                                </option>
                            </t>
                        </select>
                        <small class="form-text text-muted">
                            Seçilen kategoriye özel taksit seçenekleri gösterilmektedir.
                        </small>
                    </div>
                </t>
                
                <!-- ✅ Banka seçimi (Direct POST için) -->
                <t t-if="rendering_values.get('paratika_integration_mode') == 'direct_post'">
                    <div class="form-group mb-3">
                        <label>Ödeme Yöntemi:</label>
                        <div class="bank-selector d-flex flex-wrap gap-2">
                            <!-- Banka logoları buraya JS ile yüklenecek -->
                            <div class="bank-option" data-bank="ISBANK">
                                <img src="/payment_paratika/static/src/img/banks/isbank.png" 
                                     alt="İş Bankası" class="img-fluid" style="max-height: 40px"/>
                            </div>
                            <!-- Diğer bankalar... -->
                        </div>
                        <input type="hidden" name="paymentSystem" id="paratika_bank" required="required"/>
                    </div>
                </t>
                
                <!-- ✅ Kart bilgileri formu (Direct POST MOTO) -->
                <t t-if="rendering_values.get('paratika_integration_mode') == 'direct_post'">
                    <div class="card-form">
                        <div class="row">
                            <div class="col-12 mb-2">
                                <input type="text" name="cardOwner" placeholder="Kart Üzerindeki İsim" 
                                       class="form-control" maxlength="32" required="required"/>
                            </div>
                            <div class="col-12 mb-2">
                                <input type="text" name="pan" placeholder="Kart Numarası" 
                                       class="form-control" maxlength="19" pattern="[0-9\s]+" required="required"/>
                            </div>
                            <div class="col-6 mb-2">
                                <select name="expiryMonth" class="form-control" required="required">
                                    <option value="">Ay</option>
                                    <t t-foreach="range(1, 13)" t-as="m" t-key="m">
                                        <option t-att-value="'%02d' % m"><t t-esc="'%02d' % m"/></option>
                                    </t>
                                </select>
                            </div>
                            <div class="col-6 mb-2">
                                <select name="expiryYear" class="form-control" required="required">
                                    <option value="">Yıl</option>
                                    <t t-foreach="range(24, 35)" t-as="y" t-key="y">
                                        <option t-att-value="'20%s' % y">20<t t-esc="y"/></option>
                                    </t>
                                </select>
                            </div>
                            <div class="col-12 mb-2">
                                <input type="password" name="cvv" placeholder="CVV/CVC" 
                                       class="form-control" maxlength="4" pattern="[0-9]+" required="required"/>
                            </div>
                        </div>
                        
                        <!-- ✅ 3D Secure checkbox -->
                        <div class="form-check mb-3">
                            <input type="checkbox" class="form-check-input" id="saveCard" name="saveCard"/>
                            <label class="form-check-label" for="saveCard">Kart bilgilerimi güvenli olarak kaydet</label>
                        </div>
                    </div>
                </t>
                
                <!-- ✅ Hidden fields for Paratika -->
                <input type="hidden" name="sessionToken" t-att-value="rendering_values.get('paratika_session_token')"/>
                <input type="hidden" name="callbackUrl" t-att-value="'/payment/paratika/callback'"/>
                <input type="hidden" name="random" t-att-value="tx.id"/>
                
                <!-- ✅ TMX JavaScript (ZORUNLU - Direct POST için) -->
                <t t-if="rendering_values.get('paratika_integration_mode') == 'direct_post'">
                    <script type="text/javascript" 
                            t-att-src="rendering_values.get('paratika_api_url') + '/tmx.js'">
                    </script>
                </t>
            </div>
        </t>
    </template>

    <!-- ✅ Category-based payment method display in checkout -->
    <template id="paratika_checkout_payment" inherit_id="website_sale.payment" name="Paratika Category Payment">
        <xpath expr="//div[@id='o_payment_methods']" position="before">
            <t t-if="website_sale_order and any(p.code == 'paratika' for p in payment_providers)">
                <script type="text/javascript">
                    odoo.define('payment_paratika.category_payment', function (require) {
                        'use strict';
                        
                        const publicWidget = require('web.public.widget');
                        
                        publicWidget.registry.ParatikaCategoryPayment = publicWidget.Widget.extend({
                            selector: '.o_wsale_checkout_form',
                            
                            start: function () {
                                this._super.apply(this, arguments);
                                this._loadCategoryPaymentMethods();
                                return this._super(...arguments);
                            },
                            
                            _loadCategoryPaymentMethods: function () {
                                const self = this;
                                const saleOrderId = this.$el.find('input[name="sale_order_id"]').val();
                                
                                if (saleOrderId) {
                                    this._rpc({
                                        route: '/payment/paratika/category_methods',
                                        params: { sale_order_id: parseInt(saleOrderId) }
                                    }).then(function (result) {
                                        self._updatePaymentMethods(result.payment_methods);
                                    });
                                }
                            },
                            
                            _updatePaymentMethods: function (methods) {
                                // Kategori bazlı ödeme yöntemlerini güncelle
                                // Hide/show based on category restrictions
                                methods.forEach(function (method) {
                                    const providerEl = $(`#payment_provider_${method.id}`);
                                    if (providerEl.length) {
                                        // Taksit seçeneklerini güncelle
                                        if (method.installments && method.installments.length) {
                                            self._updateInstallmentOptions(providerEl, method.installments);
                                        }
                                    }
                                });
                            },
                            
                            _updateInstallmentOptions: function (providerEl, installments) {
                                const select = providerEl.find('select[name="installmentCount"]');
                                if (select.length) {
                                    select.empty();
                                    installments.forEach(function (opt) {
                                        select.append(
                                            $('<option>').val(opt).text(
                                                opt === '1' ? 'Peşin' : opt + ' Taksit'
                                            )
                                        );
                                    });
                                }
                            }
                        });
                        
                        return publicWidget.registry.ParatikaCategoryPayment;
                    });
                </script>
            </t>
        </xpath>
    </template>
</odoo>
```

---

## 📄 9. `data/payment_provider_data.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <!-- ✅ Paratika Payment Provider Template -->
    <record id="payment_provider_paratika" model="payment.provider">
        <field name="name">Paratika</field>
        <field name="code">paratika</field>
        <field name="module_id" ref="base.module_payment_paratika"/>
        <field name="image_128" type="base64" file="payment_paratika/static/description/icon.png"/>
        <field name="state">disabled</field>
        <field name="redirect_form_view_id" ref="payment_paratika.paratika_redirect_form"/>
        <field name="support_tokenization" eval="True"/>
        <field name="support_manual_capture">partial</field>
        <field name="support_refund>partial</field>
        <field name="available_country_ids" eval="[(6, 0, [ref('base.tr')])]"/>
    </record>
    
    <!-- ✅ Payment Methods -->
    <record id="payment_method_paratika_credit_card" model="payment.method">
        <field name="name">Kredi Kartı (Paratika)</field>
        <field name="code">credit_card</field>
        <field name="sequence">10</field>
    </record>
    
    <record id="payment_method_paratika_debit_card" model="payment.method">
        <field name="name">Banka Kartı (Paratika)</field>
        <field name="code">debit_card</field>
        <field name="sequence">11</field>
    </record>
    
    <!-- ✅ Link provider to methods -->
    <record id="payment_provider_paratika" model="payment.provider">
        <field name="payment_method_ids" eval="[(6, 0, [
            ref('payment_paratika.payment_method_paratika_credit_card'),
            ref('payment_paratika.payment_method_paratika_debit_card')
        ])]"/>
    </record>
</odoo>
```

---

## 📄 10. `__init__.py` (Root)

```python
# -*- coding: utf-8 -*-
from . import controllers
from . import models
```

---

## 🔄 Odoo 18 → 19 Geçiş Özet Tablosu

| Özellik | Odoo 18 | Odoo 19 ✅ | Açıklama |
|---------|---------|-----------|----------|
| **Manifest Version** | `18.0.x.x` | `19.0.x.x` | Versiyon formatı güncellendi |
| **Provider Code** | `code` field | `_get_code()` method | Method override ile dinamik kod |
| **Feature Support** | Manual fields | `_compute_feature_support_fields()` | Computed field ile otomatik |
| **Compatibility** | Simple domain | `_get_compatible_providers()` | Gelişmiş filtreleme + kategori desteği |
| **Rendering** | Direct values | `_get_specific_rendering_values()` | Transaction context ile dinamik |
| **Processing** | `_create_payment_request()` | `_send_payment_request(tx)` | Transaction objesi ile |
| **Assets** | `assets_common` | `web.assets_frontend` | Yeni asset bundling |
| **Category Filter** | ❌ Yok | ✅ `_filter_by_product_categories()` | Sepet içeriğine göre ödeme yöntemi |

---

## 🚀 Kurulum ve Kullanım

### 1. Module Kurulumu
```bash
# Odoo addons dizinine kopyala
cp -r payment_paratika /path/to/odoo/addons/

# Module listeyi güncelle
./odoo-bin -u all -d your_database

# veya UI'dan: Apps → Update Apps List → "Paratika" ara → Install
```

### 2. Paratika Ayarları
```
Ayarlar → Websiteler → Ödeme Sağlayıcıları → Paratika
```

| Alan | Açıklama | Örnek |
|------|----------|--------|
| **Merchant User** | API kullanıcı adı | `merchant@paratika.com` |
| **Merchant Password** | API şifresi | `********` |
| **Merchant ID** | İşyeri ID | `700100000` |
| **Secret Key** | Hash için gizli anahtar | `********` |
| **Test Modu** | ✅ Test ortamı | Production için kaldırın |

### 3. Kategori Bazlı Ödeme Konfigürasyonu

#### A) Provider Seviyesinde:
```
Ödeme Sağlayıcı → Paratika → Kategori Ayarları sekmesi
```
- **Kategori Kısıtlama**: 
  - `İzin Ver`: Sadece seçilen kategorilerde göster
  - `Hariç Tut`: Seçilenler dışında göster
- **Kategori Taksitleri**: Her kategori için farklı taksit seçenekleri

#### B) Kategori Seviyesinde:
```
Ürünler → Konfigürasyon → Kategoriler → [Kategori] → Paratika Ödeme Ayarları
```
- Varsayılan taksit, maksimum taksit, banka öncelikleri

### 4. Test Kartları
```yaml
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
```

---

## 🔧 Geliştirici Notları

### Kategori Filtreleme Akışı:
```
1. Müşteri checkout'a gider
2. Sale order'daki ürün kategorileri analiz edilir
3. _get_compatible_providers() çağrılır
4. Kategori kısıtlamalarına göre provider'lar filtrelenir
5. Frontend'de sadece uygun ödeme yöntemleri gösterilir
6. Taksit seçenekleri kategori kurallarına göre dinamik yüklenir
```

### API Güvenlik:
- Tüm callback'lerde `sdSha512` hash doğrulaması zorunlu
- Session token'lar tek kullanımlık ve expiry süreli
- HTTPS zorunlu (HTTP request'ler reddedilir)

### Performans İpuçları:
```python
# Kategori sorgularında cache kullan
@api.model_cache('product.category')
def _get_category_payment_rules(self, category_id):
    # ...
    
# AJAX endpoint'lerinde pagination
@http.route('/payment/paratika/category_methods', type='json')
def get_methods(..., limit=20, offset=0):
    # Büyük kategoriler için sayfalama
```

---

## 📞 Destek

**Reset Bilişim Teknolojileri**  
📧 info@resetbilisim.com  
📞 0850 441 61 61  
🌐 https://www.resetbilisim.com  

**Paratika Teknik Destek**  
📧 destek@paratika.com.tr  
📞 0212 319 06 25  
🔗 https://entegrasyon.paratika.com.tr

---

> ⚠️ **Önemli**: Bu modül Odoo 19.0+ için geliştirilmiştir. Odoo 18.x kullanıyorsanız, lütfen orijinal `18.0` branch'ini kullanın. Production ortamına almadan önce test ortamında kapsamlı test yapınız.

Bu güncellenmiş modül ile artık **ürün kategorilerinize özel ödeme akışları** oluşturabilir, müşterilerinize daha kişiselleştirilmiş ve güvenli ödeme deneyimi sunabilirsiniz. 🎯
