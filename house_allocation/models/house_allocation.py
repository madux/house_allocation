from datetime import datetime, timedelta
import time
from dateutil.relativedelta import relativedelta 
import odoo.addons.decimal_precision as dp
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo import http


class HouseAllocation(models.Model):
    _name = "house.allocation"
    _inherit = ['mail.thread', 'ir.needaction_mixin', 'ir.attachment']
    _description = "Request"
    _order = "id desc"
    _rec_name = "name"
    
    def change_uom(self):
        uom = self.env['product.uom'].search([('name', '=', 'Unit(s)')])
        return uom.id
    
    name = fields.Char('Ref')
    partner_id = fields.Many2one('res.partner', domain=[('customer', '=', True)])
    branch_id = fields.Many2one(
        'res.branch',
        string="Branch",
        required = True,
        help="Tell Admin to set your branch... (Users-->Preferences-->Allowed Branch)")
    product_id = fields.Many2one('product.allocation', 'House/Plot')
    label = fields.Many2one(
        'product.uom',
        string='UOM',
        default=change_uom,
        required=False)

    qty = fields.Float('Purchased Qty', default=1.0, required=True)
    list_price = fields.Float(
        'Current Rate',
        readonly=True, store=True,
        related='product_id.list_price')
    paid_amount = fields.Float('Paid Amount', readonly=False, store=True,compute="_payment_ids")
    outstanding = fields.Float('Outstanding', store=True,readonly=False, compute="_outstanding")
    payment_ids = fields.Many2many('account.payment', string='Payment Ids')
    amount_total = fields.Float('Amount to Pay', store=True,compute="get_total")
    house_no = fields.Char('House No')

    taxes_id = fields.Many2many('account.tax',
                                string=u'Taxes',
                                store=True,
                                compute="get_product_taxes")

    date_order = fields.Datetime(
        string='Purchased Date',
        required=False,
        index=True, default=fields.Datetime.now()) 
    state = fields.Selection([('draft', 'Draft'),
                              ('waiting', 'Waiting Confirmation'),
                              ('Allocated', 'Allocated'),
                              ('done', 'Sold'),
                              ('refused', 'Refused'),
                              ('cancel', 'cancel')
                              ], string='Status', index=True, readonly=True, 
                             track_visibility='onchange', copy=False, 
                             default='draft', required=True, 
                             help='State')
    invoice_id = fields.Many2many('account.invoice', string='Invoices')
     
    initial_qty = fields.Float('Total Unit Qty') #compute="check_products_details", store=True)
    remain_qty = fields.Float('Remaining Unit Qty')# compute="check_products_details",store=True)
    sold_qty = fields.Float('Sold Unit Qty', compute="check_products_details",store=True)
     
    @api.one
    @api.depends('product_id','qty')
    def check_products_details(self): 
        product = self.env['product.allocation'].search([('branch_id', '=', self.branch_id.id),('id', '=', self.product_id.id)],limit=1)
        if product and self.qty: 
            sold = (product.sold_qty + product.remain_qty) - (product.initial_qty + self.qty) 
            self.sold_qty = sold

    @api.one
    @api.depends('product_id')
    def get_product_taxes(self):
        # appends = []
        # for rec in self.product_id.taxes_id:
        #     appends.append(rec.id)
        #     self.write({'taxes_id': [(4, rec.ids)]})
        self.label = self.product_id.label

    @api.one
    @api.depends('amount_total', 'paid_amount')
    def _outstanding(self):
        self.outstanding = self.paid_amount-self.amount_total

    @api.one
    @api.depends('payment_ids')
    def _payment_ids(self):
        total = self.mapped('payment_ids') #.filtered(lambda amount: amount.amount))
        for each in total:
            self.paid_amount += each.amount

    # @api.constrains('product_id')
    # def _check_units_available(self):
    #     if self.product_id.remain_qty == 0:
    #         raise ValidationError('The requested unit of house is less than 1')

    @api.depends('qty', 'list_price', 'taxes_id')
    def get_total(self):
        totals = 0.0
        taxes = 0.0
        for rec in self:
            if rec.taxes_id:
                for tax in rec.taxes_id:
                    if tax.amount_type == "fixed":
                        taxes += tax.amount
                        totals = (rec.qty * rec.list_price) + taxes
                    if tax.amount_type == "percent":
                        taxes += tax.amount / 100
                        totals = (rec.qty * rec.list_price) * taxes + (rec.qty * rec.list_price)   
            elif not rec.taxes_id:
                totals = rec.qty * rec.list_price
            rec.amount_total = totals
    @api.model
    def create(self, vals):
        sequence = self.env['ir.sequence'].next_by_code('house.allocation')
        vals['name'] = str(sequence)
        return super(HouseAllocation, self).create(vals)
        
    @api.multi
    def push_allocation(self):
        total = 0.0
        product_location = self.env['product.allocation'].search([('id','=', self.product_id.id)]) 
        self.state = "done"
        total = product_location.sold_qty + self.qty
        # raise ValidationError('The record cannot be completed because the payment is {}'.format(total))
        product_location.write({'sold_qty': total})
            
    @api.multi
    def allocation_confirm(self):
        if self.paid_amount < self.amount_total:
            raise ValidationError('The record cannot be completed because the payment is yet  below the Amount to pay')
        else:
            self.write({'state': 'Allocated'})

    def define_invoice_line(self, invoice):
        products = self.env['product.product']
        invoice_line_obj = self.env["account.invoice.line"]
        prod = 0
        product_search = products.search([('name', '=', self.product_id.name)], limit=1)
        if product_search:
            prod = product_search.id
        else:
            pro = products.create({'name': self.product_id.name})
            prod = pro.id
        inv_id = invoice.id
        # journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
         
        product_srch = products.search([('id', '=', prod)])
        # prd_account_id = journal.default_credit_account_id.id
        curr_invoice_line = {
                                'product_id': product_srch.id,
                                'name': "House Allocation Payment by: "+ str(self.partner_id.name),
                                'price_unit': self.amount_total,
                                'quantity': self.qty,
                                'price_subtotal': self.amount_total * self.qty,
                                'account_id': product_srch.categ_id.property_account_expense_categ_id.id,
                                'invoice_id': inv_id,
                            }

        invoice_line_obj.create(curr_invoice_line)   

    def payment_button_normal(self): 
        """ Create Customer Invoice.
        """
        invoice_list = [] 
        invoice_obj = self.env["account.invoice"]
          
        for inv in self:
            invoice = invoice_obj.create({
                'partner_id': inv.partner_id.id,
                'account_id': inv.partner_id.property_account_receivable_id.id,#partner.account_id.id,
                'fiscal_position_id': inv.partner_id.property_account_position_id.id,
                'branch_id': self.branch_id.id, 
                'date_invoice': fields.Datetime.now(),
                #'type': 'in_invoice', # going
                'type': 'out_invoice', # receiving
            })
            if invoice.id:
                invoice_list.append(invoice.id)
                self.define_invoice_line(invoice) 
                
                form_view_ref = self.env.ref('account.invoice_form', False)
                tree_view_ref = self.env.ref('account.invoice_tree', False)
                # self.write({'invoice_id':[(4, invoice_list)]})
                self.write({'invoice_id':[(4, invoice_list)]}) 
                invoice.action_invoice_open()
            else:
                raise ValidationError('ASAS')
            # return {
            #         'domain': [('id', 'in', [item.id for item in self.invoice_id])],
            #         'name': 'Invoices',
            #         'view_mode': 'form',
            #         'res_model': 'account.invoice',
            #         'type': 'ir.actions.act_window',
            #         # 'views': [(tree_view_ref.id, 'tree'), (form_view_ref.id, 'form')],
            #         'views': [(form_view_ref.id, 'form')],
            #     }
            xxxxlo = self.env['account.invoice'].search([('id', '=', invoice.id)])
            if not xxxxlo:
                raise ValidationError('There is no related invoice Created.')
            resp = {
                'type': 'ir.actions.act_window',
                'name': _('invoice'),
                'res_model': 'account.invoice',
                'view_type': 'form',
                'view_mode': 'form',
                'target': 'current',
                'res_id': xxxxlo.id,
                  
            }
            return resp
            
            # dummy, view_id = self.env['ir.model.data'].get_object_reference(
            # 'account', 'invoice_form')
            # return {
            #     'name': 'Invoices',
            #     'view_mode': 'form',
            #     'view_id': view_id,
            #     'view_type': 'form',
            #     'res_model': 'account.invoice',
            #     'type': 'ir.actions.act_window',
            #     'domain': [('id', 'in', [item.id for item in self.invoice_id])],
            #     'context': { 
            #         # 'default_stock_id': self.stock_id.id,
            #             },
            #     'target': 'current'
            # }
    
    @api.multi
    def see_breakdown_invoice(self):
        search_view_ref = self.env.ref(
            'account.view_account_invoice_filter', False)
        form_view_ref = self.env.ref('account.invoice_form', False)
        tree_view_ref = self.env.ref('account.invoice_tree', False)
        invoices = self.mapped('invoice_id').filtered(lambda state: state.state in ["open"])
        return {
            'domain': [('id', 'in', [item.id for item in invoices])],
            'name': 'Invoices',
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'views': [(tree_view_ref.id, 'tree'), (form_view_ref.id, 'form')],
            'search_view_id': search_view_ref and search_view_ref.id,
        }
        
    def get_url(self, id, name):
        base_url = http.request.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')
        base_url += '/web# id=%d&view_type=form&model=%s' % (id, name)
        return "<a href={}> </b>Click<a/>.".format(base_url)

    def send_mail_account_all(self):
        bodyx = "Dear Sir, <br/>A payment for allocation with Reference: {} have been made by the Accounts.\
        Kindly {} to view. <br/>\
        Regards".format(self.name, self.get_url(self.id, self._name))
        email_from = self.env.user.email
        group_user_id2 = self.env.ref('house_allocation.director').id
        group_user_id = self.env.ref('house_allocation.officer').id
        group_user_id3 = self.env.ref('account.group_account_user').id
        if self.id:
            bodyx = bodyx
            self.mail_sending_for_three(
                email_from,
                group_user_id,
                group_user_id2,
                group_user_id3,
                bodyx) 
        else:
            pass

    def mail_sending_for_three(
            self,
            email_from,
            group_user_id,
            group_user_id2,
            group_user_id3,
            bodyx):
        from_browse = self.env.user.name
        groups = self.env['res.groups']
        for order in self:
            group_users = groups.search([('id', '=', group_user_id)])
            group_users2 = groups.search([('id', '=', group_user_id2)])
            group_users3 = groups.search([('id', '=', group_user_id3)])
            group_emails = group_users.users
            group_emails2 = group_users2.users
            group_emails3 = group_users3.users

            append_mails = []
            append_mails_to = []
            append_mails_to3 = []
            for group_mail in group_emails:
                append_mails.append(group_mail.login)

            for group_mail2 in group_emails2:
                append_mails_to.append(group_mail2.login)

            for group_mail3 in group_emails3:
                append_mails_to3.append(group_mail3.login)

            all_mails = append_mails + append_mails_to + append_mails_to3 
            email_froms = str(from_browse) + " <" + str(email_from) + ">"
            mail_sender = (', '.join(str(item) for item in all_mails))
            subject = "Payment Notification"
            
            mail_data = {
                'email_from': email_froms,
                'subject': subject,
                'email_to': mail_sender,
                #'email_cc': mail_sender,
                'reply_to': email_from,
                'body_html': bodyx
            }
            mail_id = order.env['mail.mail'].create(mail_data)
            order.env['mail.mail'].send(mail_id)


