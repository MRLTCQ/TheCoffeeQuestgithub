{
    'name': 'Blanket Order Custom',
    'version': '1.0',
    'depends': ['sale', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/blanket_order_views.xml',
        'views/blanket_order_menu.xml',
    ],
    'installable': True,
}
