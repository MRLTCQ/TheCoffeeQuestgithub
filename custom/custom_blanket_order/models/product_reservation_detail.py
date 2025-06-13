from odoo import models, fields, tools

class ProductReservationDetail(models.Model):
    _name = 'product.reservation.detail'
    _description = 'Detailed Product Reservations'
    _auto = False
    _order = 'product_id, reservation_type, reference'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', readonly=True)
    quantity = fields.Float(string='Reserved Qty', readonly=True)
    reservation_type = fields.Selection([
        ('sales', 'Sales Order'),
        ('blanket', 'Blanket Order'),
        ('other', 'Other')
    ], string='Type', readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    date = fields.Datetime(string='Scheduled Date', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    sm.id AS id,
                    sm.product_id,
                    sm.location_id,
                    sm.product_uom_qty AS quantity,
                    CASE
                        WHEN sm.blanket_order_line_id IS NOT NULL THEN 'blanket'
                        WHEN sm.origin LIKE 'SO%%' THEN 'sales'
                        ELSE 'other'
                    END AS reservation_type,
                    sm.origin AS reference,
                    sm.date AS date
                FROM stock_move sm
                WHERE sm.state = 'assigned'
                  AND sm.product_id IS NOT NULL
                  AND sm.location_id IS NOT NULL
            )
        """)