class ProductAllocation(models.Model):
    _name = "product.allocation"
    _description = "Products"
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char('Name',  required=True, help="Please add house or plot name")
    taxes_id = fields.Many2many('account.tax', string=u'Taxes')
    initial_qty = fields.Float('Total Unit Qty', required=True)
    remain_qty = fields.Float('Remaining Unit Qty', compute='get_qty', store=True,required=False)
    sold_qty = fields.Float('Sold Unit Qty', store=True,required=False)
    list_price = fields.Float('Price Per Unit', required=True)
    label = fields.Many2one(
        'product.uom',
        string='Unit of Measure',
        )
    branch_id = fields.Many2one(
        'res.branch',
        string="Project Site",)
    
    @api.one
    @api.depends('sold_qty')
    def get_qty(self):
        self.remain_qty = self.initial_qty - self.sold_qty

    @api.model
    def create(self, vals): 
        res = super(ProductAllocation, self).create(vals)
        product_price = vals['list_price']  
        product_search = self.env['product.product'].search([('name', '=', vals['name'])],limit=1)
        if product_search:
            product_search.write({'list_price': product_price})
        else:
            product_id = self.env['product.product'].create({'name': vals['name'],
                                                             'type': 'service',
                                                             'membershipx': True,
                                                             'list_price': product_price, # vals['total_cost'],
                                                             'available_in_pos':False,
                                                             'taxes_id': []})
            vals['product_id'] = product_id.id
        return res
    
    @api.multi
    def write(self, vals):
        res = super(ProductAllocation, self).write(vals)
        product_price = self.list_price 
        product_search = self.env['product.product'].search([('name', '=', self.name)])
        if product_search:
            product_search.write({'name': self.name,'list_price': product_price})
        else:
            product_id = self.env['product.product'].create({'name': self.name,
                                                            'type': 'service',
                                                            'membershipx': True,
                                                            'list_price': product_price,
                                                            'available_in_pos':False,
                                                            'taxes_id': []}) 
            self.product_id = product_id.id
        return res

    @api.multi
    def unlink(self):
        product_id = self.env['product.product'].search([('name','=ilike',self.name)])
        try:
            for product in product_id:
                product.unlink()
                return super(ProductAllocation, self).unlink()
        except Exception as e:
            raise ValidationError('Please you cannot delete because {}'.format(e))