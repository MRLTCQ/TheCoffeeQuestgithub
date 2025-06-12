# stock_extensions.py
from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'
    
    blanket_order_line_id = fields.Many2one('blanket.order.line', string='Blanket Order Line')


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    blanket_order_line_id = fields.Many2one('blanket.order.line', string='Reserved for Blanket Order')
