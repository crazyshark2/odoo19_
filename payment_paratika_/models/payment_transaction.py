# -*- coding: utf-8 -*-
"""
Paratika Payment Transaction Model for Odoo 19
"""
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    
    # =========================================================================
    # PARATIKA SPECIFIC FIELDS
    # =========================================================================
    
    # Session & Reference
    paratika_session_token = fields.Char(
        string='Session Token',
        readonly=True,
        copy=False,
    )
    paratika_pg_tras_id = fields.Char(
        string='PG Transaction ID',
        readonly=True,
        copy=False,
        index=True,
    )
    paratika_pg_order_id = fields.Char(
        string='PG Order ID',
        readonly=True,
        copy=False,
    )
    paratika_auth_code = fields.Char(
        string='Authorization Code',
        readonly=True,
        copy=False,
    )
    paratika_host_ref_num = fields.Char(
        string='Host Reference Number',
        readonly=True,
        copy=False,
    )
    
    # Card Information (masked)
    paratika_card_mask = fields.Char(
        string='Card Number (Masked)',
        readonly=True,
        copy=False,
    )
    paratika_card_type = fields.Selection(
        selection=[
            ('credit', 'Kredi Kartı'),
            ('debit', 'Banka Kartı'),
        ],
        string='Kart Tipi',
        readonly=True,
    )
    
    # Callback Data
    paratika_callback_data = fields.Json(
        string='Callback Data',
        readonly=True,
        copy=False,
    )
    paratika_callback_date = fields.Datetime(
        string='Callback Date',
        readonly=True,
        copy=False,
    )
    
    # Category & Installment Info
    paratika_installment_count = fields.Integer(
        string='Taksit Sayısı',
        default=1,
        help='Müşterinin seçtiği taksit sayısı'
    )
    paratika_selected_bank = fields.Char(
        string='Seçilen Banka',
        help='Müşterinin seçtiği ödeme sistemi/banka kodu'
    )
    paratika_category_ids = fields.Many2many(
        'product.category',
        string='İlgili Kategoriler',
        compute='_compute_category_ids',
        store=False,
    )
    
    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================
    
    @api.depends('sale_order_ids', 'order_id')
    def _compute_category_ids(self):
        """Compute product categories from related sale order"""
        for tx in self:
            categories = self.env['product.category']
            
            if tx.sale_order_ids:
                categories = tx.sale_order_ids[0].order_line.mapped('product_id.categ_id')
            elif tx.order_id:
                categories = tx.order_id.order_line.mapped('product_id.categ_id')
            
            # Include parent categories
            categories |= categories.mapped('parent_id')
            tx.paratika_category_ids = categories
    
    # =========================================================================
    # ODOO 19: PROCESSING OVERRIDES
    # =========================================================================
    
    def _get_specific_processing_values(self, processing_values):
        """Odoo 19: Get provider-specific processing values"""
        res = super()._get_specific_processing_values(processing_values)
        
        if self.provider_id.code != 'paratika':
            return res
        
        # Validate installment count against category rules
        if self.provider_id.paratika_enable_category_installments:
            allowed = self.provider_id._get_category_installment_options(self)
            
            if self.paratika_installment_count:
                count_str = str(self.paratika_installment_count)
                if count_str not in allowed:
                    # Auto-correct to default
                    self.paratika_installment_count = int(
                        self.provider_id._get_category_default_installment(self)
                    )
        
        return res
    
    def _compute_reference_prefix(self, separator, **values):
        """Odoo 19: Compute reference prefix"""
        if self.provider_id.code == 'paratika':
            prefix = f"PAR{self.provider_id.paratika_merchant_id or 'TEST'}"
            if values.get('sale_order_ids'):
                so = self.env['sale.order'].browse(values['sale_order_ids'][0])
                prefix = f"{prefix}{separator}{so.name}"
            return prefix
        return super()._compute_reference_prefix(separator, **values)
    
    # =========================================================================
    # PAYMENT PROCESSING
    # =========================================================================
    
    def _process(self, provider_code, payment_data):
        """Process payment data from provider callback"""
        
        if provider_code != 'paratika':
            return super()._process(provider_code, payment_data)
        
        self.ensure_one()
        
        # Store callback data
        self.paratika_callback_data = payment_data
        self.paratika_callback_date = fields.Datetime.now()
        
        # Extract and update amount/currency
        amount_data = self._extract_amount_data(payment_data)
        if amount_data:
            self.amount = amount_data['amount']
            if amount_data['currency_code']:
                currency = self.env['res.currency'].search(
                    [('name', '=', amount_data['currency_code'])], limit=1)
                if currency:
                    self.currency_id = currency
        
        # Extract reference
        reference = self._extract_reference(provider_code, payment_data)
        if reference:
            self.provider_reference = reference
        
        # Update card info if present
        if payment_data.get('cardMask'):
            self.paratika_card_mask = payment_data['cardMask']
        if payment_data.get('cardType'):
            self.paratika_card_type = 'credit' if payment_data['cardType'] == 'Credit' else 'debit'
        
        # Update state based on response
        response_code = payment_data.get('responseCode')
        response_msg = payment_data.get('responseMsg', '')
        
        if response_code == '00':
            self._set_done()
        elif response_code in ('07', '12', '51', '61'):
            self._set_pending()
        else:
            self._set_error(response_msg or _("Ödeme reddedildi"))
        
        return self
    
    def _extract_amount_data(self, payment_data):
        """Extract amount and currency from payment data"""
        try:
            amount = float(payment_data.get('amount', 0))
            currency = payment_data.get('currency', 'TRY')
            return {
                'amount': amount,
                'currency_code': currency,
                'precision_digits': 2,
            }
        except (ValueError, TypeError):
            _logger.warning(f"Could not extract amount from: {payment_data}")
            return None
    
    def _extract_reference(self, provider_code, payment_data):
        """Extract transaction reference from payment data"""
        return payment_data.get('pgTranId') or payment_data.get('merchantPaymentId')
    
    def _extract_token_values(self, payment_data):
        """Extract values for payment token creation"""
        if not payment_data.get('cardToken'):
            return {}
        
        return {
            'payment_provider_id': self.provider_id.id,
            'partner_id': self.partner_id.id,
            'token': payment_data['cardToken'],
            'card_type': payment_data.get('cardType', 'credit').lower(),
            'card_brand': payment_data.get('cardBrand', ''),
            'card_number': payment_data.get('cardMask', ''),
            'expiry_date': f"{payment_data.get('expiryMonth', '')}/{payment_data.get('expiryYear', '')}",
        }
    
    # =========================================================================
    # REFUND & CAPTURE SUPPORT
    # =========================================================================
    
    def _send_refund_request(self):
        """Send refund request to Paratika"""
        self.ensure_one()
        return self.provider_id._send_refund_request(self)
    
    def _send_capture_request(self):
        """Send capture request for pre-authorized payment"""
        self.ensure_one()
        return self.provider_id._send_capture_request(self)
    
    def _send_void_request(self):
        """Send void request to cancel pre-authorization"""
        self.ensure_one()
        return self.provider_id._send_void_request(self)