# ========================================================
# ODOO 19 - PAYMENT_PARATIKA MODULE GENERATOR (PowerShell)
# ========================================================

# UTF-8 encoding ayarla
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ModuleDir = "payment_paratika"

# Mevcut dizin kontrolü
if (Test-Path $ModuleDir) {
    Write-Host "[!] Dikkat: $ModuleDir dizini zaten mevcut." -ForegroundColor Yellow
    $response = Read-Host "Yeniden yazilsin mi? (E/H)"
    if ($response -ne 'E' -and $response -ne 'e') {
        Write-Host "[X] Islem iptal edildi." -ForegroundColor Red
        exit
    }
    Remove-Item -Recurse -Force $ModuleDir
}

# Dizin yapısını oluştur
Write-Host "[+] Dizin olusturuluyor: $ModuleDir" -ForegroundColor Green
$dirs = @(
    "models", "controllers", "views", "security", "data",
    "static\description", "migrations\19.0.1.0.0", "tests"
)
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Path (Join-Path $ModuleDir $dir) -Force | Out-Null
}

# Dosya yazma yardımcı fonksiyonu
function New-ModuleFile {
    param([string]$RelativePath, [string]$Content)
    $FullPath = Join-Path $ModuleDir $RelativePath
    [System.IO.File]::WriteAllText($FullPath, $Content, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] $RelativePath olusturuldu" -ForegroundColor Cyan
}

Write-Host "[+] Dosyalar olusturuluyor..." -ForegroundColor Green

