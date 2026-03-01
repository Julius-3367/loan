"""
Django admin configuration for Accounting models
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from .models import (
    Account, JournalEntry, JournalLine, FiscalPeriod,
    BankStatement, BankTransaction, AccountType,
    CostCenter, Project, Currency, ExchangeRate,
    FixedAsset, DepreciationSchedule
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """Admin interface for Chart of Accounts"""
    
    list_display = [
        'code', 'name', 'account_type', 'current_balance_display',
        'is_active', 'is_control', 'parent'
    ]
    list_filter = ['account_type', 'is_active', 'is_control']
    search_fields = ['code', 'name', 'description']
    ordering = ['code']
    
    fieldsets = (
        ('Account Information', {
            'fields': ('code', 'name', 'account_type', 'parent', 'description')
        }),
        ('Account Properties', {
            'fields': ('is_active', 'is_control', 'current_balance')
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['current_balance', 'created_at', 'updated_at']
    
    def current_balance_display(self, obj):
        """Display formatted balance"""
        balance = obj.current_balance
        if balance >= 0:
            formatted_balance = f'{balance:,.2f}'
            return format_html(
                '<span style="color: green;">KES {}</span>',
                formatted_balance
            )
        else:
            formatted_balance = f'{abs(balance):,.2f}'
            return format_html(
                '<span style="color: red;">KES ({})</span>',
                formatted_balance
            )
    current_balance_display.short_description = 'Current Balance'
    
    def save_model(self, request, obj, form, change):
        """Set created_by on creation"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class JournalLineInline(admin.TabularInline):
    """Inline journal lines for journal entry"""
    model = JournalLine
    extra = 2
    fields = ['account', 'debit', 'credit', 'description']
    
    def get_readonly_fields(self, request, obj=None):
        """Make lines readonly if entry is posted"""
        if obj and obj.status == JournalEntry.Status.POSTED:
            return ['account', 'debit', 'credit', 'description']
        return []


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    """Admin interface for Journal Entries"""
    
    list_display = [
        'entry_number', 'date', 'entry_type', 'description_short',
        'total_debit', 'total_credit', 'status_display', 'created_by'
    ]
    list_filter = ['status', 'entry_type', 'date', 'created_at']
    search_fields = ['entry_number', 'reference', 'description']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Entry Information', {
            'fields': ('entry_number', 'entry_type', 'status', 'date', 'reference', 'description')
        }),
        ('Related Objects', {
            'fields': ('loan', 'loan_repayment', 'fiscal_period', 'reversed_entry'),
            'classes': ('collapse',)
        }),
        ('Balance Summary', {
            'fields': ('total_debit', 'total_credit'),
        }),
        ('Audit Information', {
            'fields': (
                'created_by', 'created_at',
                'posted_by', 'posted_at'
            ),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = [
        'entry_number', 'total_debit', 'total_credit',
        'created_at', 'posted_at'
    ]
    
    inlines = [JournalLineInline]
    
    actions = ['post_entries', 'reverse_entries']
    
    def get_readonly_fields(self, request, obj=None):
        """Make entire entry readonly if posted"""
        readonly = list(self.readonly_fields)
        if obj and obj.status == JournalEntry.Status.POSTED:
            return readonly + [
                'entry_type', 'status', 'date', 'reference', 'description',
                'loan', 'loan_repayment', 'fiscal_period'
            ]
        return readonly
    
    def description_short(self, obj):
        """Truncate description for list display"""
        return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
    description_short.short_description = 'Description'
    
    def status_display(self, obj):
        """Display colored status"""
        colors = {
            JournalEntry.Status.DRAFT: 'orange',
            JournalEntry.Status.POSTED: 'green',
            JournalEntry.Status.REVERSED: 'red',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    @admin.action(description='Post selected journal entries')
    def post_entries(self, request, queryset):
        """Bulk post journal entries"""
        posted = 0
        errors = []
        
        for entry in queryset.filter(status=JournalEntry.Status.DRAFT):
            try:
                entry.post(request.user)
                posted += 1
            except Exception as e:
                errors.append(f"{entry.entry_number}: {str(e)}")
        
        if posted:
            self.message_user(
                request,
                f'Successfully posted {posted} journal entry(ies)',
                level='success'
            )
        
        if errors:
            self.message_user(
                request,
                f'Errors: {"; ".join(errors)}',
                level='error'
            )
    
    @admin.action(description='Reverse selected journal entries')
    def reverse_entries(self, request, queryset):
        """Bulk reverse journal entries"""
        reversed = 0
        errors = []
        
        for entry in queryset.filter(status=JournalEntry.Status.POSTED):
            try:
                entry.reverse(request.user, description=f"Reversal requested by {request.user.get_full_name()}")
                reversed += 1
            except Exception as e:
                errors.append(f"{entry.entry_number}: {str(e)}")
        
        if reversed:
            self.message_user(
                request,
                f'Successfully reversed {reversed} journal entry(ies)',
                level='success'
            )
        
        if errors:
            self.message_user(
                request,
                f'Errors: {"; ".join(errors)}',
                level='warning'
            )
    
    def save_model(self, request, obj, form, change):
        """Set created_by on creation"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    """Admin interface for Journal Lines"""
    
    list_display = [
        'journal_entry', 'account', 'debit', 'credit', 'description'
    ]
    list_filter = ['journal_entry__date', 'account__account_type']
    search_fields = [
        'journal_entry__entry_number', 'account__code',
        'account__name', 'description'
    ]
    ordering = ['-journal_entry__date', 'journal_entry', 'id']
    
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        """Prevent direct creation of journal lines (use journal entry)"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent modification of posted lines"""
        if obj and obj.journal_entry.status == JournalEntry.Status.POSTED:
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of posted lines"""
        if obj and obj.journal_entry.status == JournalEntry.Status.POSTED:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    """Admin interface for Fiscal Periods"""
    
    list_display = [
        'name', 'start_date', 'end_date', 'is_closed',
        'closed_by', 'closed_at'
    ]
    list_filter = ['is_closed', 'start_date']
    search_fields = ['name']
    ordering = ['-start_date']
    
    fieldsets = (
        ('Period Information', {
            'fields': ('name', 'start_date', 'end_date')
        }),
        ('Closure Information', {
            'fields': ('is_closed', 'closed_by', 'closed_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['closed_by', 'closed_at', 'created_at']
    
    actions = ['close_periods']
    
    @admin.action(description='Close selected periods')
    def close_periods(self, request, queryset):
        """Bulk close fiscal periods"""
        from django.utils import timezone
        
        closed = queryset.filter(is_closed=False).update(
            is_closed=True,
            closed_by=request.user,
            closed_at=timezone.now()
        )
        
        self.message_user(
            request,
            f'Successfully closed {closed} fiscal period(s)',
            level='success'
        )


class BankTransactionInline(admin.TabularInline):
    """Inline bank transactions for bank statement"""
    model = BankTransaction
    extra = 0
    fields = [
        'transaction_date', 'transaction_type', 'reference',
        'description', 'amount', 'is_reconciled'
    ]
    readonly_fields = ['is_reconciled']


@admin.register(BankStatement)
class BankStatementAdmin(admin.ModelAdmin):
    """Admin interface for Bank Statements"""
    
    list_display = [
        'statement_number', 'bank_account', 'statement_date',
        'opening_balance', 'closing_balance', 'status',
        'imported_by', 'reconciled_by'
    ]
    list_filter = ['status', 'statement_date', 'bank_account']
    search_fields = ['statement_number', 'bank_account__name']
    ordering = ['-statement_date']
    date_hierarchy = 'statement_date'
    
    fieldsets = (
        ('Statement Information', {
            'fields': ('bank_account', 'statement_number', 'statement_date')
        }),
        ('Balances', {
            'fields': ('opening_balance', 'closing_balance')
        }),
        ('Reconciliation', {
            'fields': ('status', 'reconciled_by', 'reconciled_at'),
            'classes': ('collapse',)
        }),
        ('Import Information', {
            'fields': ('import_file', 'imported_by', 'imported_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['imported_by', 'imported_at', 'reconciled_by', 'reconciled_at']
    
    inlines = [BankTransactionInline]
    
    def save_model(self, request, obj, form, change):
        """Set imported_by on creation"""
        if not change:
            obj.imported_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    """Admin interface for Bank Transactions"""
    
    list_display = [
        'transaction_date', 'transaction_type', 'reference',
        'description_short', 'amount', 'is_reconciled'
    ]
    list_filter = [
        'is_reconciled', 'transaction_type', 'transaction_date',
        'bank_statement__bank_account'
    ]
    search_fields = ['reference', 'description']
    ordering = ['-transaction_date']
    date_hierarchy = 'transaction_date'
    
    readonly_fields = ['reconciled_by', 'reconciled_at']
    
    def description_short(self, obj):
        """Truncate description"""
        return obj.description[:40] + '...' if len(obj.description) > 40 else obj.description
    description_short.short_description = 'Description'


# =======================================================================================
# ADVANCED COST ACCOUNTING & MULTI-CURRENCY ADMIN
# =======================================================================================

@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    """Admin interface for Cost Centers"""
    list_display = ['code', 'name', 'parent', 'manager', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['code', 'name', 'description']
    ordering = ['code']
    
    fieldsets = (
        ('Cost Center Information', {
            'fields': ('code', 'name', 'description', 'parent')
        }),
        ('Management', {
            'fields': ('manager', 'is_active')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Admin interface for Projects"""
    list_display = [
        'code', 'name', 'status', 'manager', 'cost_center',
        'budgeted_cost', 'start_date', 'end_date'
    ]
    list_filter = ['status', 'cost_center', 'start_date']
    search_fields = ['code', 'name', 'description']
    ordering = ['-created_at']
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Project Information', {
            'fields': ('code', 'name', 'description', 'status')
        }),
        ('Timeline', {
            'fields': ('start_date', 'end_date')
        }),
        ('Budget', {
            'fields': ('budgeted_cost', 'budgeted_revenue')
        }),
        ('Organization', {
            'fields': ('cost_center', 'manager')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    """Admin interface for Currencies"""
    list_display = ['code', 'name', 'symbol', 'is_base', 'is_active']
    list_filter = ['is_base', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """Admin interface for Exchange Rates"""
    list_display = [
        'date', 'from_currency', 'to_currency', 'rate', 'source', 'created_by'
    ]
    list_filter = ['from_currency', 'to_currency', 'source', 'date']
    search_fields = ['from_currency__code', 'to_currency__code']
    ordering = ['-date', 'from_currency', 'to_currency']
    date_hierarchy = 'date'
    
    readonly_fields = ['created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class DepreciationScheduleInline(admin.TabularInline):
    """Inline depreciation schedules"""
    model = DepreciationSchedule
    extra = 0
    readonly_fields = ['period_start_date', 'period_end_date', 'depreciation_expense', 'accumulated_depreciation', 'closing_balance']
    can_delete = False


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    """Admin interface for Fixed Assets"""
    list_display = [
        'asset_number', 'name', 'category', 'purchase_cost',
        'purchase_date', 'depreciation_method', 'status', 'custodian'
    ]
    list_filter = ['category', 'status', 'depreciation_method', 'cost_center']
    search_fields = ['asset_number', 'name', 'location']
    ordering = ['asset_number']
    date_hierarchy = 'purchase_date'
    
    fieldsets = (
        ('Asset Identification', {
            'fields': ('asset_number', 'name', 'category', 'status')
        }),
        ('Purchase Details', {
            'fields': ('purchase_date', 'purchase_cost', 'salvage_value', 'location')
        }),
        ('Depreciation', {
            'fields': (
                'useful_life_years', 'depreciation_method',
                'asset_account', 'accumulated_depreciation_account',
                'depreciation_expense_account'
            )
        }),
        ('Organization', {
            'fields': ('cost_center', 'custodian')
        }),
        ('Disposal', {
            'fields': ('disposal_date', 'disposal_proceeds'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']
    inlines = [DepreciationScheduleInline]
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DepreciationSchedule)
class DepreciationScheduleAdmin(admin.ModelAdmin):
    """Admin interface for Depreciation Schedules"""
    list_display = [
        'fixed_asset', 'period_end_date', 'depreciation_expense',
        'accumulated_depreciation', 'closing_balance', 'journal_entry'
    ]
    list_filter = ['fixed_asset__category', 'period_end_date']
    search_fields = ['fixed_asset__asset_number', 'fixed_asset__name']
    ordering = ['-period_end_date', 'fixed_asset']
    date_hierarchy = 'period_end_date'
    
    readonly_fields = ['created_at']
