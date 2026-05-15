# -*- coding: utf-8 -*-
"""
Paratika Payment Provider Model for Odoo 19
Extends payment.provider with Paratika-specific fields and methods
"""
import logging
import hashlib
import hmac
import json
import requests
from datetime import datetime, timedelta

from werkzeug.urls import url_join

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'
    
    # =========================================================================
    # PARATIKA SPECIFIC FIELDS
    # =========================================================================
    
    code = fields.Selection(
        selection_add=[('paratika', 'Paratika')],
        ondelete={'paratika': 'set default'}
    )
    
    # API Credentials
    paratika_merchant_user = fields.Char(
        string='Merchant User',
        required_if_provider='paratika',
        groups='base.group_system',
        help='Paratika merchant panelinden alınan API kullanıcı adı'
    )
    paratika_merchant_password = fields.Char(
        string='Merchant Password',
        required_if_provider='paratika',
        groups='base.group_system',
        help='Paratika merchant panelinden alınan API şifresi'
    )
    paratika_merchant_id = fields.Char(
        string='Merchant ID',
        required_if_provider='paratika',
        groups='base.group_system',
        help='Paratika işyeri numarası (7 haneli)'
    )
    paratika_secret_key = fields.Char(
        string='Secret Key',
        required_if_provider='paratika',
        groups='base.group_system',
        help='Callback hash doğrulaması için gizli anahtar'
    )
    
    # Integration Settings
    paratika_integration_mode = fields.Selection(
        selection=[
            ('hpp', 'Hosted Payment Page (HPP)'),
            ('direct_post', 'Direct POST (3D Secure)'),
            ('direct_post_moto', 'Direct POST MOTO'),
        ],
        string='Entegrasyon Modu',
        default='hpp',
        required=True,
        help='HPP: Yönlendirme ile ödeme, Direct POST: Form içinde 3D Secure'
    )
    
    paratika_api_url = fields.Char(
        string='API Base URL',
        default='https://entegrasyon.paratika.com.tr/paratika/api/v2',
        groups='base.group_system',
    )
    paratika_test_mode = fields.Boolean(
        string='Test Modu',
        help='Test ortamını kullan (entegrasyon.paratika.com.tr)',
        default=True,
    )
    
    # =========================================================================
    # CATEGORY-BASED PAYMENT FIELDS (NEW)
    # =========================================================================
    
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
    
    # Category-based installment configuration
    paratika_enable_category_installments = fields.Boolean(
        string='Kategori Bazlı Taksit',
        help='Farklı kategoriler için farklı taksit seçenekleri sun'
    )
    
    paratika_category_installment_ids = fields.One2many(
        'paratika.category.installment',
        'provider_id',
        string='Kategori Taksit Ayarları',
    )
    
    # Bank priority by category
    paratika_category_bank_priority = fields.Json(
        string='Kategori Bazlı Banka Önceliği',
        help='JSON: {"category_id": ["bank1", "bank2"]}'
    )
    
    # =========================================================================
    # ODOO 19: FEATURE SUPPORT OVERRIDES
    # =========================================================================
    
    @api.depends('code')
    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        
        paratika_providers = self.filtered(lambda p: p.code == 'paratika')
        paratika_providers.update({
            'support_tokenization': True,
            'support_manual_capture': 'partial',
            'support_refund': 'partial',
            'support_express_checkout': False,
            'support_authorization': True,
        })
    
    def _get_code(self):
        """Odoo 19: Return provider code"""
        self.ensure_one()
        if self.code == 'paratika':
            return 'paratika'
        return super()._get_code()
    
    def _get_default_payment_method_codes(self):
        """Odoo 19: Default payment methods for this provider"""
        self.ensure_one()
        if self.code == 'paratika':
            return {'credit_card', 'debit_card'}
        return super()._get_default_payment_method_codes()
    
    def _get_supported_currencies(self):
        """Odoo 19: Supported currencies"""
        self.ensure_one()
        if self.code == 'paratika':
            return self.env['res.currency'].search([
                ('name', 'in', ['TRY', 'USD', 'EUR', 'GBP'])
            ])
        return super()._get_supported_currencies()
    
    # =========================================================================
    # CATEGORY FILTERING LOGIC
    # =========================================================================
    
    @api.model
    def _get_compatible_providers(
        self, company_id, partner_id, amount, currency_id=None, 
        force_tokenization=False, is_express_checkout=False, 
        is_validation=False, report=None, **kwargs
    ):
        """Odoo 19: Get compatible providers with category filtering"""
        
        # Get base compatible providers
        providers = super()._get_compatible_providers(
            company_id, partner_id, amount, currency_id, 
            force_tokenization, is_express_checkout, 
            is_validation, report, **kwargs
        )
        
        # Apply category-based filtering for Paratika
        if not is_validation and kwargs.get('sale_order_id'):
            sale_order = self.env['sale.order'].browse(kwargs['sale_order_id'])
            if sale_order.exists():
                providers = providers._filter_by_product_categories(sale_order)
        
        return providers
    
    def _filter_by_product_categories(self, sale_order):
        """Filter providers based on product categories in sale order"""
        
        filtered = self.browse()
        
        for provider in self:
            # Non-Paratika providers pass through
            if provider.code != 'paratika':
                filtered |= provider
                continue
            
            # No restriction = show always
            if provider.paratika_category_restriction == 'none':
                filtered |= provider
                continue
            
            # Get all categories from order lines (including parents)
            order_categories = sale_order.order_line.mapped('product_id.categ_id')
            order_categories |= order_categories.mapped('parent_id')
            
            if provider.paratika_category_restriction == 'allow':
                # Show only if order has at least one allowed category
                if order_categories & provider.paratika_allowed_category_ids:
                    filtered |= provider
                    
            elif provider.paratika_category_restriction == 'deny':
                # Show only if order has NO denied categories
                if not (order_categories & provider.paratika_denied_category_ids):
                    filtered |= provider
        
        return filtered
    
    def _check_category_compatibility(self, categories):
        """Check if provider is compatible with given categories"""
        self.ensure_one()
        
        if self.code != 'paratika':
            return True
        
        if self.paratika_category_restriction == 'none':
            return True
        
        # Include parent categories
        all_categories = categories | categories.mapped('parent_id')
        
        if self.paratika_category_restriction == 'allow':
            return bool(all_categories & self.paratika_allowed_category_ids)
        elif self.paratika_category_restriction == 'deny':
            return not bool(all_categories & self.paratika_denied_category_ids)
        
        return True
    
    # =========================================================================
    # CATEGORY INSTALLMENT LOGIC
    # =========================================================================
    
    def _get_category_installment_options(self, transaction):
        """Get installment options based on product categories in transaction"""
        
        if not self.paratika_enable_category_installments:
            # Return default options
            return ['1', '2', '3', '6', '9', '12']
        
        # Get categories from sale order or order lines
        categories = self.env['product.category']
        
        if transaction.sale_order_ids:
            categories = transaction.sale_order_ids[0].order_line.mapped('product_id.categ_id')
        elif transaction.order_id:
            categories = transaction.order_id.order_line.mapped('product_id.categ_id')
        
        if not categories:
            return ['1', '2', '3', '6', '9', '12']
        
        # Collect allowed installments from category configs
        allowed = set()
        for config in self.paratika_category_installment_ids:
            if config.category_id in categories:
                if config.allowed_installments:
                    allowed.update(config.allowed_installments.split(','))
        
        # Return sorted unique values, or default if none found
        if allowed:
            return sorted(allowed, key=lambda x: int(x))
        return ['1', '2', '3', '6', '9', '12']
    
    def _get_category_default_installment(self, transaction):
        """Get default installment count based on categories"""
        
        categories = self.env['product.category']
        if transaction.sale_order_ids:
            categories = transaction.sale_order_ids[0].order_line.mapped('product_id.categ_id')
        
        for config in self.paratika_category_installment_ids:
            if config.category_id in categories and config.default_installment:
                return config.default_installment
        
        return '1'
    
    # =========================================================================
    # PARATIKA API HELPERS
    # =========================================================================
    
    def _get_paratika_base_url(self):
        """Get API base URL based on test/production mode"""
        self.ensure_one()
        
        if self.paratika_test_mode or self.state == 'test':
            return 'https://entegrasyon.paratika.com.tr/test/paratika/api/v2'
        return self.paratika_api_url or 'https://entegrasyon.paratika.com.tr/paratika/api/v2'
    
    def _generate_session_token(self, transaction):
        """Generate Paratika session token for payment"""
        self.ensure_one()
        
        # Build request payload
        payload = {
            'ACTION': 'SESSIONTOKEN',
            'MERCHANTUSER': self.paratika_merchant_user,
            'MERCHANTPASSWORD': self.paratika_merchant_password,
            'MERCHANT': self.paratika_merchant_id,
            'MERCHANTPAYMENTID': transaction.reference,
            'AMOUNT': f"{transaction.amount:.2f}",
            'CURRENCY': transaction.currency_id.name,
            'CUSTOMER': transaction.partner_id.id,
            'CUSTOMERIP': self._get_customer_ip(transaction),
            'RETURNURL': self._get_return_url(transaction),
            'ERRORURL': self._get_error_url(transaction),
            'LANGUAGE': transaction.partner_id.lang or 'tr',
            'RANDOM': fields.Datetime.now().strftime('%Y%m%d%H%M%S'),
        }
        
        # Add installment info if selected
        if transaction.paratika_installment_count:
            payload['INSTALLMENTS'] = str(transaction.paratika_installment_count)
        
        # Add category-based extra parameters
        if self.paratika_enable_category_installments:
            payload['EXTRA'] = json.dumps({
                'CategoryInstallments': 'true',
                'CategoryRules': 'enabled'
            })
        
        # Make API request
        try:
            response = requests.post(
                url_join(self._get_paratika_base_url(), 'session'),
                data=payload,
                timeout=30,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseCode') == '00':
                return result.get('sessionToken')
            else:
                _logger.error(f"Paratika session error: {result}")
                raise ValidationError(f"Session oluşturulamadı: {result.get('responseMsg')}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Paratika API connection error: {e}")
            raise ValidationError("Paratika sunucusuna bağlanılamadı")
        except json.JSONDecodeError as e:
            _logger.error(f"Paratika API response parse error: {e}")
            raise ValidationError("Geçersiz API yanıtı")
    
    def _get_customer_ip(self, transaction):
        """Get customer IP address for transaction"""
        # Try to get from partner address
        if transaction.partner_address_id and transaction.partner_address_id.ip:
            return transaction.partner_address_id.ip
        
        # Fallback to request context
        try:
            return request.httprequest.environ.get('HTTP_X_REAL_IP') or \
                   request.httprequest.environ.get('REMOTE_ADDR') or '127.0.0.1'
        except:
            return '127.0.0.1'
    
    def _get_return_url(self, transaction):
        """Generate return URL for Paratika callback"""
        return url_join(request.httprequest.url_root, '/payment/paratika/callback')
    
    def _get_error_url(self, transaction):
        """Generate error URL for Paratika callback"""
        return url_join(request.httprequest.url_root, '/payment/paratika/error')
    
    def _generate_hash(self, data_dict):
        """Generate SHA512 hash for Paratika security"""
        self.ensure_one()
        
        # Paratika hash algorithm: pipe-separated values + secret key
        hash_string = '|'.join([
            str(data_dict.get('merchantPaymentId', '')),
            str(data_dict.get('customerId', '')),
            str(data_dict.get('sessionToken', '')),
            str(data_dict.get('responseCode', '')),
            str(data_dict.get('random', '')),
            self.paratika_secret_key or ''
        ])
        
        return hashlib.sha512(hash_string.encode('utf-8')).hexdigest()
    
    def _verify_callback_hash(self, callback_data):
        """Verify SHA512 hash from Paratika callback"""
        self.ensure_one()
        
        received_hash = callback_data.get('sdSha512')
        if not received_hash:
            return False
        
        expected_hash = self._generate_hash(callback_data)
        return hmac.compare_digest(expected_hash, received_hash)
    
    # =========================================================================
    # ODOO 19: RENDERING & PROCESSING OVERRIDES
    # =========================================================================
    
    def _get_redirect_form_view(self, is_validation=False):
        """Odoo 19: Get redirect form view"""
        self.ensure_one()
        if self.code == 'paratika' and not is_validation:
            return self.env.ref('payment_paratika.paratika_redirect_form')
        return super()._get_redirect_form_view(is_validation)
    
    def _should_build_inline_form(self, is_validation=False):
        """Odoo 19: Determine if inline form should be built"""
        self.ensure_one()
        if self.code == 'paratika':
            return self.paratika_integration_mode in ['direct_post', 'direct_post_moto']
        return super()._should_build_inline_form(is_validation)
    
    def _get_specific_rendering_values(self, processing_values):
        """Odoo 19: Get provider-specific rendering values"""
        res = super()._get_specific_rendering_values(processing_values)
        
        if self.code != 'paratika':
            return res
        
        transaction = self.env['payment.transaction'].browse(processing_values['transaction_id'])
        
        # Generate session token
        session_token = self._generate_session_token(transaction)
        
        # Get category-based installment options
        installment_options = []
        default_installment = '1'
        
        if self.paratika_enable_category_installments:
            installment_options = self._get_category_installment_options(transaction)
            default_installment = self._get_category_default_installment(transaction)
        
        return {
            **res,
            'paratika_session_token': session_token,
            'paratika_api_url': self._get_paratika_base_url(),
            'paratika_integration_mode': self.paratika_integration_mode,
            'paratika_installment_options': installment_options,
            'paratika_default_installment': default_installment,
            'paratika_test_mode': self.paratika_test_mode,
            'paratika_merchant_id': self.paratika_merchant_id,
        }
    
    # =========================================================================
    # PAYMENT PROCESSING METHODS
    # =========================================================================
    
    def _send_payment_request(self, transaction):
        """Odoo 19: Process payment request (callback handling)"""
        self.ensure_one()
        
        callback_data = transaction.paratika_callback_data
        if not callback_data:
            transaction._set_error("Callback verisi bulunamadı")
            return
        
        # Security check
        if not self._verify_callback_hash(callback_data):
            transaction._set_error("Güvenlik doğrulaması başarısız")
            return
        
        # Process response
        response_code = callback_data.get('responseCode')
        
        if response_code == '00':
            # Success
            transaction.write({
                'provider_reference': callback_data.get('pgTranId'),
                'paratika_pg_tras_id': callback_data.get('pgTranId'),
                'paratika_pg_order_id': callback_data.get('pgOrderId'),
                'paratika_auth_code': callback_data.get('authCode'),
            })
            transaction._set_done()
        elif response_code in ('07', '12', '51'):
            # Pending/Retry
            transaction._set_pending()
        else:
            # Error
            error_msg = callback_data.get('responseMsg') or callback_data.get('errorMsg') or 'Ödeme reddedildi'
            transaction._set_error(error_msg)
    
    def _send_refund_request(self, transaction):
        """Odoo 19: Process refund request"""
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
                timeout=30,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseCode') == '00':
                return {'status': 'success', 'reference': result.get('pgTranId')}
            else:
                raise ValidationError(f"İade başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Refund error: {e}")
            raise
    
    def _send_capture_request(self, transaction):
        """Odoo 19: Process capture (pre-auth completion)"""
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
                timeout=30,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseCode') == '00':
                transaction._set_done()
            else:
                raise ValidationError(f"Capture başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Capture error: {e}")
            raise
    
    def _send_void_request(self, transaction):
        """Odoo 19: Process void (pre-auth cancellation)"""
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
                timeout=30,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('responseCode') == '00':
                transaction._set_canceled()
            else:
                raise ValidationError(f"Void başarısız: {result.get('responseMsg')}")
                
        except Exception as e:
            _logger.error(f"Void error: {e}")
            raise


# =========================================================================
# CATEGORY INSTALLMENT CONFIGURATION MODEL
# =========================================================================

class ParatikaCategoryInstallment(models.Model):
    """Configuration for category-based installment rules"""
    _name = 'paratika.category.installment'
    _description = 'Paratika Category Installment Configuration'
    _order = 'category_id, sequence'
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Ödeme Sağlayıcı',
        required=True,
        domain="[('code', '=', 'paratika')]",
        ondelete='cascade'
    )
    category_id = fields.Many2one(
        'product.category',
        string='Ürün Kategorisi',
        required=True,
        domain="[('is_product_category', '=', True)]",
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Sıra', default=10)
    
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
    commission_rate = fields.Float(
        string='Komisyon Oranı (%)',
        default=2.0,
        help='Bu kategori için ekstra komisyon oranı'
    )
    bank_specific_rules = fields.Json(
        string='Banka Özel Kuralları',
        help='JSON formatında banka bazlı özel kurallar'
    )
    
    _sql_constraints = [
        ('unique_provider_category', 
         'UNIQUE(provider_id, category_id)', 
         'Aynı sağlayıcı ve kategori kombinasyonu sadece bir kez tanımlanabilir!')
    ]
    
    @api.constrains('allowed_installments')
    def _check_installment_format(self):
        """Validate installment format"""
        for record in self:
            if record.allowed_installments:
                try:
                    installments = [int(x.strip()) for x in record.allowed_installments.split(',') if x.strip()]
                    if not all(1 <= i <= 12 for i in installments):
                        raise ValidationError("Taksit sayıları 1-12 arasında olmalıdır")
                except ValueError:
                    raise ValidationError("Taksit formatı hatalı. Örnek: 1,2,3,6,9,12")