# ==================== __manifest__.py ====================
New-ModuleFile "__manifest__.py" @"
{
    'name': 'Paratika Payment Provider',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Paratika Sanal POS - Odoo 19 Uyumlu + Kategori Taksit',
    'description': '''
        Paratika Payment Provider for Odoo 19
        ======================================
        * Flow yonetimi ve durum takibi
        * Kategori bazli taksit kurallari
        * HPP, Direct POST 3D, MOTO destegi
        * SHA512 guvenlik hash
    ''',
    'license': 'LGPL-3',
    'depends': ['payment', 'sale', 'product'],
    'external_dependencies': {'python': ['requests>=2.28.0']},
    'data': [
        'security/ir.model.access.csv',
        'views/payment_paratika_templates.xml',
        'views/payment_provider_views.xml',
        'views/paratika_category_installment_views.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_paratika/static/src/js/paratika_checkout.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'maintainer': 'Reset Bilisim Teknolojileri',
}
"@

# ==================== __init__.py ====================
New-ModuleFile "__init__.py" @"
from . import controllers
from . import models
"@

# ==================== models/__init__.py ====================
New-ModuleFile "models/__init__.py" @"
from . import payment_provider
from . import payment_transaction
from . import paratika_category_installment
"@

# ==================== models/payment_provider.py ====================
New-ModuleFile "models/payment_provider.py" @"
# -*- coding: utf-8 -*-
from odoo import _, api, fields, models, Command
from odoo.exceptions import ValidationError, UserError
import logging
import hashlib
import hmac
import uuid
import requests
from urllib.parse import urljoin, urlencode

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('paratika', 'Paratika')], ondelete={'paratika': 'set default'})

    # Paratika API Credentials
    paratika_merchant_id = fields.Char(string='Merchant ID', required_if_provider='paratika')
    paratika_merchant_user = fields.Char(string='Merchant User', required_if_provider='paratika')
    paratika_merchant_password = fields.Char(string='Merchant Password', password=True, required_if_provider='paratika')
    paratika_secret_key = fields.Char(string='Secret Key', password=True, required_if_provider='paratika')
    paratika_integration_model = fields.Selection([
        ('hpp', 'HPP (Hosted Payment Page)'),
        ('directpost_3d', 'Direct POST 3D Secure'),
        ('directpost_moto', 'Direct POST MOTO'),
    ], string='Entegrasyon Modeli', default='hpp', required_if_provider='paratika')

    # Flow ve Kategori Taksit Ayarlari
    paratika_enable_flow_validation = fields.Boolean(string='Akis Dogrulama Aktif', default=True)
    paratika_default_installment = fields.Selection([
        ('1', 'Tek Cekim'), ('2', '2 Taksit'), ('3', '3 Taksit'), ('4', '4 Taksit'),
        ('5', '5 Taksit'), ('6', '6 Taksit'), ('7', '7 Taksit'), ('8', '8 Taksit'),
        ('9', '9 Taksit'), ('10', '10 Taksit'), ('11', '11 Taksit'), ('12', '12 Taksit'),
    ], string='Varsayilan Taksit', default='1')
    paratika_category_installment_ids = fields.One2many(
        'paratika.category.installment.rule', 'provider_id', string='Kategori Bazli Taksit Kurallari')

    # API URLs
    paratika_api_url_test = fields.Char(string='Test API URL', default='https://test.paratika.com.tr/paratika/api/v2')
    paratika_api_url_prod = fields.Char(string='Production API URL', default='https://www.paratika.com.tr/paratika/api/v2')
    paratika_hpp_url_test = fields.Char(string='Test HPP URL', default='https://test.paratika.com.tr/paratika/hpp/v2')
    paratika_hpp_url_prod = fields.Char(string='Production HPP URL', default='https://www.paratika.com.tr/paratika/hpp/v2')

    @api.constrains('state', 'code')
    def _check_paratika_credentials(self):
        for provider in self.filtered(lambda p: p.code == 'paratika' and p.state != 'draft'):
            if not all([provider.paratika_merchant_id, provider.paratika_merchant_user,
                       provider.paratika_merchant_password, provider.paratika_secret_key]):
                raise ValidationError(_('Paratika entegrasyonu icin tum kimlik bilgileri gereklidir.'))

    def _paratika_get_api_url(self):
        return self.paratika_api_url_test if self.state == 'test' else self.paratika_api_url_prod

    def _paratika_get_hpp_url(self):
        return self.paratika_hpp_url_test if self.state == 'test' else self.paratika_hpp_url_prod

    def _paratika_generate_hash(self, params, secret_key):
        sorted_params = sorted(params.items())
        hash_string = ''.join(f"{k}{v}" for k, v in sorted_params) + secret_key
        return hashlib.sha512(hash_string.encode('utf-8')).hexdigest().upper()

    def _paratika_make_request(self, endpoint, data):
        url = f"{self._paratika_get_api_url()}/{endpoint}" if endpoint else self._paratika_get_api_url()
        data['MERCHANTID'] = self.paratika_merchant_id
        data['MERCHANTUSER'] = self.paratika_merchant_user
        data['MERCHANTPASSWORD'] = self.paratika_merchant_password
        data['HASH'] = self._paratika_generate_hash(data, self.paratika_secret_key)
        try:
            response = requests.post(url, data=data, timeout=30, headers={'User-Agent': 'Odoo/19.0'})
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            _logger.error('Paratika API request failed: %s', e)
            raise ValidationError(_('Baglanti hatasi: %s') % str(e))

    def _get_available_payment_methods(self, **kwargs):
        if self.code != 'paratika':
            return super()._get_available_payment_methods(**kwargs)
        return [{
            'id': 'paratika_card',
            'name': 'Kredi / Banka Karti',
            'image': '/payment_paratika/static/description/paratika_logo.png',
        }]
"@

