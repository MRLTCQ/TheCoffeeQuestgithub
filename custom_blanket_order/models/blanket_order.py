# blanket_order.py
from odoo import models, fields, api

class BlanketOrder(models.Model):
    _name = 'blanket.order'
    _description = 'Blanket Order'

    name = fields.Char(string='Reference', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    order_line_ids = fields.One2many('blanket.order.line', 'blanket_order_id', string='Lines')

class BlanketOrderLine(models.Model):
    _name = 'blanket.order.line'
    _description = 'Blanket Order Line'

    blanket_order_id = fields.Many2one('blanket.order', string='Blanket Order', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity')
    price_unit = fields.Monetary(string='Unit Price')
    currency_id = fields.Many2one('res.currency', string='Currency')
    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal')

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit
