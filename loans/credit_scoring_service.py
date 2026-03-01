"""
Credit Scoring Engine - SRS 3.1.3
Automated credit risk assessment with configurable parameters

Scoring Model (0-100 points):
- Income Score (30 points): Based on monthly income vs loan installment
- Employment Score (25 points): Based on employment stability and type
- Credit History Score (20 points): Based on previous loan performance
- Existing Obligations Score (15 points): Debt-to-income ratio
- Age Score (10 points): Customer age and profile maturity

Scoring Thresholds:
- 75+ points: APPROVED (Auto-approve)
- 50-74 points: CONDITIONAL (Manual review required)
- Below 50: REJECTED (Auto-reject or senior review)
"""

from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from loans.models import CreditScore, Customer, LoanApplication, Loan


class CreditScoringEngine:
    """
    Automated credit scoring engine with configurable parameters
    """
    
    # Score Weights (Total = 100)
    INCOME_WEIGHT = Decimal('30')
    EMPLOYMENT_WEIGHT = Decimal('25')
    CREDIT_HISTORY_WEIGHT = Decimal('20')
    OBLIGATIONS_WEIGHT = Decimal('15')
    AGE_WEIGHT = Decimal('10')
    
    # Thresholds
    APPROVED_THRESHOLD = Decimal('75')
    CONDITIONAL_THRESHOLD = Decimal('50')
    
    def __init__(self, loan_application):
        """
        Initialize credit scoring for a loan application
        
        Args:
            loan_application: LoanApplication instance
        """
        self.application = loan_application
        self.customer = loan_application.customer
        self.calculation_details = {}
    
    def calculate_income_score(self):
        """
        Calculate income score (0-30 points)
        
        Factors:
        - Monthly income level
        - Income vs installment ratio (Affordability)
        - Income stability
        """
        score = Decimal('0')
        details = {}
        
        income = self.customer.monthly_income or Decimal('0')
        details['monthly_income'] = str(income)
        
        if income <= 0:
            details['reason'] = 'No income reported'
            self.calculation_details['income'] = details
            return score
        
        # Calculate estimated monthly installment
        # Simplified calculation - can be enhanced
        loan_amount = self.application.requested_amount
        tenure_months = self.application.tenure_months
        product = self.application.loan_product
        
        # Estimate total repayment
        interest = product.calculate_total_interest(loan_amount, tenure_months)
        fees = product.calculate_total_fees(loan_amount)
        total_repayment = loan_amount + interest + fees
        monthly_installment = total_repayment / tenure_months
        
        details['monthly_installment'] = str(monthly_installment)
        
        # Calculate debt service ratio
        existing_obligations = self.customer.existing_loans or Decimal('0')
        total_monthly_debt = monthly_installment + existing_obligations
        debt_service_ratio = (total_monthly_debt / income) * 100
        
        details['existing_obligations'] = str(existing_obligations)
        details['debt_service_ratio'] = f"{debt_service_ratio:.2f}%"
        
        # Score based on debt service ratio
        if debt_service_ratio <= 30:
            # Excellent - under 30% DSR
            score = self.INCOME_WEIGHT
            details['assessment'] = 'Excellent affordability'
        elif debt_service_ratio <= 40:
            # Good - 30-40% DSR
            score = self.INCOME_WEIGHT * Decimal('0.8')
            details['assessment'] = 'Good affordability'
        elif debt_service_ratio <= 50:
            # Fair - 40-50% DSR
            score = self.INCOME_WEIGHT * Decimal('0.6')
            details['assessment'] = 'Fair affordability'
        elif debt_service_ratio <= 60:
            # Poor - 50-60% DSR
            score = self.INCOME_WEIGHT * Decimal('0.3')
            details['assessment'] = 'Poor affordability - high risk'
        else:
            # Very poor - over 60% DSR
            score = Decimal('0')
            details['assessment'] = 'Unaffordable - very high risk'
        
        # Bonus for high income (absolute value)
        if income >= 100000:
            bonus = Decimal('3')
            score = min(score + bonus, self.INCOME_WEIGHT)
            details['high_income_bonus'] = str(bonus)
        elif income >= 50000:
            bonus = Decimal('2')
            score = min(score + bonus, self.INCOME_WEIGHT)
            details['medium_income_bonus'] = str(bonus)
        
        details['score'] = str(score)
        self.calculation_details['income'] = details
        
        return score
    
    def calculate_employment_score(self):
        """
        Calculate employment score (0-25 points)
        
        Factors:
        - Employment status
        - Employment duration
        - Employer verification status
        """
        score = Decimal('0')
        details = {}
        
        employment_status = self.customer.employment_status
        details['employment_status'] = employment_status
        
        # Base score by employment status
        if employment_status == Customer.EMPLOYED:
            score = Decimal('15')
            details['base_score'] = '15 (employed)'
        elif employment_status == Customer.SELF_EMPLOYED:
            score = Decimal('10')
            details['base_score'] = '10 (self-employed)'
        elif employment_status == Customer.RETIRED:
            score = Decimal('8')
            details['base_score'] = '8 (retired)'
        else:
            score = Decimal('0')
            details['base_score'] = '0 (unemployed)'
            details['score'] = str(score)
            self.calculation_details['employment'] = details
            return score
        
        # Employment duration bonus
        if self.customer.employment_date:
            employment_duration = relativedelta(
                date.today(),
                self.customer.employment_date
            )
            months_employed = employment_duration.years * 12 + employment_duration.months
            details['months_employed'] = months_employed
            
            if months_employed >= 24:
                # 2+ years employment
                bonus = Decimal('8')
                details['duration_bonus'] = '8 (2+ years)'
            elif months_employed >= 12:
                # 1-2 years employment
                bonus = Decimal('5')
                details['duration_bonus'] = '5 (1-2 years)'
            elif months_employed >= 6:
                # 6-12 months employment
                bonus = Decimal('2')
                details['duration_bonus'] = '2 (6-12 months)'
            else:
                # Less than 6 months
                bonus = Decimal('0')
                details['duration_bonus'] = '0 (< 6 months)'
            
            score += bonus
        
        # Employer verification bonus
        if hasattr(self.application, 'employer_verification'):
            verification = self.application.employer_verification
            if verification.status == 'VERIFIED' and verification.employment_confirmed:
                bonus = Decimal('2')
                score += bonus
                details['verification_bonus'] = '2 (verified)'
        
        score = min(score, self.EMPLOYMENT_WEIGHT)
        details['score'] = str(score)
        self.calculation_details['employment'] = details
        
        return score
    
    def calculate_credit_history_score(self):
        """
        Calculate credit history score (0-20 points)
        
        Factors:
        - Previous loans with Alba Capital
        - Repayment history
        - Default history
        - Current active loans
        """
        score = Decimal('0')
        details = {}
        
        # Get customer's loan history
        total_loans = Loan.objects.filter(customer=self.customer).count()
        details['total_previous_loans'] = total_loans
        
        if total_loans == 0:
            # New customer - neutral score
            score = self.CREDIT_HISTORY_WEIGHT * Decimal('0.5')
            details['assessment'] = 'New customer - no history'
            details['score'] = str(score)
            self.calculation_details['credit_history'] = details
            return score
        
        # Analyze loan history
        paid_loans = Loan.objects.filter(
            customer=self.customer,
            status='PAID'
        ).count()
        
        defaulted_loans = Loan.objects.filter(
            customer=self.customer,
            status__in=['DEFAULTED', 'WRITTEN_OFF']
        ).count()
        
        overdue_loans = Loan.objects.filter(
            customer=self.customer,
            status='OVERDUE'
        ).count()
        
        active_loans = Loan.objects.filter(
            customer=self.customer,
            status='ACTIVE'
        ).count()
        
        details['paid_loans'] = paid_loans
        details['defaulted_loans'] = defaulted_loans
        details['overdue_loans'] = overdue_loans
        details['active_loans'] = active_loans
        
        # Scoring logic
        if defaulted_loans > 0:
            # Has defaults - very negative
            score = Decimal('0')
            details['assessment'] = 'Has defaulted loans - disqualified'
        elif overdue_loans > 0:
            # Has overdue loans - penalize
            score = self.CREDIT_HISTORY_WEIGHT * Decimal('0.2')
            details['assessment'] = 'Has overdue loans - high risk'
        elif paid_loans >= 3:
            # 3+ fully paid loans - excellent
            score = self.CREDIT_HISTORY_WEIGHT
            details['assessment'] = 'Excellent repayment history'
        elif paid_loans >= 2:
            # 2 paid loans - good
            score = self.CREDIT_HISTORY_WEIGHT * Decimal('0.8')
            details['assessment'] = 'Good repayment history'
        elif paid_loans >= 1:
            # 1 paid loan - fair
            score = self.CREDIT_HISTORY_WEIGHT * Decimal('0.6')
            details['assessment'] = 'Fair repayment history'
        elif active_loans > 0:
            # Has active loans, none paid yet
            score = self.CREDIT_HISTORY_WEIGHT * Decimal('0.5')
            details['assessment'] = 'Active loans - no completed history'
        
        details['score'] = str(score)
        self.calculation_details['credit_history'] = details
        
        return score
    
    def calculate_obligations_score(self):
        """
        Calculate existing obligations score (0-15 points)
        
        Factors:
        - Existing loan obligations outside Alba Capital
        - Debt-to-income ratio
        - Number of active loans
        """
        score = Decimal('0')
        details = {}
        
        income = self.customer.monthly_income or Decimal('0')
        existing_obligations = self.customer.existing_loans or Decimal('0')
        
        details['monthly_income'] = str(income)
        details['existing_obligations'] = str(existing_obligations)
        
        if income <= 0:
            details['assessment'] = 'No income - cannot assess'
            details['score'] = '0'
            self.calculation_details['obligations'] = details
            return score
        
        # Calculate existing debt percentage
        debt_percentage = (existing_obligations / income) * 100
        details['debt_percentage'] = f"{debt_percentage:.2f}%"
        
        # Score based on debt percentage
        if debt_percentage == 0:
            # No existing debt - excellent
            score = self.OBLIGATIONS_WEIGHT
            details['assessment'] = 'No existing obligations'
        elif debt_percentage <= 20:
            # Low debt - very good
            score = self.OBLIGATIONS_WEIGHT * Decimal('0.9')
            details['assessment'] = 'Low existing obligations'
        elif debt_percentage <= 40:
            # Moderate debt - acceptable
            score = self.OBLIGATIONS_WEIGHT * Decimal('0.6')
            details['assessment'] = 'Moderate existing obligations'
        elif debt_percentage <= 60:
            # High debt - risky
            score = self.OBLIGATIONS_WEIGHT * Decimal('0.3')
            details['assessment'] = 'High existing obligations'
        else:
            # Very high debt - very risky
            score = Decimal('0')
            details['assessment'] = 'Very high existing obligations - high risk'
        
        details['score'] = str(score)
        self.calculation_details['obligations'] = details
        
        return score
    
    def calculate_age_score(self):
        """
        Calculate age score (0-10 points)
        
        Factors:
        - Customer age
        - Account age with Alba Capital
        """
        score = Decimal('0')
        details = {}
        
        customer_age = self.customer.get_age()
        
        if customer_age:
            details['customer_age'] = customer_age
            
            # Score based on age
            if 30 <= customer_age <= 55:
                # Prime age - most stable
                score = Decimal('7')
                details['age_assessment'] = 'Prime age group'
            elif 25 <= customer_age < 30 or 55 < customer_age <= 60:
                # Good age range
                score = Decimal('5')
                details['age_assessment'] = 'Good age group'
            elif 21 <= customer_age < 25 or 60 < customer_age <= 65:
                # Acceptable but riskier
                score = Decimal('3')
                details['age_assessment'] = 'Acceptable age group'
            elif customer_age < 21:
                # Too young
                score = Decimal('0')
                details['age_assessment'] = 'Below minimum age'
            else:
                # Above 65
                score = Decimal('2')
                details['age_assessment'] = 'Senior age group'
        else:
            details['age_assessment'] = 'Age not provided'
        
        # Account age bonus
        if self.customer.created_at:
            account_age = (date.today() - self.customer.created_at.date()).days
            details['account_age_days'] = account_age
            
            if account_age >= 365:
                # 1+ year relationship
                bonus = Decimal('3')
                details['account_age_bonus'] = '3 (1+ year)'
            elif account_age >= 180:
                # 6+ months relationship
                bonus = Decimal('2')
                details['account_age_bonus'] = '2 (6+ months)'
            elif account_age >= 90:
                # 3+ months relationship
                bonus = Decimal('1')
                details['account_age_bonus'] = '1 (3+ months)'
            else:
                bonus = Decimal('0')
                details['account_age_bonus'] = '0 (new customer)'
            
            score += bonus
        
        score = min(score, self.AGE_WEIGHT)
        details['score'] = str(score)
        self.calculation_details['age'] = details
        
        return score
    
    def calculate_total_score(self):
        """
        Calculate total credit score and recommendation
        
        Returns:
            CreditScore instance
        """
        # Calculate individual scores
        income_score = self.calculate_income_score()
        employment_score = self.calculate_employment_score()
        credit_history_score = self.calculate_credit_history_score()
        obligations_score = self.calculate_obligations_score()
        age_score = self.calculate_age_score()
        
        # Total score
        total_score = (
            income_score +
            employment_score +
            credit_history_score +
            obligations_score +
            age_score
        )
        
        # Determine recommendation
        if total_score >= self.APPROVED_THRESHOLD:
            recommendation = CreditScore.APPROVED
        elif total_score >= self.CONDITIONAL_THRESHOLD:
            recommendation = CreditScore.CONDITIONAL
        else:
            recommendation = CreditScore.REJECTED
        
        # Create or update CreditScore record
        credit_score, created = CreditScore.objects.update_or_create(
            loan_application=self.application,
            defaults={
                'customer': self.customer,
                'income_score': income_score,
                'employment_score': employment_score,
                'credit_history_score': credit_history_score,
                'existing_obligations_score': obligations_score,
                'age_score': age_score,
                'total_score': total_score,
                'recommendation': recommendation,
                'calculation_details': self.calculation_details,
            }
        )
        
        return credit_score
    
    @staticmethod
    def override_score(credit_score, new_recommendation, override_reason, overridden_by):
        """
        Override a credit score decision (SRS requirement)
        
        Args:
            credit_score: CreditScore instance
            new_recommendation: New recommendation (APPROVED/CONDITIONAL/REJECTED)
            override_reason: Justification for override
            overridden_by: User making the override
        
        Returns:
            Updated CreditScore instance
        """
        from django.utils import timezone
        
        credit_score.recommendation = new_recommendation
        credit_score.is_overridden = True
        credit_score.override_reason = override_reason
        credit_score.overridden_by = overridden_by
        credit_score.overridden_at = timezone.now()
        credit_score.save()
        
        return credit_score


def run_credit_score(loan_application):
    """
    Convenience function to run credit scoring
    
    Args:
        loan_application: LoanApplication instance
    
    Returns:
        CreditScore instance
    """
    engine = CreditScoringEngine(loan_application)
    return engine.calculate_total_score()