# ==================== models/payment_transaction.py ====================
New-ModuleFile "models/payment_transaction.py" @"
# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
import logging
import uuid
import json
from urllib.parse import urljoin

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    paratika_session_token = fields.Char(string='Session Token', readonly=True)
    paratika_payment_id = fields.Char(string='Paratika Payment ID', readonly=True)
    paratika_flow_state = fields.Selection([
        ('init', 'Baslatildi'), ('session_created', 'Oturum Olusturuldu'),
        ('redirected', 'Yonlendirildi'), ('3ds_pending', '3D Secure Beklemede'),
        ('processing', 'Isleniyor'), ('done', 'Tamamlandi'),
        ('error', 'Hata'), ('cancelled', 'Iptal Edildi'),
    ], string='Paratika Akis Durumu', default='init', readonly=True)
    paratika_category_applied = fields.Char(string='Uygulanan Kategori Kodu', readonly=True)

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'paratika':
            return res

        if self.provider_id.paratika_enable_flow_validation:
            self._validate_payment_flow()

        installment_data = self._get_category_based_installments()
        merchant_payment_id = f'ODOO-{self.id}-{uuid.uuid4().hex[:8]}'
        base_url = self.provider_id.get_base_url()
        return_url = urljoin(base_url, '/payment/paratika/return')

        session_data = {
            'ACTION': 'SESSIONTOKEN',
            'SESSIONTYPE': 'PAYMENTSESSION',
            'MERCHANTPAYMENTID': merchant_payment_id,
            'AMOUNT': f'{self.amount:.2f}',
            'CURRENCY': self.currency_id.name,
            'RETURNURL': return_url,
            'CUSTOMER': f'customer-{self.partner_id.id}',
            'CUSTOMERNAME': self.partner_name or 'Customer',
            'CUSTOMEREMAIL': self.partner_email or 'noemail@example.com',
            'CUSTOMERIP': self.partner_address or '127.0.0.1',
            'CUSTOMERUSERAGENT': 'Odoo/19.0',
            'INSTALLMENTS': installment_data.get('installment_count', '1'),
            'CATEGORYCODE': installment_data.get('category_code', ''),
        }

        if self.sale_order_ids:
            order_items = []
            for order in self.sale_order_ids:
                for line in order.order_line:
                    category_rule = line.product_id.categ_id._get_paratika_installment_rule(self.provider_id)
                    order_items.append({
                        'code': line.product_id.default_code or str(line.id),
                        'name': line.name[:50],
                        'quantity': int(line.product_uom_qty),
                        'amount': float(line.price_unit),
                        'category': line.product_id.categ_id.name,
                        'categoryCode': category_rule.paratika_category_code if category_rule else '',
                    })
            if order_items:
                session_data['ORDERITEMS'] = json.dumps(order_items, ensure_ascii=False)

        try:
            response = self.provider_id._paratika_make_request('', session_data)
            if response.get('responseCode') == '00':
                session_token = response.get('sessionToken')
                self.paratika_session_token = session_token
                self.paratika_flow_state = 'session_created'

                if self.provider_id.paratika_integration_model == 'hpp':
                    api_url = f"{self.provider_id._paratika_get_hpp_url()}/{session_token}"
                elif self.provider_id.paratika_integration_model == 'directpost_3d':
                    api_url = f"{self.provider_id._paratika_get_api_url()}/post/sale3d/{session_token}"
                    self.paratika_flow_state = '3ds_pending'
                else:
                    api_url = f"{self.provider_id._paratika_get_api_url()}/merchant/post/sale/{session_token}"

                return {'api_url': api_url, 'installment_options': installment_data}
            else:
                self.paratika_flow_state = 'error'
                raise ValidationError(_('Paratika hata: %s') % response.get('responseMsg', 'Bilinmeyen hata'))
        except Exception as e:
            self.paratika_flow_state = 'error'
            _logger.exception('Paratika rendering error')
            raise ValidationError(_('Odeme baslatilamadi: %s') % str(e))

    def _validate_payment_flow(self):
        if not self.partner_id.email:
            raise ValidationError(_('Musteri e-posta adresi zorunludur.'))
        if self.amount <= 0:
            raise ValidationError(_('Gecersiz odeme tutari.'))
        return True

    def _get_category_based_installments(self):
        result = {'installment_count': '1', 'category_code': ''}
        if not self.sale_order_ids:
            return result
        max_priority = -1
        selected_rule = None
        for order in self.sale_order_ids:
            for line in order.order_line:
                category = line.product_id.categ_id
                rule = category._get_paratika_installment_rule(self.provider_id)
                if rule and rule.priority > max_priority:
                    max_priority = rule.priority
                    selected_rule = rule
        if selected_rule:
            result.update({
                'installment_count': str(selected_rule.max_installment_count),
                'category_code': selected_rule.paratika_category_code,
                'allowed_installments': selected_rule._get_allowed_installment_list(),
            })
            self.paratika_category_applied = selected_rule.paratika_category_code
        return result

    def _handle_feedback_data(self, feedback_data):
        if self.provider_code != 'paratika':
            return super()._handle_feedback_data(feedback_data)

        response_code = feedback_data.get('responseCode')
        if response_code == '00':
            self.paratika_flow_state = 'done'
            self.paratika_payment_id = feedback_data.get('paymentId')
            return {'status': 'done', 'reference': feedback_data.get('merchantPaymentId')}
        elif response_code in ('E01', 'E02', 'CANCEL'):
            self.paratika_flow_state = 'cancelled'
            return {'status': 'cancel'}
        else:
            self.paratika_flow_state = 'error'
            return {'status': 'error', 'error_message': feedback_data.get('responseMsg')}

    def _process_feedback_data(self, feedback_data):
        result = self._handle_feedback_data(feedback_data)
        if result.get('status') == 'done':
            self._set_done()
        elif result.get('status') == 'cancel':
            self._set_cancelled()
        elif result.get('status') == 'error':
            self._set_error(result.get('error_message'))
        return self
