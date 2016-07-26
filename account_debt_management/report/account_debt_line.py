# -*- coding: utf-8 -*-
from openerp import tools
from openerp import models, fields, api
import openerp.addons.decimal_precision as dp


class AccountDebtLine(models.Model):
    _name = "account.debt.line"
    _description = "Account Debt Line"
    _auto = False
    # we need id on order so we can get right amount when accumulating
    _order = 'date desc, date_maturity desc, move_id, id'
    _depends = {
        'account.move.line': [
            'account_id', 'debit', 'credit', 'date_maturity', 'partner_id',
            'amount_currency',
        ],
    }

    date = fields.Date(
        readonly=True
    )
    date_maturity = fields.Date(
        readonly=True
    )
    ref = fields.Char(
        'Reference',
        readonly=True
    )
    amount = fields.Float(
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        'Currency',
        readonly=True
    )
    amount_currency = fields.Float(
        digits_compute=dp.get_precision('Account'),
        readonly=True
    )
    move_id = fields.Many2one(
        'account.move',
        'Entry',
        readonly=True
    )
    move_line_id = fields.Many2one(
        'account.move.line',
        'Entry line',
        readonly=True
    )
    period_id = fields.Many2one(
        'account.period',
        'Period',
        readonly=True
    )
    account_id = fields.Many2one(
        'account.account',
        'Account',
        readonly=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        'Journal',
        readonly=True
    )
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear',
        'Fiscal Year',
        readonly=True
    )
    move_state = fields.Selection(
        [('draft', 'Unposted'), ('posted', 'Posted')],
        'Status',
        readonly=True
    )
    reconcile_id = fields.Many2one(
        'account.move.reconcile',
        'Reconciliation',
        readonly=True
    )
    reconcile_partial_id = fields.Many2one(
        'account.move.reconcile',
        'Partial Reconciliation',
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
        readonly=True
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        'Analytic Account',
        readonly=True
    )
    account_type = fields.Many2one(
        'account.account.type',
        'Account Type',
        readonly=True
    )
    type = fields.Selection([
        ('receivable', 'Receivable'),
        ('payable', 'Payable')],
        'Type',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        readonly=True
    )

    # computed fields
    display_name = fields.Char(
        compute='get_display_name'
    )
    financial_amount = fields.Float(
        compute='_get_amounts',
    )
    balance = fields.Float(
        compute='_get_amounts',
    )
    financial_balance = fields.Float(
        compute='_get_amounts',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )

    @api.one
    def get_display_name(self):
        self.display_name = '%s%s' % (
            self.move_id.display_name,
            self.move_id.display_name != self.ref and ' (%s)' % self.ref or '')

    @api.multi
    @api.depends('amount', 'amount_currency')
    def _get_amounts(self):
        """
        If debt_together in context then we discount payables and make
        cumulative all together
        """
        balance = 0.0
        financial_balance = 0.0
        # we need to reorder records
        for line in reversed(self.search(
                [('id', 'in', self.ids)], order=self._order)):
            balance += line.amount
            line.balance = balance
            financial_amount = line.currency_id and line.currency_id.compute(
                line.amount_currency,
                line.company_id.currency_id) or line.amount
            line.financial_amount = financial_amount
            financial_balance += financial_amount
            line.financial_balance = financial_balance

    def init(self, cr):
        tools.drop_view_if_exists(cr, self._table)
        query = """
            SELECT
                l.id as id,
                l.id as move_line_id,
                am.date as date,
                l.date_maturity as date_maturity,
                am.ref as ref,
                am.state as move_state,
                l.reconcile_id as reconcile_id,
                l.reconcile_partial_id as reconcile_partial_id,
                l.move_id as move_id,
                l.partner_id as partner_id,
                am.company_id as company_id,
                am.journal_id as journal_id,
                p.fiscalyear_id as fiscalyear_id,
                am.period_id as period_id,
                l.account_id as account_id,
                l.analytic_account_id as analytic_account_id,
                a.type as type,
                a.user_type as account_type,
                l.currency_id as currency_id,
                l.amount_currency as amount_currency,
                coalesce(l.debit, 0.0) - coalesce(l.credit, 0.0) as amount
            FROM
                account_move_line l
                left join account_account a on (l.account_id = a.id)
                left join account_move am on (am.id=l.move_id)
                left join account_period p on (am.period_id=p.id)
            WHERE
                l.state != 'draft' and type IN ('payable', 'receivable')
        """
        cr.execute("""CREATE or REPLACE VIEW %s as (%s
        )""" % (self._table, query))

    @api.multi
    def action_open_related_document(self):
        self.ensure_one()
        domain = [
            ('move_id', '=', self.move_id.id),
        ]
        view_id = False
        # TODO ver si queremos devolver lista si hay mas de uno
        record = self.env['account.invoice'].search(domain, limit=1)
        if not record:
            record = self.env['account.voucher'].search(domain, limit=1)
            if record:
                if record.type == 'receipt':
                    view_id = self.env['ir.model.data'].xmlid_to_res_id(
                        'account_voucher.view_vendor_receipt_form')
                elif record.type == 'payment':
                    view_id = self.env['ir.model.data'].xmlid_to_res_id(
                        'account_voucher.view_vendor_payment_form')
            else:
                record = self.move_id

        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': record.id,
            'view_id': view_id,
        }
