/** @odoo-module **/

import { registry } from '@web/core/registry';
import { patch } from '@web/core/utils/patch';

const graphView = registry.category('views').get('forecast_graph');

if (graphView && graphView.Controller) {
    patch(graphView.Controller.prototype, {
        _getForecastLineDisplayName(line) {
            return line.origin || line.picking_origin || "false reserved";
        },
    });
    console.debug('[custom_blanket_order] forecast_graph patched');
} else {
    console.warn('[custom_blanket_order] forecast_graph view not found');
}