"@

# ==================== models/paratika_category_installment.py ====================
New-ModuleFile "models/paratika_category_installment.py" @"
# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    paratika_installment_rule_ids = fields.One2many(
        'paratika.category.installment.rule', 'category_id', string='Paratika Taksit Kurallari')

    def _get_paratika_installment_rule(self, provider):
        self.ensure_one()
        rule = self.paratika_installment_rule_ids.filtered(
            lambda r: r.provider_id == provider and r.active)
        return rule[:1]


class ParatikaCategoryInstallmentRule(models.Model):
    _name = 'paratika.category.installment.rule'
    _description = 'Paratika Kategori Bazli Taksit Kurali'
    _order = 'priority desc, id'

    provider_id = fields.Many2one('payment.provider', string='Odeme Saglayici', required=True,
        domain=[('code', '=', 'paratika')])
    category_id = fields.Many2one('product.category', string='Urun Kategorisi', required=True)
    paratika_category_code = fields.Char(string='Paratika Kategori Kodu', size=64,
        help='Paratika API\'de kullanilacak kategori kodu')
    max_installment_count = fields.Selection([
        ('1', 'Tek Cekim'), ('2', '2 Taksit'), ('3', '3 Taksit'), ('4', '4 Taksit'),
        ('5', '5 Taksit'), ('6', '6 Taksit'), ('7', '7 Taksit'), ('8', '8 Taksit'),
        ('9', '9 Taksit'), ('10', '10 Taksit'), ('11', '11 Taksit'), ('12', '12 Taksit'),
    ], string='Maksimum Taksit', default='1', required=True)
    allowed_installments = fields.Char(string='Izin Verilen Taksitler',
        help='Virgulle ayrilmis taksit sayilari, orn: "1,3,6,9"')
    priority = fields.Integer(string='Oncelik', default=10)
    active = fields.Boolean(string='Aktif', default=True)

    @api.constrains('allowed_installments')
    def _check_allowed_installments(self):
        for rule in self:
            if rule.allowed_installments:
                try:
                    installments = [int(i.strip()) for i in rule.allowed_installments.split(',')]
                    if not all(1 <= i <= 12 for i in installments):
                        raise ValidationError(_('Taksit sayilari 1-12 araliginda olmalidir.'))
                except ValueError:
                    raise ValidationError(_('Gecersiz taksit formati. Ornek: "1,3,6,9"'))

    def _get_allowed_installment_list(self):
        if self.allowed_installments:
            return [int(i.strip()) for i in self.allowed_installments.split(',')]
        return list(range(1, int(self.max_installment_count) + 1))
