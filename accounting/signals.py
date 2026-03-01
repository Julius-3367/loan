"""
Accounting Signals - Automatic Journal Entry Creation

Listens to loan events and automatically generates proper
double-entry accounting entries.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from .models import JournalEntry, JournalLine
from .services import AccountingService
from loans.models import Loan, LoanRepayment


@receiver(post_save, sender=Loan)
def create_loan_disbursement_entry(sender, instance, created, **kwargs):
    """
    Create journal entry when loan is disbursed
    
    DR: Loans Receivable (Asset)
    CR: Cash/Bank (Asset)
    """
    # Only process when loan status changes to DISBURSED
    if not created:
        old_loan = Loan.objects.get(pk=instance.pk)
        if old_loan.status != Loan.LoanStatus.DISBURSED and instance.status == Loan.LoanStatus.DISBURSED:
            AccountingService.create_loan_disbursement_entry(instance)


@receiver(post_save, sender=LoanRepayment)
def create_loan_repayment_entry(sender, instance, created, **kwargs):
    """
    Create journal entry when loan repayment is received
    
    DR: Cash/Bank (Asset)
    CR: Loans Receivable (Asset) - for principal
    CR: Interest Income (Revenue) - for interest
    CR: Fee Income (Revenue) - for fees
    CR: Penalty Income (Revenue) - for penalties
    """
    if created:
        AccountingService.create_loan_repayment_entry(instance)
