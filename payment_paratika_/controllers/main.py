# -*- coding: utf-8 -*-
"""
Paratika Payment Controller for Odoo 19
Handles callbacks, category-based filtering, and AJAX endpoints
"""
import logging
import json
import hashlib
import hmac
from datetime import datetime

from werkzeug.exceptions import BadRequest, Forbidden
from werkzeug.urls import url_join

from odoo import http, _
from odoo.http import request, Response, content_disposition
from odoo.addons.payment.controllers.main import PaymentController
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class ParatikaPaymentController(PaymentController):
    
    @http.route([
        '/payment/paratika/callback',
        '/payment/paratika/return',
        '/payment/paratika/notify',
    ], type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def paratika_callback(self, **post):
        """
        Paratika payment callback handler
        Processes payment results and updates transaction state
        """
        _logger.info(f"Paratika callback received: {post.get('merchantPaymentId', 'N/A')}")
        
        if not post:
            _logger.warning("Empty callback received")
            return self._redirect_to_cart()
        
        # Find provider
        provider = request.env['payment.provider'].sudo().search(
            [('code', '=', 'paratika'), ('state', 'in', ['enabled', 'test'])], 
            limit=1
        )
        
        if not provider:
            _logger.error("Active Paratika provider not found")
            return self._redirect_to_cart()
        
        # Security: Verify SHA512 hash
        if not provider._verify_callback_hash(post):
            _logger.warning(f"Invalid hash for transaction: {post.get('merchantPaymentId')}")
            return Response(
                json.dumps({'status': 'error', 'message': 'Invalid security hash'}),
                mimetype='application/json',
                status=400
            )
        
        # Find transaction
        reference = post.get('merchantPaymentId') or post.get('pgOrderId')
        if not reference:
            _logger.error("No reference found in callback")
            return self._redirect_to_cart()
        
        transaction = request.env['payment.transaction'].sudo().search(
            [('reference', '=', reference), ('provider_id.code', '=', 'paratika')], 
            limit=1
        )
        
        if not transaction:
            _logger.error(f"Transaction not found: {reference}")
            return self._redirect_to_cart()
        
        # Store callback data for audit
        transaction.write({
            'paratika_callback_data': post,
            'paratika_callback_date': fields.Datetime.now(),
        })
        
        # Process payment result
        try:
            self._process_callback_result(provider, transaction, post)
        except Exception as e:
            _logger.error(f"Error processing callback: {e}", exc_info=True)
            transaction._set_error(_("Ödeme işlenirken bir hata oluştu"))
            return self._redirect_to_checkout(transaction, error=_("Ödeme tamamlanamadı"))
        
        # Redirect based on result
        return self._handle_callback_redirect(transaction, post)
    
    def _process_callback_result(self, provider, transaction, callback_data):
        """Process the callback result and update transaction"""
        
        response_code = callback_data.get('responseCode')
        response_msg = callback_data.get('responseMsg', '')
        
        # Extract payment details
        pg_tras_id = callback_data.get('pgTranId')
        pg_order_id = callback_data.get('pgOrderId')
        auth_code = callback_data.get('authCode')
        host_ref_num = callback_data.get('hostRefNum')
        
        # Update transaction with Paratika references
        update_vals = {
            'provider_reference': pg_tras_id or pg_order_id,
            'paratika_pg_tras_id': pg_tras_id,
            'paratika_pg_order_id': pg_order_id,
            'paratika_auth_code': auth_code,
            'paratika_host_ref_num': host_ref_num,
        }
        
        if callback_data.get('cardMask'):
            update_vals['paratika_card_mask'] = callback_data['cardMask']
        if callback_data.get('cardType'):
            update_vals['paratika_card_type'] = callback_data['cardType']
        
        # Handle different response codes
        if response_code == '00':
            # Success
            update_vals['state'] = 'done'
            transaction.write(update_vals)
            transaction._set_done()
            
        elif response_code in ('07', '12', '51', '61', '62', '65'):
            # Soft decline - can be retried
            update_vals['state'] = 'pending'
            transaction.write(update_vals)
            transaction._set_pending()
            
        elif response_code in ('05', '14', '41', '43', '54', '57', '63', '91'):
            # Hard decline
            update_vals['state'] = 'error'
            transaction.write(update_vals)
            transaction._set_error(response_msg or _("Ödeme reddedildi"))
            
        elif response_code in ('98', '99'):
            # System error
            update_vals['state'] = 'error'
            transaction.write(update_vals)
            transaction._set_error(_("Sistem hatası: ") + (response_msg or "Bilinmeyen hata"))
            
        else:
            # Unknown status
            _logger.warning(f"Unknown response code {response_code}: {response_msg}")
            transaction.write(update_vals)
    
    def _handle_callback_redirect(self, transaction, callback_data):
        """Handle redirect after callback processing"""
        
        if transaction.state == 'done':
            # Success redirect
            if transaction.sale_order_ids:
                sale_order = transaction.sale_order_ids[0]
                return request.redirect(f'/shop/confirmation/{sale_order.id}')
            return request.redirect('/shop/checkout/status?status=success')
        else:
            # Error redirect
            error_msg = callback_data.get('responseMsg') or callback_data.get('errorMsg')
            if not error_msg:
                error_msg = _("Ödeme işlemi tamamlanamadı")
            return request.redirect(f'/shop/checkout?error={request.url_encode(error_msg)}')
    
    def _redirect_to_cart(self):
        """Redirect to shopping cart"""
        return request.redirect('/shop/cart')
    
    def _redirect_to_checkout(self, transaction, error=None):
        """Redirect to checkout with optional error"""
        url = '/shop/checkout'
        if error:
            url += f'?error={request.url_encode(error)}'
        return request.redirect(url)
    
    # ========================================================================
    # CATEGORY-BASED PAYMENT METHODS API
    # ========================================================================
    
    @http.route('/payment/paratika/category_methods', type='json', auth='public', website=True)
    def get_category_payment_methods(self, sale_order_id=None, category_ids=None, **kwargs):
        """
        Get payment methods filtered by product categories
        AJAX endpoint for dynamic payment method display
        """
        _logger.debug(f"Getting category methods for SO:{sale_order_id}, Categories:{category_ids}")
        
        methods = []
        
        try:
            if sale_order_id:
                sale_order = request.env['sale.order'].sudo().browse(int(sale_order_id))
                if not sale_order.exists():
                    return {'payment_methods': [], 'error': 'Invalid sale order'}
                
                # Get compatible providers with category filtering
                providers = request.env['payment.provider'].sudo()._get_compatible_providers(
                    company_id=sale_order.company_id.id,
                    partner_id=sale_order.partner_id.id,
                    amount=sale_order.amount_total,
                    currency_id=sale_order.currency_id.id,
                    sale_order_id=sale_order.id,
                )
                
                # Filter Paratika providers and build response
                for provider in providers.filtered(lambda p: p.code == 'paratika'):
                    method_data = self._build_payment_method_data(provider, sale_order)
                    methods.append(method_data)
                    
            elif category_ids:
                # Direct category query (for cart preview)
                categories = request.env['product.category'].sudo().browse(category_ids)
                methods = self._get_methods_for_categories(categories)
                
        except Exception as e:
            _logger.error(f"Error in category_methods: {e}", exc_info=True)
            return {'payment_methods': [], 'error': str(e)}
        
        return {'payment_methods': methods}
    
    def _build_payment_method_data(self, provider, sale_order):
        """Build payment method data structure for frontend"""
        
        # Get category-based installment options
        installments = []
        default_installment = '1'
        
        if provider.paratika_enable_category_installments:
            # Create temp transaction for context
            temp_tx = request.env['payment.transaction'].new({
                'sale_order_ids': [(4, sale_order.id)],
                'provider_id': provider.id,
                'amount': sale_order.amount_total,
                'currency_id': sale_order.currency_id.id,
            })
            installments = provider._get_category_installment_options(temp_tx)
            
            # Get default installment from category config
            for line in sale_order.order_line:
                cat_config = provider.paratika_category_installment_ids.filtered(
                    lambda c: c.category_id == line.product_id.categ_id
                )
                if cat_config and cat_config.default_installment:
                    default_installment = cat_config.default_installment
                    break
        
        return {
            'id': provider.id,
            'name': provider.name,
            'code': provider.code,
            'image_128': provider.image_128,
            'description': provider.description or '',
            'installments': installments,
            'default_installment': default_installment,
            'supports_tokenization': provider.support_tokenization,
            'supports_manual_capture': provider.support_manual_capture,
            'category_restriction': provider.paratika_category_restriction,
        }
    
    def _get_methods_for_categories(self, categories):
        """Get payment methods for given categories"""
        methods = []
        providers = request.env['payment.provider'].sudo().search(
            [('code', '=', 'paratika'), ('state', 'in', ['enabled', 'test'])]
        )
        
        for provider in providers:
            if provider._check_category_compatibility(categories):
                methods.append({
                    'id': provider.id,
                    'name': provider.name,
                    'code': provider.code,
                })
        
        return methods
    
    # ========================================================================
    # INSTALLMENT CALCULATION API
    # ========================================================================
    
    @http.route('/payment/paratika/calculate_installment', type='json', auth='public')
    def calculate_installment(self, amount, installment_count, category_ids=None, **kwargs):
        """
        Calculate installment amounts with category-based commissions
        Returns detailed breakdown for display
        """
        try:
            amount = float(amount)
            installment_count = int(installment_count)
        except (ValueError, TypeError) as e:
            return {'error': f'Invalid parameters: {e}'}
        
        # Get category-based commission rate
        commission_rate = 0.0
        category_surcharge = 0.0
        
        if category_ids:
            categories = request.env['product.category'].sudo().browse(category_ids)
            commission_rate, category_surcharge = self._get_category_commission_rates(categories)
        
        # Calculate base amounts
        base_amount = amount
        commission = base_amount * commission_rate
        surcharge = base_amount * category_surcharge
        
        total_with_fees = base_amount + commission + surcharge
        
        # Calculate per-installment amount
        if installment_count <= 1:
            # Single payment - no interest
            per_installment = total_with_fees
            total_interest = 0.0
        else:
            # Installment payment - apply interest based on category
            interest_rate = self._get_installment_interest_rate(installment_count, category_ids)
            total_interest = total_with_fees * interest_rate
            total_with_interest = total_with_fees + total_interest
            per_installment = total_with_interest / installment_count
        
        return {
            'success': True,
            'calculation': {
                'original_amount': round(base_amount, 2),
                'commission': round(commission, 2),
                'commission_rate': commission_rate * 100,
                'category_surcharge': round(surcharge, 2),
                'category_surcharge_rate': category_surcharge * 100,
                'subtotal_with_fees': round(total_with_fees, 2),
                'installment_count': installment_count,
                'interest_rate': interest_rate * 100 if installment_count > 1 else 0,
                'total_interest': round(total_interest, 2),
                'total_amount': round(total_with_fees + total_interest, 2),
                'per_installment': round(per_installment, 2),
                'currency': request.env.user.company_id.currency_id.name,
            }
        }
    
    def _get_category_commission_rates(self, categories):
        """Get commission rates based on product categories"""
        base_rate = 0.020  # Default 2%
        surcharge = 0.0
        
        for category in categories:
            cat_name = category.name.lower()
            
            # Electronics: higher commission
            if any(kw in cat_name for kw in ['elektronik', 'electronics', 'teknoloji']):
                base_rate = max(base_rate, 0.025)
                surcharge += 0.005
            
            # Digital products: lower commission
            elif any(kw in cat_name for kw in ['dijital', 'digital', 'yazılım', 'software']):
                base_rate = min(base_rate, 0.015)
            
            # Luxury items: higher commission
            elif any(kw in cat_name for kw in ['lüks', 'luxury', 'mücevher', 'jewelry']):
                surcharge += 0.010
        
        return base_rate, min(surcharge, 0.02)  # Cap surcharge at 2%
    
    def _get_installment_interest_rate(self, installment_count, category_ids=None):
        """Get interest rate for installments based on count and category"""
        # Base rates by installment count
        base_rates = {
            2: 0.010, 3: 0.015, 4: 0.020,
            6: 0.030, 9: 0.045, 12: 0.060,
        }
        
        rate = base_rates.get(installment_count, 0.015)
        
        # Category adjustments
        if category_ids:
            categories = request.env['product.category'].sudo().browse(category_ids)
            for category in categories:
                if category.paratika_max_installment and int(category.paratika_max_installment) < installment_count:
                    # Category doesn't allow this many installments - return high rate to discourage
                    return 0.15
        
        return rate
    
    # ========================================================================
    # CARD TOKENIZATION API
    # ========================================================================
    
    @http.route('/payment/paratika/tokenize_card', type='json', auth='user')
    def tokenize_card(self, transaction_id, card_token, **kwargs):
        """
        Save card token for future one-click payments
        Requires user authentication
        """
        try:
            transaction = request.env['payment.transaction'].browse(int(transaction_id))
            transaction.check_access_rights('read')
            
            if transaction.provider_id.code != 'paratika':
                return {'error': 'Invalid provider'}
            
            # Create or update payment token
            token_vals = transaction._extract_token_values({
                'cardToken': card_token,
                'cardType': kwargs.get('card_type', 'credit'),
                'cardBrand': kwargs.get('card_brand', ''),
                'expiryMonth': kwargs.get('expiry_month'),
                'expiryYear': kwargs.get('expiry_year'),
            })
            
            if token_vals:
                token = request.env['payment.token'].sudo().create(token_vals)
                return {
                    'success': True,
                    'token_id': token.id,
                    'message': _('Kart başarıyla kaydedildi')
                }
            
            return {'error': 'Token creation failed'}
            
        except Exception as e:
            _logger.error(f"Tokenization error: {e}", exc_info=True)
            return {'error': str(e)}
    
    @http.route('/payment/paratika/user_tokens', type='json', auth='user')
    def get_user_tokens(self, **kwargs):
        """Get saved card tokens for current user"""
        tokens = request.env['payment.token'].sudo().search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('provider_id.code', '=', 'paratika'),
            ('verified', '=', True),
        ])
        
        return {
            'tokens': [{
                'id': t.id,
                'name': t.name,
                'card_brand': t.card_brand,
                'card_number': t.card_number,  # Already masked by Odoo
                'expiry_date': t.expiry_date,
                'is_default': t.id == request.env.user.partner_id.payment_token_id.id,
            } for t in tokens]
        }


class ParatikaWebsiteSale(WebsiteSale):
    """Extend website sale for category-based payment display"""
    
    @http.route(['/shop/checkout'], type='http', auth="public", website=True, sitemap=False)
    def checkout(self, **post):
        """Override checkout to inject category payment data"""
        response = super().checkout(**post)
        
        # Add category payment data to response context if needed
        if request.website and request.env['payment.provider'].sudo().search([('code', '=', 'paratika')]):
            # This will be handled by the JS widget
            pass
        
        return response