"@

# ==================== controllers/__init__.py ====================
New-ModuleFile "controllers/__init__.py" @"
from . import main
"@

# ==================== controllers/main.py ====================
New-ModuleFile "controllers/main.py" @"
# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ParatikaController(http.Controller):

    @http.route('/payment/paratika/return', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def paratika_return_from_redirect(self, **data):
        _logger.info('Paratika return callback received: %s', {k:v for k,v in data.items() if k != 'sdSha512'})

        if not data.get('merchantPaymentId'):
            return request.redirect('/payment/status')

        tx = request.env['payment.transaction'].sudo().search([
            ('provider_code', '=', 'paratika'),
            ('reference', '=', data.get('merchantPaymentId'))
        ], limit=1)

        if not tx:
            _logger.warning('Transaction not found for merchantPaymentId: %s', data.get('merchantPaymentId'))
            return request.redirect('/payment/status')

        try:
            tx._process_feedback_data(data)
            if tx.state == 'done':
                return request.redirect(tx._get_return_url())
            elif tx.state == 'cancel':
                return request.redirect('/payment/cancel')
            else:
                return request.redirect('/payment/error')
        except Exception as e:
            _logger.exception('Error processing Paratika callback')
            return request.redirect('/payment/error')

    @http.route('/payment/paratika/webhook', type='json', auth='public', csrf=False)
    def paratika_webhook(self, **data):
        _logger.info('Paratika webhook received')
        if not data.get('merchantPaymentId'):
            return {'status': 'error', 'message': 'Missing merchantPaymentId'}
        try:
            tx = request.env['payment.transaction'].sudo().search([
                ('provider_code', '=', 'paratika'),
                ('reference', '=', data.get('merchantPaymentId'))
            ], limit=1)
            if tx:
                tx._process_feedback_data(data)
            return {'status': 'success'}
        except Exception as e:
            _logger.exception('Webhook processing error')
            return {'status': 'error', 'message': str(e)}
"@

# ==================== views/payment_provider_views.xml ====================
New-ModuleFile "views/payment_provider_views.xml" @"
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_provider_form_paratika" model="ir.ui.view">
        <field name="name">payment.provider.form.paratika</field>
        <field name="model">payment.provider</field>
        <field name="inherit_id" ref="payment.payment_provider_form"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='credentials']" position="after">
                <page string="Paratika Ayarlari" name="paratika_config" attrs="{'invisible': [('code', '!=', 'paratika')]} ">
                    <group string="API Kimlik Bilgileri">
                        <field name="paratika_merchant_id"/>
                        <field name="paratika_merchant_user"/>
                        <field name="paratika_merchant_password"/>
                        <field name="paratika_secret_key"/>
                    </group>
                    <group string="Entegrasyon">
                        <field name="paratika_integration_model"/>
                        <field name="paratika_enable_flow_validation"/>
                        <field name="paratika_default_installment"/>
                    </group>
                    <group string="API URL'leri">
                        <field name="paratika_api_url_test"/>
                        <field name="paratika_api_url_prod"/>
                        <field name="paratika_hpp_url_test"/>
                        <field name="paratika_hpp_url_prod"/>
                    </group>
                </page>
            </xpath>
        </field>
    </record>
</odoo>
"@

