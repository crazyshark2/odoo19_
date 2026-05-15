# -*- coding: utf-8 -*-
"""
Test Category-Based Payment Filtering for Paratika Provider
Odoo 19 Compatible
"""
from odoo.tests import common, tagged, Form
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger
from .test_paratika_common import TestParatikaCommon


@tagged('-at_install', 'post_install', 'paratika', 'category_filter')
class TestCategoryFilter(TestParatikaCommon):
    """Test category-based payment method filtering"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create additional test categories
        cls.cat_digital = cls.Category.create({
            'name': 'Dijital Ürünler',
            'parent_id': cls.cat_electronics.id,
        })
        cls.cat_furniture = cls.Category.create({
            'name': 'Mobilya',
            'parent_id': cls.cat_home.id,
        })
        
        # Create test products
        cls.Product = cls.env['product.product']
        cls.prod_laptop = cls.Product.create({
            'name': 'Gaming Laptop',
            'categ_id': cls.cat_electronics.id,
            'list_price': 15000.00,
            'type': 'product',
        })
        cls.prod_software = cls.Product.create({
            'name': 'Antivirus Software',
            'categ_id': cls.cat_digital.id,
            'list_price': 500.00,
            'type': 'product',
        })
        cls.prod_sofa = cls.Product.create({
            'name': 'Corner Sofa',
            'categ_id': cls.cat_furniture.id,
            'list_price': 8000.00,
            'type': 'product',
        })
        
        # Create test sale orders
        cls.SaleOrder = cls.env['sale.order']
        cls.so_electronics = cls._create_sale_order([cls.prod_laptop])
        cls.so_mixed = cls._create_sale_order([cls.prod_laptop, cls.prod_sofa])
        cls.so_digital = cls._create_sale_order([cls.prod_software])
    
    @classmethod
    def _create_sale_order(cls, products):
        """Helper to create sale order with products"""
        so = cls.SaleOrder.create({
            'partner_id': cls.partner.id,
            'order_line': [(0, 0, {
                'product_id': prod.id,
                'product_uom_qty': 1,
                'product_uom': prod.uom_id.id,
                'price_unit': prod.list_price,
            }) for prod in products],
        })
        so.action_confirm()
        return so
    
    # =========================================================================
    # TEST: NO RESTRICTION
    # =========================================================================
    
    def test_01_no_restriction_shows_always(self):
        """Provider with no category restriction should show for all orders"""
        self.paratika_provider.paratika_category_restriction = 'none'
        self.paratika_provider.paratika_allowed_category_ids = False
        self.paratika_provider.paratika_denied_category_ids = False
        
        # Should be compatible with all order types
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_electronics.id,
        )
        self.assertIn(self.paratika_provider, providers)
        
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_mixed.id,
        )
        self.assertIn(self.paratika_provider, providers)
    
    # =========================================================================
    # TEST: ALLOW RESTRICTION
    # =========================================================================
    
    def test_02_allow_restriction_only_allowed_categories(self):
        """Provider with 'allow' restriction should only show for allowed categories"""
        self.paratika_provider.paratika_category_restriction = 'allow'
        self.paratika_provider.paratika_allowed_category_ids = self.cat_electronics
        
        # Electronics order - should show
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_electronics.id,
        )
        self.assertIn(self.paratika_provider, providers)
        
        # Digital order (child of electronics) - should show (parent category match)
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_digital.id,
        )
        self.assertIn(self.paratika_provider, providers)
        
        # Mixed order with non-allowed category - should NOT show
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_mixed.id,
        )
        # Mixed order has electronics (allowed) so should still show
        self.assertIn(self.paratika_provider, providers)
        
        # Furniture-only order - should NOT show
        so_furniture = self._create_sale_order([self.prod_sofa])
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=so_furniture.id,
        )
        self.assertNotIn(self.paratika_provider, providers)
    
    # =========================================================================
    # TEST: DENY RESTRICTION
    # =========================================================================
    
    def test_03_deny_restriction_excludes_denied_categories(self):
        """Provider with 'deny' restriction should exclude denied categories"""
        self.paratika_provider.paratika_category_restriction = 'deny'
        self.paratika_provider.paratika_denied_category_ids = self.cat_electronics
        
        # Electronics order - should NOT show
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_electronics.id,
        )
        self.assertNotIn(self.paratika_provider, providers)
        
        # Home/Furniture order - should show
        so_furniture = self._create_sale_order([self.prod_sofa])
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=so_furniture.id,
        )
        self.assertIn(self.paratika_provider, providers)
    
    # =========================================================================
    # TEST: CATEGORY INSTALLMENT OPTIONS
    # =========================================================================
    
    def test_04_category_installment_options(self):
        """Test category-based installment option retrieval"""
        # Setup category installment config
        self.paratika_provider.paratika_enable_category_installments = True
        self.InstallmentConfig = self.env['paratika.category.installment']
        
        # Electronics: max 3 installments
        self.InstallmentConfig.create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_electronics.id,
            'allowed_installments': '1,2,3',
            'default_installment': '1',
        })
        
        # Home: up to 12 installments
        self.InstallmentConfig.create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_home.id,
            'allowed_installments': '1,2,3,6,9,12',
            'default_installment': '6',
        })
        
        # Create temp transaction for electronics order
        temp_tx = self.Transaction.new({
            'sale_order_ids': [(4, self.so_electronics.id)],
            'provider_id': self.paratika_provider.id,
            'amount': 15000.00,
        })
        
        # Should get electronics installments
        installments = self.paratika_provider._get_category_installment_options(temp_tx)
        self.assertEqual(installments, ['1', '2', '3'])
        
        # Create temp transaction for home order
        so_home = self._create_sale_order([self.prod_sofa])
        temp_tx_home = self.Transaction.new({
            'sale_order_ids': [(4, so_home.id)],
            'provider_id': self.paratika_provider.id,
            'amount': 8000.00,
        })
        
        # Should get home installments
        installments_home = self.paratika_provider._get_category_installment_options(temp_tx_home)
        self.assertEqual(installments_home, ['1', '2', '3', '6', '9', '12'])
    
    def test_05_default_installment_by_category(self):
        """Test default installment selection based on category"""
        self.paratika_provider.paratika_enable_category_installments = True
        
        # Setup configs
        self.env['paratika.category.installment'].create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_electronics.id,
            'default_installment': '1',  # Peşin for electronics
        })
        self.env['paratika.category.installment'].create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_home.id,
            'default_installment': '6',  # 6 taksit for home
        })
        
        # Test electronics order
        temp_tx = self.Transaction.new({
            'sale_order_ids': [(4, self.so_electronics.id)],
            'provider_id': self.paratika_provider.id,
        })
        default = self.paratika_provider._get_category_default_installment(temp_tx)
        self.assertEqual(default, '1')
        
        # Test home order
        so_home = self._create_sale_order([self.prod_sofa])
        temp_tx_home = self.Transaction.new({
            'sale_order_ids': [(4, so_home.id)],
            'provider_id': self.paratika_provider.id,
        })
        default_home = self.paratika_provider._get_category_default_installment(temp_tx_home)
        self.assertEqual(default_home, '6')
    
    # =========================================================================
    # TEST: CHECK CATEGORY COMPATIBILITY
    # =========================================================================
    
    def test_06_check_category_compatibility_method(self):
        """Test the _check_category_compatibility helper method"""
        # No restriction
        self.paratika_provider.paratika_category_restriction = 'none'
        self.assertTrue(self.paratika_provider._check_category_compatibility(self.cat_electronics))
        
        # Allow restriction - matching category
        self.paratika_provider.paratika_category_restriction = 'allow'
        self.paratika_provider.paratika_allowed_category_ids = self.cat_electronics
        self.assertTrue(self.paratika_provider._check_category_compatibility(self.cat_electronics))
        self.assertFalse(self.paratika_provider._check_category_compatibility(self.cat_home))
        
        # Deny restriction - matching category
        self.paratika_provider.paratika_category_restriction = 'deny'
        self.paratika_provider.paratika_denied_category_ids = self.cat_electronics
        self.assertFalse(self.paratika_provider._check_category_compatibility(self.cat_electronics))
        self.assertTrue(self.paratika_provider._check_category_compatibility(self.cat_home))
    
    # =========================================================================
    # TEST: PARENT CATEGORY INHERITANCE
    # =========================================================================
    
    def test_07_parent_category_inheritance(self):
        """Test that child categories inherit parent category rules"""
        self.paratika_provider.paratika_category_restriction = 'allow'
        self.paratika_provider.paratika_allowed_category_ids = self.cat_electronics
        
        # Digital is child of electronics - should be allowed
        self.assertTrue(self.paratika_provider._check_category_compatibility(self.cat_digital))
        
        # Create grandchild category
        cat_games = self.Category.create({
            'name': 'Oyunlar',
            'parent_id': self.cat_digital.id,
        })
        self.assertTrue(self.paratika_provider._check_category_compatibility(cat_games))
    
    # =========================================================================
    # TEST: MULTIPLE CATEGORIES IN ORDER
    # =========================================================================
    
    def test_08_mixed_category_order_filtering(self):
        """Test filtering when order has multiple categories"""
        # Allow only electronics
        self.paratika_provider.paratika_category_restriction = 'allow'
        self.paratika_provider.paratika_allowed_category_ids = self.cat_electronics
        
        # Mixed order has electronics + furniture
        # Should show because at least one category matches (OR logic)
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_mixed.id,
        )
        self.assertIn(self.paratika_provider, providers)
        
        # Now deny electronics
        self.paratika_provider.paratika_category_restriction = 'deny'
        self.paratika_provider.paratika_denied_category_ids = self.cat_electronics
        
        # Mixed order has electronics (denied) - should NOT show
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=1000,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=self.so_mixed.id,
        )
        self.assertNotIn(self.paratika_provider, providers)
    
    # =========================================================================
    # TEST: EDGE CASES
    # =========================================================================
    
    @mute_logger('odoo.models')
    def test_09_empty_order_categories(self):
        """Test behavior when order has no product categories"""
        # Create order without products
        so_empty = self.SaleOrder.create({
            'partner_id': self.partner.id,
        })
        
        # Should fall back to default behavior (show provider)
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=0,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=so_empty.id,
        )
        # Non-Paratika providers should still work
        # Paratika with no restriction should show
        self.paratika_provider.paratika_category_restriction = 'none'
        providers = self.Provider._get_compatible_providers(
            company_id=self.env.company.id,
            partner_id=self.partner.id,
            amount=0,
            currency_id=self.env.company.currency_id.id,
            sale_order_id=so_empty.id,
        )
        self.assertIn(self.paratika_provider, providers)
    
    def test_10_category_config_validation(self):
        """Test validation of category installment configuration"""
        InstallmentConfig = self.env['paratika.category.installment']
        
        # Valid config
        config = InstallmentConfig.create({
            'provider_id': self.paratika_provider.id,
            'category_id': self.cat_electronics.id,
            'allowed_installments': '1,2,3,6',
        })
        self.assertTrue(config.exists())
        
        # Invalid installment number (>12)
        with self.assertRaises(ValidationError):
            InstallmentConfig.create({
                'provider_id': self.paratika_provider.id,
                'category_id': self.cat_home.id,
                'allowed_installments': '1,2,15',  # 15 is invalid
            })
        
        # Invalid format
        with self.assertRaises(ValidationError):
            InstallmentConfig.create({
                'provider_id': self.paratika_provider.id,
                'category_id': self.cat_furniture.id,
                'allowed_installments': 'abc,def',  # Not numbers
            })
        
        # Duplicate provider+category
        with self.assertRaises(ValidationError):
            InstallmentConfig.create({
                'provider_id': self.paratika_provider.id,
                'category_id': self.cat_electronics.id,  # Already exists
                'allowed_installments': '1,2',
            })