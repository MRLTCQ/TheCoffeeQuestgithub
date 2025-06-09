{
    'name': 'Blanket Order Custom',
    'version': '1.0',
    'depends': ['sale', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/blanket_order_menu.xml',
        'views/blanket_order_views.xml',
    ],
    'license': 'LGPL-3', 
    'installable': True,
}
