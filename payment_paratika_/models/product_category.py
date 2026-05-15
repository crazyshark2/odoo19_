# -*- coding: utf-8 -*-
"""
Extend product.category with Paratika payment settings
"""
from odoo import api, fields, models, _


class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    # =========================================================================
    # PARATIKA PAYMENT SETTINGS
    # =========================================================================
    
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
    
    paratika_commission_override = fields.Float(
        string='Özel Komisyon (%)',
        help='Bu kategori için özel komisyon oranı (boş bırakılırsa genel oran kullanılır)'
    )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_paratika_payment_rules(self, provider_id=None):
        """Get Paratika payment rules for this category"""
        self.ensure_one()
        
        rules = {
            'allowed_providers': self.paratika_payment_provider_ids.ids,
            'default_installment': self.paratika_default_installment,
            'max_installment': int(self.paratika_max_installment) if self.paratika_max_installment else 12,
            'bank_priority': [b.code for b in self.paratika_bank_priority],
            'commission_rate': self.paratika_commission_override if self.paratika_commission_override else None,
        }
        
        return rules