# -*- coding: utf-8 -*-
from odoo.tests import common, tagged


@tagged('-at_install', 'post_install', 'paratika')
class TestParatikaCommon(common.TransactionCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Provider = cls.env['payment.provider']
        cls.Transaction = cls.env['payment.transaction']
        cls.Partner = cls.env['res.partner']
        cls.Category = cls.env['product.category']
        
        # Test provider
        cls.paratika_provider = cls.Provider.create({
            'name': 'Paratika Test',
            'code': 'paratika',
            'state': 'test',
            'paratika_merchant_id': '700100000',
            'paratika_merchant_user': 'test_user',
            'paratika_merchant_password': 'test_pass',
            'paratika_secret_key': 'test_secret_12345',
            'paratika_test_mode': True,
        })
        
        # Test categories
        cls.cat_electronics = cls.Category.create({'name': 'Elektronik'})
        cls.cat_home = cls.Category.create({'name': 'Ev & Yaşam'})
        
        # Test partner
        cls.partner = cls.Partner.create({
            'name': 'Test Customer',
            'email': 'test@example.com',
        })