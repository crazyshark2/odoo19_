# -*- coding: utf-8 -*-
"""
Paratika Bank Model - Bank/PoZ configuration
"""
from odoo import api, fields, models, _


class ParatikaPaymentBank(models.Model):
    """Bank/POS configuration for Paratika"""
    _name = 'paratika.payment.bank'
    _description = 'Paratika Payment Bank Configuration'
    _order = 'name'
    
    name = fields.Char(string='Banka Adı', required=True, translate=True)
    code = fields.Char(string='Banka Kodu', required=True, help='Paratika API banka kodu')
    logo = fields.Binary(string='Logo', attachment=True)
    
    # Installment configuration
    supports_installments = fields.Boolean(string='Taksit Desteği', default=True)
    max_installments = fields.Selection(
        selection=[
            ('1', 'Peşin'), ('2', '2'), ('3', '3'), ('4', '4'),
            ('6', '6'), ('9', '9'), ('12', '12'),
        ],
        string='Maksimum Taksit',
        default='12'
    )
    
    # Commission rates
    base_commission = fields.Float(string='Temel Komisyon (%)', default=2.0)
    installment_commission = fields.Float(
        string='Taksit Komisyonu (%/ay)', 
        default=0.5,
        help='Her taksit için ek komisyon oranı'
    )
    
    # Category-specific overrides
    category_commission_rules = fields.Json(
        string='Kategori Komisyon Kuralları',
        help='JSON: {"category_id": {"commission": 2.5, "max_installments": "6"}}'
    )
    
    # Display settings
    active = fields.Boolean(string='Aktif', default=True)
    sequence = fields.Integer(string='Sıra', default=10)
    
    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'Banka kodu benzersiz olmalıdır!')
    ]