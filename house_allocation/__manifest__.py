#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Maduka Sopulu Chris kingston
#
# Created:     20/04/2018
# Copyright:   (c) kingston 2018
# Licence:     <your licence>
#--------------------------------------------------------------------
{
    'name': 'House Allocation',
    'version': '10.0.1.0.0',
    'author': 'Maduka Sopulu',
    'description': """ERP Application for managing
                     the Estate management activities of a company""",
    'category': 'Procurement',

    'depends': ['base', 'branch'],
    'data': [
        
        'sequence/sequence.xml',
        'security/security_group.xml',
        'views/house_allocation_view.xml',
        # 'views/imprest_view.xml',
        # 'views/store_issuance_view.xml',
        # 'views/pop_message_wizard.xml',
        'security/ir.model.access.csv',
    ],
    'price': 420.99,
    'currency': 'USD',

    'installable': True,
    'auto_install': False,
}