# ==================== views/paratika_category_installment_views.xml ====================
New-ModuleFile "views/paratika_category_installment_views.xml" @"
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_category_form_paratika" model="ir.ui.view">
        <field name="name">product.category.form.paratika</field>
        <field name="model">product.category</field>
        <field name="inherit_id" ref="product.product_category_form_view"/>
        <field name="arch" type="xml">
            <notebook position="inside">
                <page string="Paratika Taksit" name="paratika_installments">
                    <field name="paratika_installment_rule_ids">
                        <tree editable="bottom">
                            <field name="provider_id" options="{'no_create': True}"/>
                            <field name="paratika_category_code"/>
                            <field name="max_installment_count"/>
                            <field name="allowed_installments" widget="text"/>
                            <field name="priority" widget="integer"/>
                            <field name="active" widget="boolean_toggle"/>
                        </tree>
                    </field>
                </page>
            </notebook>
        </field>
    </record>

    <record id="view_provider_form_category_installments" model="ir.ui.view">
        <field name="name">payment.provider.form.category.installments</field>
        <field name="model">payment.provider</field>
        <field name="inherit_id" ref="payment.payment_provider_form"/>
        <field name="arch" type="xml">
            <xpath expr="//sheet/notebook" position="inside">
                <page string="Kategori Taksitleri" name="category_installments"
                        attrs="{'invisible': [('code', '!=', 'paratika')]} ">
                    <field name="paratika_category_installment_ids">
                        <tree editable="bottom">
                            <field name="category_id"/>
                            <field name="paratika_category_code"/>
                            <field name="max_installment_count"/>
                            <field name="allowed_installments"/>
                            <field name="priority"/>
                            <field name="active" widget="boolean_toggle"/>
                        </tree>
                    </field>
                </page>
            </xpath>
        </field>
    </record>
</odoo>
"@

# ==================== views/payment_paratika_templates.xml ====================
New-ModuleFile "views/payment_paratika_templates.xml" @"
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="paratika_checkout" name="Paratika Checkout">
        <t t-name="payment_paratika.checkout">
            <div class="paratika-checkout" t-att-data-installments="installment_options.get('allowed_installments', [1])">
                <input type="hidden" name="paratika_session_token" t-att-value="api_url.split('/')[-1] if api_url else ''"/>
                <div class="installment-selector" t-if="installment_options.get('allowed_installments')">
                    <label for="installment_count">Taksit Secimi:</label>
                    <select name="installment_count" id="installment_count" class="form-control">
                        <t t-foreach="installment_options['allowed_installments']" t-as="inst">
                            <option t-att-value="inst">
                                <t t-if="inst == 1">Tek Cekim</t>
                                <t t-else=""><t t-esc="inst"/> Taksit</t>
                            </option>
                        </t>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary">Odemeyi Tamamla</button>
            </div>
        </t>
    </template>
</odoo>
"@

# ==================== security/ir.model.access.csv ====================
New-ModuleFile "security/ir.model.access.csv" @"
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_paratika_category_installment_rule,paratika.category.installment.rule,model_paratika_category_installment_rule,base.group_user,1,1,1,0
"@

# ==================== data/payment_provider_data.xml ====================
New-ModuleFile "data/payment_provider_data.xml" @"
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="payment_provider_paratika" model="payment.provider">
        <field name="name">Paratika</field>
        <field name="code">paratika</field>
        <field name="module_id" ref="base.module_payment_paratika"/>
        <field name="state">disabled</field>
        <field name="sequence">100</field>
    </record>
</odoo>
"@

# ==================== static/description/index.html ====================
New-ModuleFile "static/description/index.html" @"
<?xml version="1.0" encoding="utf-8"?>
<section class="oe_container">
    <div class="oe_row oe_spaced">
        <h2 class="oe_slogan">Paratika Payment Provider - Odoo 19</h2>
        <p class="oe_mt32">Paratika Sanal POS entegrasyonu: Flow yonetimi, kategori bazli taksit, 3D Secure destegi.</p>
    </div>
</section>
"@

# ==================== migrations/19.0.1.0.0/pre-migration.py ====================
New-ModuleFile "migrations/19.0.1.0.0/pre-migration.py" @"
# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""
        ALTER TABLE payment_provider
        ADD COLUMN IF NOT EXISTS paratika_enable_flow_validation BOOLEAN DEFAULT TRUE
    """)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS paratika_category_installment_rule (
            id SERIAL PRIMARY KEY,
            provider_id INTEGER REFERENCES payment_provider(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES product_category(id) ON DELETE CASCADE,
            paratika_category_code VARCHAR(64),
            max_installment_count VARCHAR(2) DEFAULT '1',
            allowed_installments VARCHAR(128),
            priority INTEGER DEFAULT 10,
            active BOOLEAN DEFAULT TRUE,
            create_uid INTEGER REFERENCES res_users(id),
            create_date TIMESTAMP,
            write_uid INTEGER REFERENCES res_users(id),
            write_date TIMESTAMP
        )
    """)
