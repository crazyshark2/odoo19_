# -*- coding: utf-8 -*-
"""
Test Complete Payment Flow for Paratika Provider
Odoo 19 Compatible
"""
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from odoo.tests import common, tagged, HttpCase
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from .test_paratika_common import TestParatikaCommon


@tagged('-at_install', 'post_install', 'paratika', 'payment_flow')
class TestPaymentFlow(TestParatikaCommon):
    """Test complete payment flow with Paratika"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create a sale order for testing
        cls.Product = cls.env['product.product']
        cls.prod_test = cls.Product.create({
            'name': 'Test Product',
            'categ_id': cls.cat_electronics.id,
            'list_price': 1000.00,
            'type': 'product',
        })
        
        cls.SaleOrder = cls.env['sale.order']
        cls.so_test = cls.SaleOrder.create({
            'partner_id': cls.partner.id,
            'order_line': [(0, 0, {
                'product_id': cls.prod_test.id,
                'product_uom_qty': 1,
                'product_uom': cls.prod_test.uom_id.id,
                'price_unit': cls.prod_test.list_price,
            })],
        })
        cls.so_test.action_confirm()
    
    # =========================================================================
    # TEST: SESSION TOKEN GENERATION
    # =========================================================================
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_01_generate_session_token_success(self, mock_post):
        """Test successful session token generation"""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '00',
            'responseMsg': 'Success',
            'sessionToken': 'TEST_SESSION_TOKEN_12345',
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Create transaction
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_001',
        })
        
        # Generate token
        token = self.paratika_provider._generate_session_token(transaction)
        
        # Verify
        self.assertEqual(token, 'TEST_SESSION_TOKEN_12345')
        mock_post.assert_called_once()
        
        # Verify request payload
        call_args = mock_post.call_args
        payload = call_args[1]['data']
        self.assertEqual(payload['MERCHANT'], self.paratika_provider.paratika_merchant_id)
        self.assertEqual(payload['AMOUNT'], '1000.00')
        self.assertEqual(payload['CURRENCY'], 'TRY')
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_02_generate_session_token_failure(self, mock_post):
        """Test session token generation with API error"""
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '99',
            'responseMsg': 'System Error',
        }
        mock_post.return_value = mock_response
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_002',
        })
        
        # Should raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            self.paratika_provider._generate_session_token(transaction)
        
        self.assertIn('Session oluşturulamadı', str(cm.exception))
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_03_generate_session_token_connection_error(self, mock_post):
        """Test session token generation with connection error"""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_003',
        })
        
        with self.assertRaises(ValidationError) as cm:
            self.paratika_provider._generate_session_token(transaction)
        
        self.assertIn('bağlanılamadı', str(cm.exception))
    
    # =========================================================================
    # TEST: HASH GENERATION & VERIFICATION
    # =========================================================================
    
    def test_04_hash_generation(self):
        """Test SHA512 hash generation matches Paratika spec"""
        test_data = {
            'merchantPaymentId': 'TEST_REF_001',
            'customerId': '1',
            'sessionToken': 'TOKEN_123',
            'responseCode': '00',
            'random': '20240101120000',
        }
        
        hash_result = self.paratika_provider._generate_hash(test_data)
        
        # Verify it's a valid SHA512 hex string
        self.assertEqual(len(hash_result), 128)  # SHA512 = 64 bytes = 128 hex chars
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_result))
    
    def test_05_hash_verification_success(self):
        """Test successful hash verification"""
        callback_data = {
            'merchantPaymentId': 'TEST_REF_001',
            'customerId': '1',
            'sessionToken': 'TOKEN_123',
            'responseCode': '00',
            'random': '20240101120000',
        }
        
        # Generate expected hash
        expected_hash = self.paratika_provider._generate_hash(callback_data)
        callback_data['sdSha512'] = expected_hash
        
        # Verify
        result = self.paratika_provider._verify_callback_hash(callback_data)
        self.assertTrue(result)
    
    def test_06_hash_verification_failure(self):
        """Test hash verification with tampered data"""
        callback_data = {
            'merchantPaymentId': 'TEST_REF_001',
            'customerId': '1',
            'sessionToken': 'TOKEN_123',
            'responseCode': '00',
            'random': '20240101120000',
            'sdSha512': 'invalid_hash_value',
        }
        
        result = self.paratika_provider._verify_callback_hash(callback_data)
        self.assertFalse(result)
    
    def test_07_hash_verification_missing_hash(self):
        """Test hash verification when hash is missing"""
        callback_data = {
            'merchantPaymentId': 'TEST_REF_001',
            'responseCode': '00',
            # Missing sdSha512
        }
        
        result = self.paratika_provider._verify_callback_hash(callback_data)
        self.assertFalse(result)
    
    # =========================================================================
    # TEST: PAYMENT PROCESSING
    # =========================================================================
    
    def test_08_process_successful_payment(self):
        """Test processing successful payment callback"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_004',
            'state': 'pending',
        })
        
        callback_data = {
            'merchantPaymentId': 'TEST_REF_004',
            'responseCode': '00',
            'responseMsg': 'Success',
            'pgTranId': 'PG_123456789',
            'pgOrderId': 'PG_ORDER_001',
            'authCode': 'AUTH_001',
        }
        callback_data['sdSha512'] = self.paratika_provider._generate_hash(callback_data)
        
        # Process
        transaction._process('paratika', callback_data)
        
        # Verify transaction state
        self.assertEqual(transaction.state, 'done')
        self.assertEqual(transaction.provider_reference, 'PG_123456789')
        self.assertEqual(transaction.paratika_pg_tras_id, 'PG_123456789')
        self.assertEqual(transaction.paratika_auth_code, 'AUTH_001')
    
    def test_09_process_declined_payment(self):
        """Test processing declined payment callback"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_005',
            'state': 'pending',
        })
        
        callback_data = {
            'merchantPaymentId': 'TEST_REF_005',
            'responseCode': '05',
            'responseMsg': 'Do Not Honor',
        }
        callback_data['sdSha512'] = self.paratika_provider._generate_hash(callback_data)
        
        # Process
        transaction._process('paratika', callback_data)
        
        # Verify transaction state
        self.assertEqual(transaction.state, 'error')
        self.assertIn('reddedildi', transaction.state_message.lower())
    
    def test_10_process_pending_payment(self):
        """Test processing pending/retry payment callback"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_006',
            'state': 'draft',
        })
        
        callback_data = {
            'merchantPaymentId': 'TEST_REF_006',
            'responseCode': '07',  # Lost card - can retry
            'responseMsg': 'Lost Card, Pick Up',
        }
        callback_data['sdSha512'] = self.paratika_provider._generate_hash(callback_data)
        
        # Process
        transaction._process('paratika', callback_data)
        
        # Verify transaction state
        self.assertEqual(transaction.state, 'pending')
    
    # =========================================================================
    # TEST: REFUND PROCESSING
    # =========================================================================
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_11_send_refund_request_success(self, mock_post):
        """Test successful refund request"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '00',
            'responseMsg': 'Refund Success',
            'pgTranId': 'REFUND_123',
        }
        mock_post.return_value = mock_response
        
        # Create completed transaction
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 500.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_007',
            'state': 'done',
            'provider_reference': 'PG_ORIGINAL_123',
            'paratika_pg_tras_id': 'PG_ORIGINAL_123',
        })
        
        # Send refund
        result = transaction._send_refund_request()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['reference'], 'REFUND_123')
        
        # Verify API call
        call_args = mock_post.call_args[1]['data']
        self.assertEqual(call_args['ACTION'], 'REFUND')
        self.assertEqual(call_args['AMOUNT'], '500.00')
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_12_send_refund_request_failure(self, mock_post):
        """Test failed refund request"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '99',
            'responseMsg': 'Refund Not Allowed',
        }
        mock_post.return_value = mock_response
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 500.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_008',
            'state': 'done',
            'provider_reference': 'PG_ORIGINAL_456',
            'paratika_pg_tras_id': 'PG_ORIGINAL_456',
        })
        
        with self.assertRaises(ValidationError) as cm:
            transaction._send_refund_request()
        
        self.assertIn('İade başarısız', str(cm.exception))
    
    # =========================================================================
    # TEST: CAPTURE & VOID (PRE-AUTH)
    # =========================================================================
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_13_send_capture_request(self, mock_post):
        """Test capture (post-auth) request for pre-authorized payment"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '00',
            'responseMsg': 'Post-Auth Success',
        }
        mock_post.return_value = mock_response
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 750.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_009',
            'state': 'authorized',
            'provider_reference': 'PG_AUTH_123',
            'paratika_pg_tras_id': 'PG_AUTH_123',
        })
        
        # Send capture
        transaction._send_capture_request()
        
        # Verify transaction is now done
        self.assertEqual(transaction.state, 'done')
        
        # Verify API call
        call_args = mock_post.call_args[1]['data']
        self.assertEqual(call_args['ACTION'], 'POSTAUTH')
    
    @patch('odoo.addons.payment_paratika.models.payment_provider.requests.post')
    def test_14_send_void_request(self, mock_post):
        """Test void request to cancel pre-authorization"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'responseCode': '00',
            'responseMsg': 'Void Success',
        }
        mock_post.return_value = mock_response
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 750.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_010',
            'state': 'authorized',
            'provider_reference': 'PG_AUTH_456',
            'paratika_pg_tras_id': 'PG_AUTH_456',
        })
        
        # Send void
        transaction._send_void_request()
        
        # Verify transaction is canceled
        self.assertEqual(transaction.state, 'cancel')
    
    # =========================================================================
    # TEST: RENDERING VALUES
    # =========================================================================
    
    @patch.object(TestParatikaCommon.Provider, '_generate_session_token')
    def test_15_get_specific_rendering_values(self, mock_generate_token):
        """Test rendering values include Paratika-specific data"""
        mock_generate_token.return_value = 'MOCK_SESSION_TOKEN'
        
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_011',
        })
        
        processing_values = {
            'transaction_id': transaction.id,
            'amount': 1000.00,
        }
        
        rendering_values = self.paratika_provider._get_specific_rendering_values(processing_values)
        
        # Verify Paratika-specific values
        self.assertEqual(rendering_values['paratika_session_token'], 'MOCK_SESSION_TOKEN')
        self.assertIn('paratika_api_url', rendering_values)
        self.assertEqual(rendering_values['paratika_integration_mode'], 'hpp')
    
    # =========================================================================
    # TEST: CATEGORY-BASED INSTALLMENT IN PROCESSING
    # =========================================================================
    
    def test_16_installment_validation_in_processing(self):
        """Test installment count validation during processing"""
        # Enable category installments
        self.paratika_provider.paratika_enable_category_installments = True
        
        # Setup: Electronics allows only 1,2,3
        self.env['paratika.category.installment'].create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_electronics.id,
            'allowed_installments': '1,2,3',
            'default_installment': '1',
        })
        
        # Create transaction with invalid installment (6) for electronics
        transaction = self.Transaction.new({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_012',
            'sale_order_ids': [(4, self.so_test.id)],  # Electronics category
            'paratika_installment_count': 6,  # Invalid for electronics
        })
        
        # Get processing values - should auto-correct installment
        processing_values = transaction._get_specific_processing_values({})
        
        # Should have corrected to default (1)
        self.assertEqual(transaction.paratika_installment_count, 1)
    
    # =========================================================================
    # TEST: TOKENIZATION
    # =========================================================================
    
    def test_17_extract_token_values(self):
        """Test extraction of token values from payment data"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_013',
        })
        
        payment_data = {
            'cardToken': 'TOKEN_ABC123',
            'cardType': 'Credit',
            'cardBrand': 'Visa',
            'cardMask': '454671******7894',
            'expiryMonth': '12',
            'expiryYear': '2026',
        }
        
        token_values = transaction._extract_token_values(payment_data)
        
        # Verify extracted values
        self.assertEqual(token_values['payment_provider_id'], self.paratika_provider.id)
        self.assertEqual(token_values['partner_id'], self.partner.id)
        self.assertEqual(token_values['token'], 'TOKEN_ABC123')
        self.assertEqual(token_values['card_type'], 'credit')
        self.assertEqual(token_values['card_brand'], 'Visa')
        self.assertEqual(token_values['expiry_date'], '12/2026')
    
    def test_18_extract_token_values_no_token(self):
        """Test token extraction when no card token present"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'amount': 1000.00,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'TEST_REF_014',
        })
        
        payment_data = {
            'responseCode': '00',
            # No cardToken
        }
        
        token_values = transaction._extract_token_values(payment_data)
        self.assertEqual(token_values, {})
    
    # =========================================================================
    # TEST: AMOUNT & REFERENCE EXTRACTION
    # =========================================================================
    
    def test_19_extract_amount_data(self):
        """Test extraction of amount data from callback"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'reference': 'TEST_REF_015',
        })
        
        payment_data = {
            'amount': '1250.50',
            'currency': 'EUR',
        }
        
        amount_data = transaction._extract_amount_data(payment_data)
        
        self.assertEqual(amount_data['amount'], 1250.50)
        self.assertEqual(amount_data['currency_code'], 'EUR')
        self.assertEqual(amount_data['precision_digits'], 2)
    
    def test_20_extract_reference(self):
        """Test extraction of transaction reference"""
        transaction = self.Transaction.create({
            'provider_id': self.paratika_provider.id,
            'reference': 'TEST_REF_016',
        })
        
        # Test with pgTranId
        payment_data_1 = {'pgTranId': 'PG_123'}
        ref_1 = transaction._extract_reference('paratika', payment_data_1)
        self.assertEqual(ref_1, 'PG_123')
        
        # Test with merchantPaymentId fallback
        payment_data_2 = {'merchantPaymentId': 'MERCH_456'}
        ref_2 = transaction._extract_reference('paratika', payment_data_2)
        self.assertEqual(ref_2, 'MERCH_456')
        
        # Test with no reference
        payment_data_3 = {'responseCode': '00'}
        ref_3 = transaction._extract_reference('paratika', payment_data_3)
        self.assertIsNone(ref_3)


@tagged('post_install', '-at_install', 'paratika_http')
class TestPaymentFlowHttp(HttpCase):
    """HTTP tests for Paratika payment flow"""
    
    def test_01_callback_endpoint_invalid_hash(self):
        """Test callback endpoint rejects invalid hash"""
        response = self.url_open(
            '/payment/paratika/callback',
            data={
                'merchantPaymentId': 'TEST_001',
                'responseCode': '00',
                'sdSha512': 'invalid_hash',
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Invalid security hash', response.content)
    
    def test_02_callback_endpoint_success(self):
        """Test successful callback processing"""
        # This would require full setup with mocked provider
        # Implemented in integration test suite
        pass