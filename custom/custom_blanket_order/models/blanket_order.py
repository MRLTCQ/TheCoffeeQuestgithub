from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class BlanketOrder(models.Model):
    _name = 'blanket.order'
    _description = 'Blanket Order'

    name = fields.Char(string='Reference', required=True, default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    date_order = fields.Datetime(string='Order Date', default=fields.Datetime.now, readonly=True)
    
    # Removed date_start and date_end from header - they're now on lines only
    
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id,
        required=True
    )
    order_line_ids = fields.One2many('blanket.order.line', 'blanket_order_id', string='Order Lines')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(string='Taxes', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='Total', compute='_compute_amounts', store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('blanket.order') or 'New'
        return super().create(vals)

    @api.depends('order_line_ids.price_subtotal', 'order_line_ids.price_tax')
    def _compute_amounts(self):
        for order in self:
            untaxed = sum(line.price_subtotal for line in order.order_line_ids)
            tax = sum(line.price_tax for line in order.order_line_ids)
            order.update({
                'amount_untaxed': untaxed,
                'amount_tax': tax,
                'amount_total': untaxed + tax,
            })


class BlanketOrderLine(models.Model):
    _name = 'blanket.order.line'
    _description = 'Blanket Order Line'

    blanket_order_id = fields.Many2one('blanket.order', string='Blanket Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    tax_ids = fields.Many2many('account.tax', string='Taxes')
    currency_id = fields.Many2one(related='blanket_order_id.currency_id', store=True, readonly=True)

    order_before_date = fields.Date(string='Order Before Date', required=True, help="Order before date for this order line")

    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Monetary(string='Tax', compute='_compute_amount', store=True)
    price_total = fields.Monetary(string='Total', compute='_compute_amount', store=True)

    delivered_qty = fields.Float(string='Delivered Quantity', default=0.0)
    invoiced_qty = fields.Float(string='Invoiced Quantity', default=0.0)

    is_reserved = fields.Boolean(string='Reserved', default=False)

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_amount(self):
        for line in self:
            taxes = line.tax_ids.compute_all(
                line.price_unit,
                currency=line.currency_id,
                quantity=line.quantity,
                product=line.product_id,
                partner=line.blanket_order_id.partner_id
            )
            line.price_subtotal = taxes['total_excluded']
            line.price_tax = taxes['total_included'] - taxes['total_excluded']
            line.price_total = taxes['total_included']

    @api.constrains('order_before_date')
    def _check_line_dates(self):
        for line in self:
            if line.order_before_date and line.order_before_date < fields.Date.today():
                raise ValidationError("Order before date must not be in the past.")

    
    def reserve_stock(self):
        for line in self:
            if not line.is_reserved and line.quantity > 0:
                stock_move = self.env['stock.move'].create({
                    'name': line.blanket_order_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.env.ref('stock.stock_location_stock').id,
                    'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                    'partner_id': line.blanket_order_id.partner_id.id,
                    'origin': line.blanket_order_id.name,
                })
                stock_move._action_confirm()
                line.is_reserved = True

    

    @api.onchange('quantity')
    @api.onchange('product_id')
    def _onchange_quantity_reserve(self):
        for line in self:
            if not line.product_id or line.quantity <= 0 or line.is_reserved:
                return

            available_qty = line.product_id.qty_available
            if line.quantity > available_qty:
                raise UserError(f"Not enough stock for {line.product_id.display_name}. Available: {available_qty}")

            line.reserve_stock()