"@

# ==================== tests/__init__.py ====================
New-ModuleFile "tests/__init__.py" @"
from . import test_paratika_category_installment
"@

# ==================== tests/test_paratika_category_installment.py ====================
New-ModuleFile "tests/test_paratika_category_installment.py" @"
# -*- coding: utf-8 -*-
from odoo.tests import common, tagged
from odoo.exceptions import ValidationError

@tagged('-at_install', 'post_install')
class TestParatikaCategoryInstallment(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.provider = self.env['payment.provider'].create({
            'name': 'Paratika Test', 'code': 'paratika',
            'paratika_merchant_user': 'test_user', 'paratika_merchant_password': 'test_pass',
            'paratika_merchant_id': '10000000', 'paratika_secret_key': 'test_secret', 'state': 'test',
        })
        self.cat_electronics = self.env['product.category'].create({'name': 'Elektronik'})
        self.rule = self.env['paratika.category.installment.rule'].create({
            'provider_id': self.provider.id, 'category_id': self.cat_electronics.id,
            'paratika_category_code': 'ELEC001', 'max_installment_count': '6',
            'allowed_installments': '1,3,6', 'priority': 20,
        })

    def test_category_installment_rule_retrieval(self):
        rule = self.cat_electronics._get_paratika_installment_rule(self.provider)
        self.assertEqual(rule, self.rule)
        self.assertEqual(rule.max_installment_count, '6')

    def test_allowed_installments_parsing(self):
        installments = self.rule._get_allowed_installment_list()
        self.assertEqual(installments, [1, 3, 6])

    def test_installment_validation(self):
        with self.assertRaisesRegex(ValidationError, '1-12 araliginda'):
            self.env['paratika.category.installment.rule'].create({
                'provider_id': self.provider.id, 'category_id': self.cat_electronics.id,
                'allowed_installments': '1,15,20',
            })
"@

# ==================== README.md ====================
New-ModuleFile "README.md" @"
# payment_paratika - Odoo 19

Paratika Sanal POS entegrasyon modulu.

## Ozellikler
- Odoo 19.0 uyumlulugu
- Flow yonetimi ve durum takibi
- Kategori bazli taksit kurallari
- HPP, Direct POST 3D, MOTO destegi
- SHA512 hash guvenligi

## Kurulum
1. Modulu `odoo/addons` dizinine kopyalayin
2. Odoo'yu `-u payment_paratika` ile guncelleyin
3. Ayarlar > Odeme Saglayicilari'ndan Paratika'yi yapilandirin

## Kategori Taksit Ayari
Urunler > Konfigurasyon > Urun Kategorileri > [Kategori] > Paratika Taksit

## API Parametreleri
| Parametre | Aciklama |
|-----------|----------|
| INSTALLMENTS | Taksit sayisi (1-12) |
| CATEGORYCODE | Kategori kodu |
| ORDERITEMS | Urun listesi (JSON) |

> Not: Kategori kodlari Paratika panelinde tanimli olmalidir.
"@

# Bitiş mesajı
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "[+] Modul basariyla olusturuldu: $ModuleDir" -ForegroundColor Green
Write-Host "[+] Tum dosyalar UTF-8 encoding ile yazildi." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Kullanim:" -ForegroundColor Yellow
Write-Host "  1. payment_paratika klasorunu odoo/addons icine kopyalayin"
Write-Host "  2. Odoo'yu su parametrelerle baslatin:"
Write-Host "     odoo-bin -c odoo.conf -u payment_paratika --stop-after-init"
Write-Host "  3. Ayarlar > Odeme Saglayicilari > Paratika'yi yapilandirin"
Write-Host "========================================================"
pause