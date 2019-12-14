import time
from odoo import models, fields, api, _
import odoo.addons.decimal_precision as dp
from odoo.exceptions import except_orm, ValidationError
from odoo.tools import misc, DEFAULT_SERVER_DATETIME_FORMAT
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from odoo import http


class account_payment(models.Model):
    _inherit = "account.payment"

    @api.multi
    def post(self):
        res = super(account_payment, self).post()
        domain_inv = [('invoice_id', 'in', [item.id for item in self.invoice_ids])]
        house_id = self.env['house.allocation'].search(domain_inv)
        if house_id.state not in ['done','Allocated']:
            house_id.send_mail_account_all()
            house_id.write({'payment_ids': [(4,[self.id])], 'state': 'waiting'}) 
        else:
            house_id.send_mail_account_all()
            house_id.write({'payment_ids': [(4,[self.id])], 'state': 'done'})
            # house_id.write({'payment_ids': [(4,[self.id])], 'state': 'waiting'})
        return res
