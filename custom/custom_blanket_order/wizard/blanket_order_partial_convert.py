from odoo import models, fields, api
from odoo.exceptions import UserError

class BlanketOrderLinePartialWizard(models.TransientModel):
    _name = 'blanket.order.line.partial.wizard'
    _description = 'Partial Conversion of Blanket Order Line'

    blanket_order_line_id = fields.Many2one('blanket.order.line', required=True)
    product_id = fields.Many2one(related='blanket_order_line_id.product_id', readonly=True)
    available_qty = fields.Float(related='blanket_order_line_id.quantity', readonly=True)
    already_delivered = fields.Float(related='blanket_order_line_id.delivered_qty', readonly=True)

    partial_qty = fields.Float(string='Quantity to Deliver', required=True)
    delivery_date = fields.Date(string='Planned Delivery Date', required=True)

    def action_create_sales_order(self):
        self.ensure_one()
        line = self.blanket_order_line_id
        remaining = line.quantity - line.delivered_qty

        if self.partial_qty <= 0:
            raise UserError("Quantity must be greater than 0.")
        if self.partial_qty > remaining:
            raise UserError(f"Cannot deliver more than remaining: {remaining} units.")

        # Create Sales Order
        so = self.env['sale.order'].create({
            'partner_id': line.blanket_order_id.partner_id.id,
            'date_order': fields.Date.today(),
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': self.partial_qty,
                'price_unit': line.price_unit,
                'tax_id': [(6, 0, line.tax_ids.ids)],
                'name': line.description or line.product_id.display_name,
            })],
            'origin': line.blanket_order_id.name,
        })

        # Track delivery progress
        line.delivered_qty += self.partial_qty

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': so.id,
            'target': 'current',
        }
