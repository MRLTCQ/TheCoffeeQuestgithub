# models/blanket_order.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class BlanketOrder(models.Model):
    _name = 'blanket.order'
    _description = 'Blanket Order'

    name = fields.Char(string='Reference', required=True, default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    date_order = fields.Datetime(string='Order Date', default=fields.Datetime.now, readonly=True)
    
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id,
        required=True
    )
    order_line_ids = fields.One2many('blanket.order.line', 'blanket_order_id', string='Order Lines')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(string='Taxes', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='Total', compute='_compute_amounts', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

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

    def action_confirm(self):
        """Confirm the blanket order and reserve stock"""
        for order in self:
            order.state = 'confirmed'
            for line in order.order_line_ids:
                line.reserve_stock()

    def action_cancel(self):
        """Cancel the blanket order and unreserve stock"""
        for order in self:
            for line in order.order_line_ids:
                line.unreserve_stock()
            order.state = 'cancel'


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
    reserved_qty = fields.Float(string='Reserved Quantity', default=0.0)

    # Stock move references for reservation tracking
    move_ids = fields.One2many('stock.move', 'blanket_order_line_id', string='Stock Moves')

    @api.model
    def create(self, vals):
        line = super().create(vals)
        if line.blanket_order_id.state == 'confirmed':
            line.update_reservation()
        return line

    def write(self, vals):
        result = super().write(vals)
        for line in self:
            if line.blanket_order_id.state == 'confirmed' and (
                'quantity' in vals or 'product_id' in vals
            ):
                line.update_reservation()
        return result


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
        """Reserve stock using simplified stock move creation"""
        for line in self:
            if line.reserved_qty >= line.quantity:
                continue  # Already fully reserved
                
            qty_to_reserve = line.quantity - line.reserved_qty

            if line.product_id.qty_available < qty_to_reserve:
                raise UserError(
                    f"Cannot reserve {qty_to_reserve} units of {line.product_id.display_name}. "
                    f"Only {line.product_id.qty_available} units available."
                )

            stock_location = self.env.ref('stock.stock_location_stock')
            customer_location = self.env.ref('stock.stock_location_customers')

            move_vals = {
                'name': f"Blanket Order Reservation: {line.blanket_order_id.name}",
                'product_id': line.product_id.id,
                'product_uom_qty': qty_to_reserve,
                'product_uom': line.product_id.uom_id.id,
                'location_id': stock_location.id,
                'location_dest_id': customer_location.id,
                'partner_id': line.blanket_order_id.partner_id.id,
                'blanket_order_line_id': line.id,
                'origin': line.blanket_order_id.name if line.blanket_order_id.name != 'New' else f"Blanket Line {line.id}",
                'state': 'draft',
            }

            move = self.env['stock.move'].create(move_vals)
            move._action_confirm()
            move._action_assign()

            if move.state == 'assigned':
                line.reserved_qty += qty_to_reserve
            else:
                move.unlink()
                raise UserError(
                    f"Could not reserve {qty_to_reserve} units of {line.product_id.display_name}. "
                    f"Stock may not be available."
                )

    def update_reservation(self):
        """Update reservation when quantity changes"""
        for line in self:
            if line.quantity > line.reserved_qty:
                # Need to reserve more
                qty_to_reserve = line.quantity - line.reserved_qty
                line._reserve_additional_stock(qty_to_reserve)
            elif line.quantity < line.reserved_qty:
                # Need to unreserve some
                qty_to_unreserve = line.reserved_qty - line.quantity
                line._unreserve_partial_stock(qty_to_unreserve)

    def _reserve_additional_stock(self, qty_to_reserve):
        """Reserve additional stock quantity"""
        # Check availability first
        if self.product_id.qty_available < qty_to_reserve:
            raise UserError(
                f"Cannot reserve additional {qty_to_reserve} units of {self.product_id.display_name}. "
                f"Only {self.product_id.qty_available} units available."
            )

        # Create stock move for additional reservation
        stock_location = self.env.ref('stock.stock_location_stock')
        customer_location = self.env.ref('stock.stock_location_customers')
        
        move_vals = {
            'name': f"Blanket Order Reservation: {self.blanket_order_id.name}",
            'product_id': self.product_id.id,
            'product_uom_qty': qty_to_reserve,
            'product_uom': self.product_id.uom_id.id,
            'location_id': stock_location.id,
            'location_dest_id': customer_location.id,
            'partner_id': self.blanket_order_id.partner_id.id,
            'origin': self.blanket_order_id.name,
            'blanket_order_line_id': self.id,
            'state': 'draft',
        }
        
        move = self.env['stock.move'].create(move_vals)
        move._action_confirm()
        move._action_assign()
        
        if move.state == 'assigned':
            self.reserved_qty += qty_to_reserve
        else:
            move.unlink()
            raise UserError(
                f"Could not reserve additional {qty_to_reserve} units of {self.product_id.display_name}. "
                f"Stock may not be available."
            )

    def _unreserve_partial_stock(self, qty_to_unreserve):
        """Unreserve partial stock quantity"""
        remaining_to_unreserve = qty_to_unreserve
        
        # Find moves to unreserve (start with most recent)
        moves_to_reduce = self.move_ids.filtered(
            lambda m: m.state in ('assigned', 'confirmed')
        ).sorted('create_date', reverse=True)
        
        for move in moves_to_reduce:
            if remaining_to_unreserve <= 0:
                break
                
            if move.product_uom_qty <= remaining_to_unreserve:
                # Cancel entire move
                remaining_to_unreserve -= move.product_uom_qty
                move._action_cancel()
            else:
                # Reduce move quantity
                new_qty = move.product_uom_qty - remaining_to_unreserve
                move.product_uom_qty = new_qty
                remaining_to_unreserve = 0
                
        self.reserved_qty -= qty_to_unreserve

    def unreserve_stock(self):
        """Unreserve all stock by cancelling moves"""
        for line in self:
            # Cancel all draft/confirmed moves
            moves_to_cancel = line.move_ids.filtered(lambda m: m.state in ('draft', 'waiting', 'confirmed', 'assigned'))
            moves_to_cancel._action_cancel()
            line.reserved_qty = 0.0

    def _check_stock_availability(self):
        for line in self:
            if line.quantity > line.product_id.qty_available:
                raise UserError(
                    f"Only {line.product_id.qty_available} units of "
                    f"{line.product_id.display_name} are available."
                )

    @api.onchange('quantity')
    def _onchange_quantity(self):
        for line in self:
            if line.blanket_order_id.state == 'confirmed':
                line.update_reservation()


    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set default values when product changes"""
        if self.product_id:
            self.description = self.product_id.display_name
            self.price_unit = self.product_id.list_price
            
            # If we had reservations for old product, unreserve them
            if self.reserved_qty > 0:
                self.unreserve_stock()
                
            # Check availability for new product
            if self.quantity > 0:
                self._check_stock_availability()

    def action_create_picking(self):
        """Create a picking from reserved stock"""
        for line in self:
            if line.reserved_qty <= 0:
                raise UserError(f"No reserved stock for {line.product_id.display_name}")
            
            # Get outgoing picking type
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('warehouse_id.company_id', '=', self.env.company.id)
            ], limit=1)
            
            if not picking_type:
                raise UserError("No outgoing picking type found")
            
            # Create picking
            picking_vals = {
                'partner_id': line.blanket_order_id.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': self.env.ref('stock.stock_location_stock').id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                'origin': line.blanket_order_id.name,
            }
            
            picking = self.env['stock.picking'].create(picking_vals)
            
            # Move the reserved stock moves to this picking
            assigned_moves = line.move_ids.filtered(lambda m: m.state == 'assigned')
            if assigned_moves:
                assigned_moves.write({'picking_id': picking.id})
                picking.action_confirm()
                
            return {
                'type': 'ir.actions.act_window',
                'name': 'Delivery Order',
                'res_model': 'stock.picking',
                'res_id': picking.id,
                'view_mode': 'form',
                'target': 'current',
            }
        
    def action_open_partial_convert_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Partial Conversion',
            'res_model': 'blanket.order.line.partial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_blanket_order_line_id': self.id,
            },
        }

